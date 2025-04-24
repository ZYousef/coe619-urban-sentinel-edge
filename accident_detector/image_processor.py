"""
image_processor.py

Defines ImageProcessor façade that combines motion detection and JPEG compression.
"""
import cv2
import logging
import threading
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional

from .config import Config

logger = logging.getLogger("accident_detector")

@dataclass(frozen=True)
class ImageProcessorConfig:
    """
    Configuration parameters for motion detection and image compression.
    """
    resize_width: int
    resize_height: int
    compression_quality: int
    motion_threshold_pixels: int
    motion_pixel_diff_threshold: int
    blur_ksize: Tuple[int, int] = (5, 5)
    diff_alpha: float = 0.25

class MotionDetector:
    """
    Detects motion between consecutive frames using frame differencing.
    """
    def __init__(self, cfg: ImageProcessorConfig) -> None:
        self.byte_diff = cfg.motion_pixel_diff_threshold
        self.pixel_threshold = cfg.motion_threshold_pixels
        self.blur_ksize = cfg.blur_ksize
        self.alpha = cfg.diff_alpha
        self.prev_frame: Optional[np.ndarray] = None
        self.lock = threading.Lock()

    def detect(self, frame: np.ndarray) -> bool:
        """
        Returns True if motion is detected in the given frame.
        """
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, self.blur_ksize, 0)
            with self.lock:
                if self.prev_frame is None:
                    self.prev_frame = gray
                    return False
                diff = cv2.absdiff(self.prev_frame, gray)
                changed = np.count_nonzero(diff > self.byte_diff)
                # Smooth previous frame toward current
                self.prev_frame = cv2.addWeighted(
                    self.prev_frame, 1 - self.alpha,
                    gray, self.alpha, 0
                )
            return changed > self.pixel_threshold
        except Exception as e:
            logger.error(f"Motion detection error: {e}", exc_info=True)
            return False

class Compressor:
    """
    Resizes an image and compresses it to JPEG.
    """
    def __init__(self, cfg: ImageProcessorConfig) -> None:
        self.resize_dim = (cfg.resize_width, cfg.resize_height)
        self.quality = cfg.compression_quality

    def compress(self, image: np.ndarray) -> Tuple[bytes, np.ndarray]:
        """
        Returns a tuple of (JPEG bytes, resized image array).
        """
        try:
            resized = cv2.resize(
                image, self.resize_dim, interpolation=cv2.INTER_AREA
            )
            params = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
            success, encoded = cv2.imencode('.jpg', resized, params)
            if not success:
                raise RuntimeError("JPEG encoding failed")
            return encoded.tobytes(), resized
        except Exception as e:
            logger.error(f"Image compression failed: {e}", exc_info=True)
            raise

class ImageProcessor:
    """
    Façade class: wraps MotionDetector and Compressor.
    """
    def __init__(self, config: Config) -> None:
        cfg = ImageProcessorConfig(
            resize_width=config.getint("Image", "ResizeWidth"),
            resize_height=config.getint("Image", "ResizeHeight"),
            compression_quality=config.getint("Image", "CompressionQuality"),
            motion_threshold_pixels=config.getint(
                "Performance", "MotionThresholdPixels"
            ),
            motion_pixel_diff_threshold=config.getint(
                "Performance", "MotionPixelDiffThreshold"
            )
        )
        self.detector = MotionDetector(cfg)
        self.compressor = Compressor(cfg)

    def detect_motion(self, frame: np.ndarray) -> bool:
        """Delegate to MotionDetector.detect."""
        return self.detector.detect(frame)

    def compress(self, frame: np.ndarray) -> Tuple[bytes, np.ndarray]:
        """Delegate to Compressor.compress."""
        return self.compressor.compress(frame)
