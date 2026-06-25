"""Engine orchestrator — drives the multi-agent reasoning loop.

Each tick:
  raw telemetry ─▶ verify ─▶ context ─▶ causal ─▶ FSM ─▶ action ─▶ persist + SSE

Owns FSM state, hardware state, NH₃ history (for the predictive slope), feed
schedule, chaos overrides, and the narrator auto-demo. The vision runtime is
owned by the app and passed in; the engine reads its latest assessment and
tells it to emulate stress during a confirmed hypoxia event.
"""
from __future__ import annotations

import asyncio
import csv
import logging
import math
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from .agents import action, causal, context, telemetry
from .causal.fsm import FSMState, Signals, transition
from .config import settings
from .integrations import OpenWeatherClient, TelegramClient, arm_voice
from .models import AgentEvent, AutoFeedLog, TelemetryLog
from .schemas import (
    AmbientContext,
    ChaosCommand,
    HardwareState,
    RiskAssessment,
    TankState,
    Telemetry,
    ToxicityAssessment,
    VisionAssessment,
)
from .sse import SSEBus
from .vision.broadcaster import VisionRuntime

log = logging.getLogger("aquabro.engine")

# Emergency aeration physically oxygenates the tank. While the aerator is
# engaged on an injected DO crash, the override ramps back up each tick so the
# demo visibly recovers — otherwise the override pins DO low forever and the
# tank stays CRITICAL until a manual reset (only the narrator auto-reset
# cleared it before).
AERATOR_DO_RECOVERY_PER_TICK = 0.6   # mg/L the aerator adds per tick
DO_RECOVERED = 6.5                   # safe level — override clears, source resumes

_NOTE_AGENT = {
    "VERIFY": "TELEMETRY",
    "CONTEXT": "CONTEXT",
    "CAUSAL": "CAUSAL",
    "ACTION": "ACTION",
    "FSM": "ORCHESTRATOR",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Telemetry source: CSV replay (Zenodo) or synthetic baseline ──────
class TelemetrySource:
    def __init__(self, csv_path) -> None:
        self.rows: list[tuple[float, float, float]] = self._load_csv(csv_path)
        self._idx = 0
        self._t0 = time.monotonic()

    @staticmethod
    def _load_csv(path) -> list[tuple[float, float, float]]:
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.reader(fh)
                header = [h.strip().lower() for h in next(reader, [])]
                di = next((i for i, h in enumerate(header) if "do" in h or "oxy" in h), None)
                pi = next((i for i, h in enumerate(header) if h == "ph" or "ph_" in h or "phlevel" in h.replace(" ", "")), None)
                ti = next((i for i, h in enumerate(header) if "temp" in h), None)
                if di is None or pi is None or ti is None:
                    return []
                rows: list[tuple[float, float, float]] = []
                for r in reader:
                    try:
                        rows.append((float(r[di]), float(r[pi]), float(r[ti])))
                    except (ValueError, IndexError):
                        continue
                return rows
        except FileNotFoundError:
            return []
        except Exception as exc:
            log.warning("telemetry CSV load failed (%s): %s", path, exc)
            return []

    def next(self) -> tuple[float, float, float]:
        if self.rows:
            row = self.rows[self._idx % len(self.rows)]
            self._idx += 1
            return row
        t = time.monotonic() - self._t0
        do = 6.6 + 0.35 * math.sin(t * 0.06) + 0.05 * math.sin(t * 0.7)
        ph = 7.15 + 0.04 * math.sin(t * 0.04)
        temp = 28.4 + 0.3 * math.sin(t * 0.02)
        return (do, ph, temp)


class Engine:
    def __init__(
        self,
        bus: SSEBus,
        vision: VisionRuntime,
        session_factory,
        weather: OpenWeatherClient | None = None,
        telegram: TelegramClient | None = None,
    ) -> None:
        self.bus = bus
        self.vision = vision
        self.session_factory = session_factory
        self.weather = weather or OpenWeatherClient()
        self.telegram = telegram or TelegramClient()
        self.source = TelemetrySource(settings.telemetry_csv_path)

        self.fsm = FSMState.NORMAL
        self.prev_fsm = FSMState.NORMAL
        self.prev_sensor_fault = False
        self.hardware = HardwareState()
        self.nh3_history: deque[tuple[datetime, float]] = deque(maxlen=30)
        self._feed_events: deque[tuple[float, float]] = deque()  # (monotonic, grams)
        self._next_feed_at = time.monotonic() + 8.0
        self._prev_telemetry: Telemetry | None = None
        self._override_do: float | None = None
        self._override_ph: float | None = None
        self._override_temp: float | None = None
        self._force_fault = False
        self.powered = True                # master on/off
        self._ticking = False              # guards nudge vs loop overlap
        self._manual_hold: dict[str, float] = {"aerator": 0.0, "feed_valve": 0.0}
        self.energy_wh: float = 0.0  # cumulative site electricity meter

        self._task: asyncio.Task[None] | None = None
        self._narrator: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._last_state: TankState = self._baseline_state()

    # ── lifecycle ───────────────────────────────────────────────────
    async def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="engine-loop")
            log.info("engine started (interval=%.1fs, csv=%d rows)",
                     settings.telemetry_interval, len(self.source.rows))

    async def stop(self) -> None:
        self._stop.set()
        for t in (self._task, self._narrator):
            if t:
                t.cancel()
        self._task = self._narrator = None

    # ── public control ──────────────────────────────────────────────
    def snapshot(self) -> TankState:
        return self._last_state

    async def emit_narrative(self, level: str, text: str) -> None:
        """Publish a human-readable narrative event (plain English, no jargon)."""
        await self.bus.publish({
            "type": "narrative", "ts": _now().isoformat(),
            "level": level, "text": text,
        })

    async def publish_hardware(self) -> None:
        """Publish the current hardware snapshot (shared by override paths)."""
        await self.bus.publish({
            "type": "hardware", "ts": _now().isoformat(),
            "hardware": self.hardware.model_dump(mode="json"),
        })

    async def _emit_transitions(
        self, prev_fsm: str, fsm: str, res, sensor_fault: bool,
        aerator_started: bool, feed_locked: bool,
    ) -> None:
        """Emit plain-English narrative on edge transitions only (not every tick)."""
        nh3 = res.toxicity.nh3_mg_l
        if prev_fsm != FSMState.AT_RISK and fsm == FSMState.AT_RISK:
            await self.emit_narrative(
                "warn",
                f"Water quality dropping. Ammonia is climbing toward unsafe levels "
                f"(NH3 {nh3:.3f} mg/L).",
            )
        if prev_fsm != FSMState.CRITICAL and fsm == FSMState.CRITICAL:
            await self.emit_narrative(
                "critical",
                "Critical: ammonia is toxic to the fish. Emergency measures engaged.",
            )
        if prev_fsm != FSMState.RECOVERING and fsm == FSMState.RECOVERING:
            await self.emit_narrative("info", "Levels stabilising. The tank is recovering.")
        if prev_fsm != FSMState.NORMAL and fsm == FSMState.NORMAL:
            await self.emit_narrative("good", "All clear. Water is back in the safe range.")
        if aerator_started:
            await self.emit_narrative(
                "info", "Aerator pump started to push oxygen into the tank."
            )
        if feed_locked:
            await self.emit_narrative(
                "info", "Auto-feeder paused to stop adding to the ammonia load."
            )
        if sensor_fault and not self.prev_sensor_fault:
            await self.emit_narrative(
                "warn", "Oxygen probe fault detected. Holding the last good reading."
            )
        self.prev_sensor_fault = sensor_fault

    def toxicity_history(self) -> list[dict]:
        """Recent NH₃ magnitude series for the predictive chart."""
        from .causal.math_models import NH3_THRESHOLD

        return [
            {"t": ts.isoformat(), "nh3": round(v, 5), "threshold": NH3_THRESHOLD}
            for ts, v in self.nh3_history
        ]

    def inject(self, cmd: ChaosCommand) -> None:
        if cmd.do is not None:
            self._override_do = cmd.do
        if cmd.ph is not None:
            self._override_ph = cmd.ph
        if cmd.temp_c is not None:
            self._override_temp = cmd.temp_c
        self._force_fault = bool(cmd.sensor_fault)
        log.info("chaos injected do=%s ph=%s temp=%s fault=%s",
                 self._override_do, self._override_ph, self._override_temp, self._force_fault)

    def reset(self) -> None:
        self._override_do = self._override_ph = self._override_temp = None
        self._force_fault = False
        self.hardware = HardwareState()
        self.fsm = FSMState.NORMAL
        self.prev_fsm = FSMState.NORMAL
        self.nh3_history.clear()
        self.vision.set_stress(False)
        self._manual_hold = {"aerator": 0.0, "feed_valve": 0.0}
        log.info("global reset")

    def set_manual(self, device: str, seconds: float = 30.0) -> None:
        """Operator took manual control — autonomy yields on that device for a window."""
        self._manual_hold[device] = time.monotonic() + seconds

    def _in_manual(self, device: str) -> bool:
        return time.monotonic() < self._manual_hold.get(device, 0.0)

    async def apply_hardware_override(
        self, device: str, action: str, rate_pct: float | None = None,
    ) -> HardwareState | None:
        """Apply a manual override and claim manual control so the loop won't
        immediately undo it (e.g. auto-restoring a held feed valve)."""
        if device == "aerator":
            self.hardware = self.hardware.model_copy(update={"aerator": action})
        elif device == "feed_valve":
            update = {"feed_valve": action}
            if rate_pct is not None:
                update["feed_rate_pct"] = rate_pct
            self.hardware = self.hardware.model_copy(update=update)
        else:
            return None
        self.set_manual(device)
        return self.hardware

    async def set_narrator(self, run: bool) -> None:
        if run and self._narrator is None:
            self._narrator = asyncio.create_task(self._narrator_script(), name="narrator")
        elif not run and self._narrator is not None:
            self._narrator.cancel()
            self._narrator = None

    async def nudge(self) -> None:
        """Process one tick immediately so button presses feel instant —
        injected faults / overrides publish without waiting on the loop interval."""
        if not self.powered or self._ticking:
            return
        self._ticking = True
        try:
            await self._tick()
        except Exception:
            log.exception("nudge tick failed")
        finally:
            self._ticking = False

    async def set_power(self, on: bool) -> None:
        """Master on/off. Off ⇒ halt tracking + logs; On ⇒ resume immediately."""
        self.powered = on
        if on:
            log.info("system powered ON")
            await self.nudge()
        else:
            await self.set_narrator(False)
            self.vision.set_stress(False)
            off = self._last_state.model_copy(update={"system_on": False})
            self._last_state = off
            await self.bus.publish({"type": "state", "ts": _now().isoformat(),
                                    "state": off.model_dump(mode="json")})
            log.info("system powered OFF — tracking + logs halted")

    # ── main loop ───────────────────────────────────────────────────
    async def _loop(self) -> None:
        while not self._stop.is_set():
            if self.powered:
                try:
                    await self._tick()
                except Exception:
                    log.exception("tick failed")
            await asyncio.sleep(settings.telemetry_interval if self.powered else 1.0)

    async def _tick(self) -> None:
        # 0. emergency aeration heals an injected DO crash: ramp the override
        # back up while the aerator is engaged, then hand control back to the
        # telemetry source once the tank is safe.
        if self.hardware.aerator == "ACTIVE" and self._override_do is not None:
            self._override_do = min(
                self._override_do + AERATOR_DO_RECOVERY_PER_TICK, DO_RECOVERED
            )
            if self._override_do >= DO_RECOVERED:
                self._override_do = None
                log.info("aerator recovered DO — override cleared")

        # 1. raw telemetry (+ chaos overrides)
        do, ph, temp = self.source.next()
        is_override = False
        if self._override_do is not None:
            do, is_override = self._override_do, True
        if self._override_ph is not None:
            ph, is_override = self._override_ph, True
        if self._override_temp is not None:
            temp, is_override = self._override_temp, True
        raw = Telemetry(timestamp=_now(), do_level=do, ph_level=ph, temp_c=temp, is_override=is_override)

        vision: VisionAssessment | None = self.vision.assessment

        # 2. telemetry verification (sensor-fault vs bio crash)
        ver = telemetry.verify(raw, self._prev_telemetry, vision)
        sensor_fault = ver.sensor_fault or self._force_fault
        self._prev_telemetry = ver.telemetry

        # 3. context (ambient + organic load)
        ambient = await self.weather.get_ambient()
        self._tick_feed()
        ctx = context.build_context(ambient, self._recent_feed_mass())

        # 4. causal diagnosis
        res = causal.diagnose(
            ver.telemetry, vision, ctx.tan_estimate, list(self.nh3_history),
            sensor_fault=sensor_fault, hypoxia_confirmed=ver.hypoxia_confirmed,
        )
        self.nh3_history.append((_now(), res.toxicity.nh3_mg_l))

        # 5. FSM
        action_active = self.hardware.aerator == "ACTIVE" or self.hardware.feed_valve == "LOCKED"
        recovering = res.severity != "CRITICAL" and ver.telemetry.do_level > 3.0 and res.toxicity.slope_per_min <= 0
        tr = transition(self.fsm, Signals(severity=res.severity, action_active=action_active, recovering=recovering))
        self.prev_fsm, self.fsm = self.fsm, tr.state
        fsm_notes: list[str] = []
        if tr.changed:
            fsm_notes.append(f"[FSM] {self.prev_fsm.value}→{self.fsm.value}: {tr.reason}.")

        # 6. action plan + hardware application
        plan = action.plan(res, self.hardware)
        prev_aerator = self.hardware.aerator
        prev_feed_valve = self.hardware.feed_valve
        hw_changed = False
        if plan.aerator is not None and plan.aerator != self.hardware.aerator and not self._in_manual("aerator"):
            self.hardware = self.hardware.model_copy(update={"aerator": plan.aerator})
            hw_changed = True
        if plan.feed_valve is not None and plan.feed_valve != self.hardware.feed_valve and not self._in_manual("feed_valve"):
            update = {"feed_valve": plan.feed_valve}
            if plan.feed_rate_pct is not None:
                update["feed_rate_pct"] = plan.feed_rate_pct
            self.hardware = self.hardware.model_copy(update=update)
            hw_changed = True
        aerator_started = hw_changed and self.hardware.aerator == "ACTIVE" and prev_aerator != "ACTIVE"
        feed_locked = hw_changed and self.hardware.feed_valve == "LOCKED" and prev_feed_valve != "LOCKED"

        # Sync the synthetic vision to oxygen level: real fish gasp and go
        # lethargic as DO falls, so the synthetic detector emulates that.
        # (Only affects SyntheticDetector — real clips drive their own detection.)
        self.vision.set_stress(ver.telemetry.do_level <= 2.0)

        # 7. integrations: telegram + voice on entering CRITICAL
        if self.fsm == FSMState.CRITICAL and self.prev_fsm != FSMState.CRITICAL:
            if plan.telegram_text:
                await self.telegram.send(plan.telegram_text)
        voice_intent = None
        if plan.voice_prompt and self.fsm == FSMState.CRITICAL and self.prev_fsm != FSMState.CRITICAL:
            voice_intent = arm_voice(plan.voice_prompt)

        # 8. assemble state (+ site energy meter — always counting while running)
        load_w = self._power_load_w()
        self.energy_wh += load_w * (settings.telemetry_interval / 3600.0)
        state = TankState(
            fsm_state=self.fsm.value,
            telemetry=ver.telemetry,
            vision=vision,
            context=ctx.ambient,
            toxicity=res.toxicity,
            risks=res.risks,
            hardware=self.hardware,
            sensor_fault=sensor_fault,
            system_on=self.powered,
            power_w=load_w,
            energy_wh=self.energy_wh,
            updated_at=_now(),
        )
        self._last_state = state

        # 9. persist (best-effort)
        notes = ver.notes + ctx.notes + res.notes + plan.notes + fsm_notes
        await self._persist(ver.telemetry, plan, notes)

        # 9b. edge-triggered narrative (human, plain English — no jargon)
        await self._emit_transitions(
            self.prev_fsm,
            self.fsm,
            res,
            sensor_fault,
            aerator_started,
            feed_locked,
        )

        # 10. SSE publish
        await self._publish(state, res.toxicity, notes, voice_intent, hw_changed)

    # ── helpers ─────────────────────────────────────────────────────
    def _baseline_state(self) -> TankState:
        return TankState(
            fsm_state="NORMAL",
            telemetry=Telemetry(timestamp=_now(), do_level=6.6, ph_level=7.2, temp_c=28.4),
            hardware=HardwareState(),
            system_on=True,
            power_w=40.0,
            energy_wh=0.0,
            updated_at=_now(),
        )

    def _tick_feed(self) -> None:
        now = time.monotonic()
        # purge feed events older than 60s
        while self._feed_events and now - self._feed_events[0][0] > 60.0:
            self._feed_events.popleft()
        if self.hardware.feed_valve == "ACTIVE" and now >= self._next_feed_at:
            self._feed_events.append((now, 10.0))
            self._next_feed_at = now + 8.0

    def _recent_feed_mass(self) -> float:
        return sum(g for _, g in self._feed_events)

    def _power_load_w(self) -> float:
        """Instantaneous site draw: always-on baseline + running actuators."""
        load = 40.0  # controller, probes, circulation pump — always on
        if self.hardware.aerator == "ACTIVE":
            load += 750.0
        if self.hardware.feed_valve == "ACTIVE":
            load += 60.0
        return load

    async def _persist(self, tel: Telemetry, plan, notes: list[str]) -> None:
        try:
            async with self.session_factory() as session:
                session.add(TelemetryLog(
                    timestamp=tel.timestamp, tank_id=tel.tank_id,
                    do_level=tel.do_level, ph_level=tel.ph_level, temp_c=tel.temp_c,
                    is_override=tel.is_override,
                ))
                if plan.feed_valve == "LOCKED":
                    session.add(AutoFeedLog(
                        mass_grams=0.0, status="LOCKED_BY_AI",
                        rate_pct=plan.feed_rate_pct or self.hardware.feed_rate_pct,
                    ))
                for n in notes:
                    agent = "ORCHESTRATOR"
                    for tag, name in _NOTE_AGENT.items():
                        if tag in n:
                            agent = name
                            break
                    session.add(AgentEvent(agent=agent, message=n))
                await session.commit()
        except Exception:
            log.debug("persist skipped (db unavailable)", exc_info=True)

    async def _publish(self, state: TankState, tox: ToxicityAssessment,
                       notes: list[str], voice_intent, hw_changed: bool) -> None:
        await self.bus.publish({"type": "state", "ts": state.updated_at.isoformat(),
                                "state": state.model_dump(mode="json")})
        await self.bus.publish({
            "type": "toxicity", "ts": state.updated_at.isoformat(),
            "nh3": tox.nh3_mg_l, "fraction": tox.nh3_fraction,
            "threshold": tox.threshold_mg_l, "slope": tox.slope_per_min,
            "ph": tox.ph, "temp_c": tox.temp_c, "tan": tox.tan,
        })
        for n in notes:
            agent = next((v for k, v in _NOTE_AGENT.items() if k in n), "ORCHESTRATOR")
            await self.bus.publish({"type": "reasoning", "ts": state.updated_at.isoformat(),
                                    "agent": agent, "message": n})
        if voice_intent is not None:
            await self.bus.publish({"type": "voice", "ts": state.updated_at.isoformat(),
                                    "provider": voice_intent.provider,
                                    "system_prompt": voice_intent.system_prompt,
                                    "agent_id": voice_intent.agent_id,
                                    "webhook_url": voice_intent.webhook_url})
        if hw_changed:
            await self.bus.publish({"type": "hardware", "ts": state.updated_at.isoformat(),
                                    "hardware": state.hardware.model_dump(mode="json")})

    # ── narrator: auto 3-minute demo ────────────────────────────────
    async def _narrator_script(self) -> None:
        """Auto-run the spec's 3-state demo on a timer for a reliable live show."""
        steps = [
            (1.0, lambda: self.reset()),
            (6.0, lambda: self.inject(ChaosCommand(ph=8.7))),               # §3.1/3.3 toxicity
            (22.0, lambda: self.reset()),
            (4.0, lambda: self.inject(ChaosCommand(do=1.2))),               # §3.2 hypoxia (+vision stress)
            (22.0, lambda: self.reset()),
        ]
        try:
            while not self._stop.is_set():
                for delay, fn in steps:
                    if self._stop.is_set():
                        return
                    fn()
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
