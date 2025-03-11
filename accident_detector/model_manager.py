"""
model_manager.py

Contains the ModelManager class, which handles downloading the ML model
(if necessary) and loading it into memory for predictions.
"""

import os
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastai.vision.all import load_learner

logger = logging.getLogger("accident_detector")

class ModelManager:
    """
    Downloads and manages the AI model (Fast.ai exported .pkl).
    Also provides a predict() method to run inference on frames.
    """
    def __init__(self, config):
        self.model_path = config.get("System", "ModelPath")
        self.model_url = config.get("System", "ModelUrl")
        self._model = None
        self._lock = None
        self._model_loaded = False

        import threading
        self._lock = threading.Lock()

        self.session = requests.Session()
        retry_attempts = config.getint("API", "RetryAttempts", 5)
        retry_backoff_factor = config.getfloat("API", "RetryBackoffFactor", 1.0)
        retries = Retry(
            total=retry_attempts,
            backoff_factor=retry_backoff_factor,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def download_model(self):
        """
        Downloads the model file if it doesn't exist locally.
        Returns True if successful, False if there's an error.
        """
        if os.path.exists(self.model_path):
            return True

        logger.info(f"Downloading model from {self.model_url}")
        try:
            with self.session.get(self.model_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(self.model_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            file_size_mb = os.path.getsize(self.model_path) / (1024 * 1024)
            logger.info(f"Model downloaded successfully, size: {file_size_mb:.2f} MB")
            if not self._verify_model_integrity():
                logger.error("Model integrity check failed")
                os.remove(self.model_path)
                return False
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading model: {e}")
            return False

    def _verify_model_integrity(self):
        """
        Basic check to ensure the downloaded model is big enough and can load
        without throwing an exception. Returns True if valid.
        """
        try:
            size = os.path.getsize(self.model_path)
            if size < 1024:
                logger.error(f"Model file too small: {size} bytes")
                return False
            _ = load_learner(self.model_path, cpu=True)
            return True
        except Exception as e:
            logger.error(f"Failed to load AI model for integrity check: {e}")
            return False

    def load_model(self):
        """Loads the model into memory if not already loaded."""
        with self._lock:
            if self._model_loaded:
                return True
            try:
                if not os.path.exists(self.model_path):
                    logger.error("Model file not found")
                    return False
                self._model = load_learner(self.model_path, cpu=True)
                self._model_loaded = True
                logger.info("AI model loaded successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to load AI model: {e}")
                return False

    def predict(self, img):
        """
        Runs a prediction on the given PILImage. Returns (label, confidence).
        If the model isn't loaded or there's an error, returns ("unknown", 0.0).
        """
        with self._lock:
            if not self._model_loaded:
                if not self.load_model():
                    return "unknown", 0.0
            try:
                prediction, pred_idx, probs = self._model.predict(img)
                confidence = probs[pred_idx].item()
                return prediction, confidence
            except Exception as e:
                logger.error(f"Prediction error: {e}")
                return "unknown", 0.0
