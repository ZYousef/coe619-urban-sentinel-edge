"""
camera_manager.py

Contains the CameraManager class, which initializes and reads frames
from the camera or a looping video source.
"""

import cv2
import time
import logging

logger = logging.getLogger("accident_detector")

class CameraManager:
    """
    Manages interaction with a camera or video feed. Responsible
    for opening, reading, and releasing the capture device.
    """
    def __init__(self, config):
        self.config = config
        self.width = config.getint("Camera", "Width", 640)
        self.height = config.getint("Camera", "Height", 480)
        self.fps = config.getint("Camera", "FPS", 10)
        self.warmup_frames = config.getint("Camera", "WarmupFrames", 5)
        self.cap = None

    def initialize(self):
        """
        Attempts to open the configured camera or video source,
        sets capture properties, and reads a few warmup frames.
        """
        try:
            # self.cap = cv2.VideoCapture(0)
            self.cap = cv2.VideoCapture(self.config.get("Camera", "loop_video"))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            if not self.cap.isOpened():
                logger.error("Could not open video stream")
                return False
            logger.info("Warming up camera...")
            for _ in range(self.warmup_frames):
                self.cap.read()
                time.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"Camera initialization error: {e}")
            return False

    def read_frame(self):
        """
        Reads a single frame from the camera or video file. Returns
        (ret, frame) just like cv2.VideoCapture.read().
        """
        if self.cap is None or not self.cap.isOpened():
            logger.warning("Camera not initialized or closed")
            return False, None
        return self.cap.read()

    def release(self):
        """
        Closes the video capture if it's open.
        """
        if self.cap is not None:
            logger.info("Closing video capture")
            self.cap.release()
            self.cap = None
