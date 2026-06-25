"""Vision subsystem (spec §2.2 / §4.1).

  detector    — pluggable fish-detection strategies (motion-based default,
                YOLOv8 drop-in) with a zero-dependency synthetic fallback.
  broadcaster — replays Zenodo MP4s frame-by-frame as a local "RTSP" stream,
                runs the detector each frame, and serves an annotated MJPEG.

All cv2/numpy imports are lazy so the rest of the app imports cleanly even
without OpenCV installed.
"""
from .broadcaster import VisionRuntime
from .detector import Detection, Detector, SyntheticDetector, make_detector

__all__ = [
    "VisionRuntime",
    "Detection",
    "Detector",
    "SyntheticDetector",
    "make_detector",
]
