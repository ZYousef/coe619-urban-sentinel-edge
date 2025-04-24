"""
camera_manager.py

Manages interaction with a camera or video file source. Supports context-manager,
thread-safe initialization, and flexible loop strategies (rewind or random).
"""
import cv2
import logging
import threading
import random
from dataclasses import dataclass
from enum import Enum
from typing import Union, Optional

from .config import Config

logger = logging.getLogger("accident_detector")

class LoopMode(Enum):
    """Defines behavior when video source reaches the end."""
    REWIND = 'rewind'
    RANDOM = 'random'

@dataclass(frozen=True)
class CameraConfig:
    """Configuration parameters for camera/video capture."""
    source: Union[int, str]
    width: int
    height: int
    fps: float
    warmup_frames: int
    loop_mode: LoopMode

class CameraManager:
    """
    Context-manager-aware camera/video capture manager.

    Usage:
        with CameraManager(config) as cam:
            ret, frame = cam.read_frame()
    """
    def __init__(self, config: Config) -> None:
        # Parse source (int for device index or str for file path)
        src = config.get("Camera", "Source")
        try:
            self.source: Union[int, str] = int(src)
        except ValueError:
            self.source = src

        self.cfg = CameraConfig(
            source=self.source,
            width=config.getint("Camera", "Width"),
            height=config.getint("Camera", "Height"),
            fps=config.getfloat("Camera", "FPS"),
            warmup_frames=config.getint("Camera", "WarmupFrames"),
            loop_mode=LoopMode(config.get("Camera", "LoopMode"))
        )

        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()

    def __enter__(self) -> 'CameraManager':
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def initialize(self) -> bool:
        """
        Opens the capture device or file, sets properties, and reads warmup frames.
        Returns True on success.
        """
        with self._lock:
            try:
                cap = cv2.VideoCapture(self.cfg.source)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
                cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
                # ── If we're in RANDOM mode, jump to a random start frame better simulation ──
                if self.cfg.loop_mode == LoopMode.RANDOM:
                    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    if total > 0:
                        start = random.randint(0, total - 1)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
                # Warmup
                for _ in range(self.cfg.warmup_frames):
                    if not cap.read()[0]:
                        break

                if not cap.isOpened():
                    logger.error(f"Failed to open capture source {self.cfg.source}")
                    return False

                self._cap = cap
                logger.info(f"Camera initialized: {self.cfg.source}"
                            f" ({self.cfg.width}x{self.cfg.height}@{self.cfg.fps}fps)")
                return True

            except Exception as e:
                logger.error(f"Error initializing camera: {e}", exc_info=True)
                return False

    def read_frame(self) -> (bool, Optional[any]):
        """
        Reads a single frame from the capture. If at end-of-file, applies loop strategy.
        Returns (ret, frame).
        """
        with self._lock:
            if self._cap is None:
                logger.error("Capture device not initialized")
                return False, None

            ret, frame = self._cap.read()
            if not ret:
                # End of stream or error, apply loop strategy
                total = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if total > 0:
                    if self.cfg.loop_mode == LoopMode.RANDOM:
                        idx = random.randint(0, total - 1)
                        self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    else:
                        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self._cap.read()
                if not ret:
                    logger.warning("Failed to read frame after loop reset")
                    return False, None

            return True, frame

    def release(self) -> None:
        """Releases the capture device or file."""
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
                logger.info("Camera capture released")
