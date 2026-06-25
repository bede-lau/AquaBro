"""Fish detectors.

``MotionDetector`` is the default: background subtraction (MOG2) localizes
the biomass as foreground blobs, nearest-neighbour centroid tracking yields
motion vectors, and the aggregate displacement becomes an *activity index*.
That index — not a trained class label — is what drives the lethargy /
surface-piping signals. It needs no labelled tilapia weights and runs on the
raw Zenodo MP4s.

``YoloDetector`` is an opt-in drop-in: supply weights (``VISION_YOLO_WEIGHTS``)
and it returns the same ``Detection`` shape. ``SyntheticDetector`` is the
zero-dependency fallback so the system runs before any video/cv2 is present.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..schemas import VisionAssessment

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np


@dataclass(slots=True)
class Detection:
    activity_index: float          # 0..1 normalized motion energy
    lethargy: bool
    surface_piping: bool
    fish_count: int
    mean_depth_norm: float         # 0=surface, 1=bottom
    fault: bool = False
    annotated: "np.ndarray | None" = None  # BGR frame with overlay


@runtime_checkable
class Detector(Protocol):
    def detect(self, frame: "np.ndarray") -> Detection: ...

    def to_assessment(self, d: Detection) -> VisionAssessment:
        ...


def _to_assessment(d: Detection) -> VisionAssessment:
    return VisionAssessment(
        activity_index=round(d.activity_index, 3),
        lethargy=d.lethargy,
        surface_piping=d.surface_piping,
        fish_count=d.fish_count,
        mean_depth_norm=round(d.mean_depth_norm, 3),
        fault=d.fault,
    )


# ── Synthetic fallback (no deps) ─────────────────────────────────────
class SyntheticDetector:
    """Deterministic synthetic activity so the loop runs without video.

    Produces a slow sine around a healthy baseline; ``set_stress`` lets the
    engine simulate lethargy during a DO-crash demo even with no camera.
    """

    def __init__(self) -> None:
        self._t = 0.0
        self._stress = False

    def set_stress(self, on: bool) -> None:
        self._stress = on

    def detect(self, frame: "np.ndarray | None") -> Detection:  # type: ignore[override]
        import math

        self._t += 0.12
        if self._stress:
            activity = max(0.02, 0.05 + 0.03 * math.sin(self._t))
            lethargy, piping = True, True
            depth = 0.15
        else:
            activity = 0.45 + 0.18 * math.sin(self._t)
            activity = max(0.05, min(1.0, activity))
            lethargy = activity < 0.12
            piping = False
            depth = 0.55
        return Detection(
            activity_index=activity,
            lethargy=lethargy,
            surface_piping=piping,
            fish_count=24,
            mean_depth_norm=depth,
            fault=True,
        )

    def to_assessment(self, d: Detection) -> VisionAssessment:
        return _to_assessment(d)


# ── Motion-based detector (cv2) ──────────────────────────────────────
class MotionDetector:
    """Frame-differencing motion detector.

    MOG2 background subtraction absorbs slow/steady swimmers into the
    background on real footage (the fish literally vanish from the mask).
    Temporal frame differencing flags anything that moves between frames, so
    the biomass stays visible regardless of swim speed. ``activity`` is motion
    energy (foreground ratio); ``fish_count`` is motion blobs above ``min_area``.
    """

    def __init__(
        self,
        diff_thresh: int = 8,
        min_area: int = 8,
        gap: int = 5,
        max_width: int = 640,
        dilate: int = 2,
    ) -> None:
        self.diff_thresh = diff_thresh
        self.min_area = min_area
        self.gap = gap
        self.max_width = max_width
        self._dilate = dilate
        self._buf: "collections.deque" = collections.deque(maxlen=gap + 1)
        self._ema_activity = 0.35
        try:
            import cv2  # type: ignore

            self._cv2 = cv2
            self._kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            self._ok = True
        except Exception:
            self._cv2 = None  # type: ignore[assignment]
            self._kern = None  # type: ignore[assignment]
            self._ok = False

    def detect(self, frame: "np.ndarray") -> Detection:  # type: ignore[override]
        if not self._ok or frame is None:
            return Detection(0.0, True, False, 0, 0.5, fault=True)
        cv2 = self._cv2
        h, w = frame.shape[:2]
        if w > self.max_width:
            scale = self.max_width / w
            frame = cv2.resize(frame, (self.max_width, int(h * scale)))
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        self._buf.append(gray)
        if len(self._buf) < self.gap + 1:
            return Detection(self._ema_activity, False, False, 0, 0.5, fault=False, annotated=frame)

        # diff across a gap of frames — catches slow swimmers that single-frame
        # diff and MOG2 both miss on real footage.
        diff = cv2.absdiff(self._buf[0], self._buf[-1])
        _, mask = cv2.threshold(diff, self.diff_thresh, 255, cv2.THRESH_BINARY)
        if self._dilate:
            mask = cv2.dilate(mask, self._kern, iterations=self._dilate)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes: list[tuple[int, int, int, int]] = []
        centroids: list[tuple[float, float]] = []
        for c in contours:
            if cv2.contourArea(c) < self.min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            boxes.append((x, y, bw, bh))
            centroids.append((x + bw / 2.0, y + bh / 2.0))

        fg = cv2.countNonZero(mask)
        raw_activity = min(1.0, (fg / (w * h)) / 0.02)
        self._ema_activity = 0.8 * self._ema_activity + 0.2 * raw_activity
        activity = self._ema_activity

        mean_depth = (sum(cy for _, cy in centroids) / len(centroids) / h) if centroids else 0.5
        fish_count = len(boxes)
        lethargy = activity < 0.06 and fish_count == 0
        surface_piping = mean_depth < 0.25 and activity < 0.20

        for x, y, bw, bh in boxes:
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 120), 1)
        hud = (
            f"ACT {activity:.2f}  N={fish_count}  FG={fg}  DEPTH {mean_depth:.2f}"
            f"  {'LETHARGIC' if lethargy else 'ACTIVE'}{'  PIPING' if surface_piping else ''}"
        )
        cv2.rectangle(frame, (0, 0), (w, 26), (0, 0, 0), -1)
        cv2.putText(frame, hud, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 120), 1)

        return Detection(
            activity_index=activity,
            lethargy=lethargy,
            surface_piping=surface_piping,
            fish_count=fish_count,
            mean_depth_norm=mean_depth,
            fault=False,
            annotated=frame,
        )

    def to_assessment(self, d: Detection) -> VisionAssessment:
        return _to_assessment(d)


# ── YOLOv8 drop-in (optional) ────────────────────────────────────────
class YoloDetector:
    """Real detector. Requires ``ultralytics`` + trained weights.

    Returns the same Detection shape. Motion-derived signals (activity from
    centroid displacement, depth from bbox vertical position) still feed
    lethargy/piping so the behavioural logic is identical across detectors.
    """

    def __init__(self, weights: str, conf: float = 0.25, max_width: int = 640) -> None:
        self.conf = conf
        self.max_width = max_width
        self._prev_centroids: list[tuple[float, float]] = []
        self._ema_activity = 0.4
        try:
            from ultralytics import YOLO  # type: ignore

            self._model = YOLO(weights)
            self._ok = True
        except Exception:
            self._model = None  # type: ignore[assignment]
            self._ok = False

    def detect(self, frame: "np.ndarray") -> Detection:  # type: ignore[override]
        if not self._ok or self._model is None:
            return Detection(0.0, True, False, 0, 0.5, fault=True)
        import cv2  # type: ignore

        res = self._model.predict(frame, conf=self.conf, verbose=False)[0]
        h, w = frame.shape[:2]
        centroids: list[tuple[float, float]] = []
        for b in res.boxes:
            x1, y1, x2, y2 = map(float, b.xyxy[0].tolist())
            centroids.append(((x1 + x2) / 2, (y1 + y2) / 2))
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 120), 1)
        disp = 0.0
        if self._prev_centroids and centroids:
            for cx, cy in centroids:
                best = min(
                    ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
                    for px, py in self._prev_centroids
                )
                disp += best
        self._prev_centroids = centroids
        raw = disp / (max(1, len(centroids)) * max(1, w) * 0.05)
        raw = max(0.0, min(1.0, raw))
        self._ema_activity = 0.8 * self._ema_activity + 0.2 * raw
        activity = self._ema_activity
        depth = (sum(cy for _, cy in centroids) / len(centroids) / h) if centroids else 0.5
        n = len(centroids)
        return Detection(
            activity_index=activity,
            lethargy=activity < 0.12 and n > 0,
            surface_piping=depth < 0.25 and activity < 0.30,
            fish_count=n,
            mean_depth_norm=depth,
            fault=False,
            annotated=frame,
        )

    def to_assessment(self, d: Detection) -> VisionAssessment:
        return _to_assessment(d)


def make_detector(mode: str = "motion", yolo_weights: str = "") -> Detector:
    """Factory. Never raises — degrades to SyntheticDetector."""
    mode = (mode or "motion").lower()
    if mode == "yolo" and yolo_weights:
        det = YoloDetector(yolo_weights)
        if det._ok:  # type: ignore[attr-defined]
            return det
    if mode in ("motion", "yolo"):
        det = MotionDetector()
        if det._ok:  # type: ignore[attr-defined]
            return det
    return SyntheticDetector()
