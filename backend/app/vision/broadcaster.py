"""Vision broadcaster — local "RTSP" sim from Zenodo MP4s + MJPEG server.

A single background task replays the 30s clips frame-by-frame (looped),
runs the detector each frame, caches the latest annotated JPEG + assessment,
and serves an MJPEG multipart stream to the dashboard. With no clips or no
OpenCV it falls back to a rendered synthetic tank so the visual + reasoning
both keep running for the demo.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from ..schemas import VisionAssessment
from .detector import Detection, SyntheticDetector, make_detector

AssessmentCallback = Callable[[VisionAssessment], Awaitable[None]]


class VisionRuntime:
    def __init__(
        self,
        clips_dir: str | Path,
        fps: int = 15,
        detector_mode: str = "motion",
        yolo_weights: str = "",
    ) -> None:
        self.clips_dir = Path(clips_dir)
        self.fps = max(1, fps)
        self.detector = make_detector(detector_mode, yolo_weights)
        # When no real clips are present the configured (real) detector has
        # nothing to look at, so a synthetic detector drives assessment instead
        # — this keeps the reasoning loop + stress injection working pre-dataset.
        self._fallback = SyntheticDetector()
        self.assessment: VisionAssessment | None = None
        self._jpeg: bytes | None = None
        self._clips: list[Path] = self._discover_clips()
        self._clip_idx = 0
        self._cap: object | None = None
        self._cv2: object | None = self._import_cv2()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._callback: AssessmentCallback | None = None
        self._stress = False

    @staticmethod
    def _import_cv2() -> object | None:
        try:
            import cv2  # type: ignore

            return cv2
        except Exception:
            return None

    # ── lifecycle ───────────────────────────────────────────────────
    def set_assessment_callback(self, cb: AssessmentCallback) -> None:
        self._callback = cb

    def set_stress(self, on: bool) -> None:
        """Tell a synthetic detector to emulate lethargy (DO-crash demo)."""
        self._stress = on
        self._fallback.set_stress(on)
        if isinstance(self.detector, SyntheticDetector):
            self.detector.set_stress(on)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._clips = self._discover_clips()
        self._task = asyncio.create_task(self._run(), name="vision-runtime")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._close_cap()

    # ── frame sources ───────────────────────────────────────────────
    def _discover_clips(self) -> list[Path]:
        if not self.clips_dir.exists():
            return []
        return sorted(
            p for p in self.clips_dir.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".avi"}
        )

    def _close_cap(self) -> None:
        if self._cap is not None and self._cv2 is not None:
            try:
                self._cap.release()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._cap = None

    async def _next_frame(self) -> "object | None":
        """Return next BGR ndarray from clips, rotating/looping. None if N/A."""
        if self._cv2 is None or not self._clips:
            return None
        cv2 = self._cv2
        loop = asyncio.get_event_loop()

        def _read() -> "object | None":
            if self._cap is None:
                clip = self._clips[self._clip_idx % len(self._clips)]
                self._cap = cv2.VideoCapture(str(clip))  # type: ignore[attr-defined]
            ok, frame = self._cap.read()  # type: ignore[attr-defined]
            if not ok or frame is None:
                self._close_cap()
                self._clip_idx += 1
                return None
            return frame

        return await loop.run_in_executor(None, _read)

    def _render_synthetic(self, d: Detection) -> "object | None":
        """Draw a faux tank view when no real clip is available."""
        if self._cv2 is None:
            return None
        import numpy as np  # type: ignore

        cv2 = self._cv2
        h, w = 360, 480
        frame = np.zeros((h, w, 3), dtype="uint8")
        # bluish water gradient
        for y in range(h):
            shade = 14 + int(40 * (y / h))
            frame[y, :] = (shade, shade - 6, 6)
        tag = "SYNTHETIC FEED" if isinstance(self.detector, SyntheticDetector) else "NO CLIP"
        label = f"{tag}  ACT {d.activity_index:.2f}  N={d.fish_count}"
        cv2.putText(frame, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 120), 1)
        cv2.putText(
            frame,
            f"{'LETHARGIC' if d.lethargy else 'ACTIVE'}{' · PIPING' if d.surface_piping else ''}",
            (10, 46),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 200, 255) if d.lethargy else (120, 255, 120),
            1,
        )
        return frame

    def _encode(self, frame: "object") -> bytes | None:
        if self._cv2 is None:
            return None
        cv2 = self._cv2
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])  # type: ignore[attr-defined]
        return bytes(buf) if ok else None

    # ── main loop ───────────────────────────────────────────────────
    async def _run(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            try:
                frame = await self._next_frame()
                if frame is None:
                    det = self._fallback.detect(None)  # no clip this tick
                    synthetic = self._render_synthetic(det)
                    self._jpeg = self._encode(synthetic) if synthetic is not None else self._jpeg
                else:
                    det = self.detector.detect(frame)  # type: ignore[arg-type]
                    self._jpeg = self._encode(det.annotated if det.annotated is not None else frame)

                self.assessment = self.detector.to_assessment(det)
                if self._callback is not None:
                    try:
                        await self._callback(self.assessment)
                    except Exception:
                        pass
            except Exception:
                # Never let the vision loop kill the process.
                pass
            await asyncio.sleep(interval)

    # ── MJPEG stream for FastAPI StreamingResponse ──────────────────
    async def mjpeg(self) -> AsyncIterator[bytes]:
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            jpeg = self._jpeg
            if jpeg is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            await asyncio.sleep(interval)
