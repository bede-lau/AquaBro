"""FastAPI application — wires engine, vision, SSE, webhooks, chaos controls.

Single process. The lifespan starts Postgres schema init, the vision runtime,
and the engine loop; everything degrades gracefully (no DB / no keys / no
clips ⇒ mock mode, app still serves).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .causal.graph import build_graph_view
from .config import settings
from .db import SessionLocal, init_db
from .engine import Engine
from .schemas import ChaosCommand, NarratorCommand
from .sse import SSEBus
from .vision.broadcaster import VisionRuntime

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("aquabro.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort schema creation — missing Postgres must not stop startup.
    try:
        await init_db()
        log.info("postgres schema ready")
    except Exception as exc:
        log.warning("postgres unavailable, running without persistence: %s", exc)

    bus = SSEBus()
    vision = VisionRuntime(
        clips_dir=settings.clips_path,
        fps=settings.vision_fps,
        detector_mode=settings.vision_detector,
        yolo_weights=settings.vision_yolo_weights,
    )
    await vision.start()
    engine = Engine(bus, vision, session_factory=SessionLocal)
    await engine.start()

    app.state.bus = bus
    app.state.vision = vision
    app.state.engine = engine

    # 2-way Telegram operator agent (long-polls inbound commands).
    app.state.telegram_agent = None
    app.state.telegram_task = None
    telegram_stop = asyncio.Event()
    app.state.telegram_stop = telegram_stop
    if settings.telegram_agent_ready:
        from .integrations.telegram import TelegramClient
        from .integrations.telegram_bot import TelegramAgent

        agent = TelegramAgent(engine, TelegramClient())
        app.state.telegram_agent = agent
        app.state.telegram_task = asyncio.create_task(
            agent.run(telegram_stop), name="telegram-agent"
        )
        log.info("telegram agent task started")
    else:
        log.info("telegram agent off")

    log.info("AquaBro up → http://localhost:%d  (docs /docs)", settings.app_port)
    try:
        yield
    finally:
        telegram_stop.set()
        t = app.state.telegram_task
        if t is not None:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        await engine.stop()
        await vision.stop()


app = FastAPI(title="AquaBro API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _engine(request: Request) -> Engine:
    return request.app.state.engine


# ── health + state ──────────────────────────────────────────────────
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/api/state")
async def get_state(request: Request) -> dict:
    return _engine(request).snapshot().model_dump(mode="json")


@app.get("/api/causal/graph")
async def get_graph(request: Request) -> dict:
    return build_graph_view(_engine(request).snapshot()).model_dump(mode="json")


@app.get("/api/toxicity/history")
async def get_toxicity(request: Request) -> list[dict]:
    return _engine(request).toxicity_history()


# ── live streams ────────────────────────────────────────────────────
@app.get("/api/stream")
async def sse_stream(request: Request):
    bus: SSEBus = request.app.state.bus
    engine = _engine(request)
    q = bus.subscribe()

    async def gen():
        # seed the client with the current snapshot immediately
        await q.put({
            "type": "state", "ts": engine.snapshot().updated_at.isoformat(),
            "state": engine.snapshot().model_dump(mode="json"),
        })
        try:
            async for frame in bus.stream(q):
                if await request.is_disconnected():
                    break
                yield frame
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/vision/stream")
async def vision_stream(request: Request):
    vision: VisionRuntime = request.app.state.vision
    if vision._jpeg is None and vision._cv2 is None:
        raise HTTPException(503, "vision offline — install opencv or add clips to data/clips/")
    return StreamingResponse(vision.mjpeg(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/vision/state")
async def vision_state(request: Request) -> dict:
    v = request.app.state.vision.assessment
    return v.model_dump(mode="json") if v else {}


# ── chaos controls (Demo Chaos panel) ───────────────────────────────
@app.post("/api/chaos")
async def chaos(cmd: ChaosCommand, request: Request) -> dict:
    engine = _engine(request)
    if not engine.powered:
        return engine.snapshot().model_dump(mode="json")
    engine.inject(cmd)
    await engine.nudge()  # publish immediately — low-latency fault injection
    return engine.snapshot().model_dump(mode="json")


@app.post("/api/chaos/reset")
async def chaos_reset(request: Request) -> dict:
    engine = _engine(request)
    engine.reset()
    await engine.nudge()
    return engine.snapshot().model_dump(mode="json")


@app.post("/api/chaos/narrator")
async def chaos_narrator(cmd: NarratorCommand, request: Request) -> dict:
    await _engine(request).set_narrator(cmd.run)
    return {"narrator": cmd.run}


# ── master power (system on/off) ───────────────────────────────────
class PowerCommand(BaseModel):
    on: bool


@app.post("/api/system/power")
async def system_power(cmd: PowerCommand, request: Request) -> dict:
    await _engine(request).set_power(cmd.on)
    return _engine(request).snapshot().model_dump(mode="json")


# ── hardware override (ElevenLabs trigger_aerator webhook target) ───
class HardwareOverride(BaseModel):
    device: str            # "aerator" | "feed_valve"
    action: str            # "ACTIVE" | "STANDBY" | "LOCKED"
    rate_pct: float | None = None
    reason: str | None = None


@app.post("/api/hardware/override")
async def hardware_override(cmd: HardwareOverride, request: Request) -> dict:
    """Physical-world interface — also the webhook the voice agent's tool calls."""
    engine = _engine(request)
    if not engine.powered:
        return engine.hardware.model_dump(mode="json")
    hw = await engine.apply_hardware_override(cmd.device, cmd.action, cmd.rate_pct)
    if hw is None:
        raise HTTPException(400, f"unknown device {cmd.device}")
    await engine.nudge()  # publish immediately — low-latency manual control
    log.info("hardware override %s=%s reason=%s", cmd.device, cmd.action, cmd.reason)
    return hw.model_dump(mode="json")


@app.post("/api/voice/resolve")
async def voice_resolve(action: str, request: Request) -> dict:
    """Operator's spoken resolution of a voice escalation.

    Called by the frontend after the browser/ElevenLabs session hears
    "execute" or "cancel". Execute ⇒ fire the aerator webhook.
    """
    engine = _engine(request)
    if action.lower().startswith("exec"):
        await hardware_override(
            HardwareOverride(device="aerator", action="ACTIVE", reason="voice_execute"),
            request,
        )
        return {"resolved": "executed", "aerator": engine.hardware.aerator}
    return {"resolved": "cancelled", "aerator": engine.hardware.aerator}


@app.get("/api/telegram/status")
async def telegram_status(request: Request) -> dict:
    """Report the 2-way Telegram agent's configuration and live-poll state."""
    task = getattr(request.app.state, "telegram_task", None)
    polling = bool(task is not None and not task.done())
    return {
        "enabled": settings.telegram_agent_enabled,
        "configured": settings.telegram_configured,
        "ready": settings.telegram_agent_ready,
        "llm": settings.llm_configured,
        "model": settings.llm_text_model,
        "chat_id": settings.telegram_chat_id,
        "polling": polling,
    }
