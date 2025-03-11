"""
image_processor.py

Contains the ImageProcessor class, which performs tasks like
motion detection, image resizing, and JPEG compression.
"""

import cv2
import logging
import numpy as np
import threading

logger = logging.getLogger("accident_detector")

class ImageProcessor:
    """
    Responsible for detecting motion in frames, resizing/compressing
    images for efficient transmission, etc.
    """
    def __init__(self, config):
        self.resize_dim = (
            config.getint("Image", "ResizeWidth", 224),
            config.getint("Image", "ResizeHeight", 224)
        )
        self.compression_quality = config.getint("Image", "CompressionQuality", 70)
        self.motion_threshold_pixels = config.getint("Performance", "MotionThresholdPixels", 500)
        self.motion_pixel_diff_threshold = config.getint("Performance", "MotionPixelDiffThreshold", 25)
        self.prev_frame = None
        self.motion_detected = False
        self.motion_lock = threading.Lock()

    def compress_image(self, image):
        """
        Resizes and compresses an image using the configured width, height,
        and JPEG quality. Returns (buffer, resized_image).
        """
        try:
            resized = cv2.resize(image, self.resize_dim)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.compression_quality]
            _, buffer = cv2.imencode('.jpg', resized, encode_param)
            return buffer, resized
        except Exception as e:
            logger.error(f"Image compression failed: {e}")
            raise

    def detect_motion(self, frame):
        """
        Performs a simple motion detection by comparing the current frame
        to a blurred version of the previous frame, counting the number
        of changed pixels beyond a certain threshold.
        """
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            with self.motion_lock:
                if self.prev_frame is None:
                    self.prev_frame = gray
                    return False
                diff = cv2.absdiff(self.prev_frame, gray)
                changed_pixels = np.count_nonzero(diff > self.motion_pixel_diff_threshold)
                self.motion_detected = (changed_pixels > self.motion_threshold_pixels)

                # Update prev_frame using a weighted average for smoothing
                alpha = 0.75
                self.prev_frame = cv2.addWeighted(self.prev_frame, 1-alpha, gray, alpha, 0)
            return self.motion_detected
        except Exception as e:
            logger.error(f"Motion detection error: {e}")
            return False
