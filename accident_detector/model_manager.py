"""
model_manager.py

Contains the ModelManager class, which handles downloading the ML model
(if necessary) and loading it into memory for predictions.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import torch
from fastai.vision.all import load_learner, Learner, PILImage

from .config import Config

logger = logging.getLogger("accident_detector")

@dataclass(frozen=True)
class ModelConfig:
    """
    Configuration for model file location and download URL.
    """
    model_path: str
    download_url: str

class ModelManager:
    """
    Handles downloading, loading, and inference with the ML model.
    """
    def __init__(self, config: Config):
        self.config = config
        self._model: Optional[Learner] = None

        self.model_config = ModelConfig(
            model_path=self.config.get("Model", "Path"),
            download_url=self.config.get("Model", "DownloadURL"),
        )

        # Prepare a session with retries
        retries = Retry(total=3, backoff_factor=0.3,
                        status_forcelist=(500, 502, 504))
        adapter = HTTPAdapter(max_retries=retries)
        self._session = requests.Session()
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def download_model(self) -> bool:
        """
        Ensures the model file exists locally, downloading it if missing.
        """
        path = self.model_config.model_path

        if os.path.exists(path):
            logger.info(f"Model already exists at {path}")
            return True

        # Download model
        logger.info(f"Downloading model from {self.model_config.download_url} to {path}")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            response = self._session.get(
                self.model_config.download_url,
                stream=True,
                timeout=30
            )
            response.raise_for_status()
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            logger.error(f"Failed to download model: {e}", exc_info=True)
            return False

        logger.info(f"Model downloaded at {path}")
        return True

    def load_model(self) -> bool:
        """
        Loads the model into memory (lazy-loading). Logs the device used.
        """
        if self._model is not None:
            return True

        if not self.download_model():
            return False

        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading model on {device}")
            self._model = load_learner(
                self.model_config.model_path,
                cpu=(device == "cpu")
            )
            self._model.dls.device = torch.device(device)
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}", exc_info=True)
            return False

    def predict(self, img: PILImage) -> Tuple[str, float]:
        """
        Runs inference on a single image.

        Returns:
            label: predicted class label
            confidence: probability of the predicted label
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        try:
            pred, _, probs = self._model.predict(img)
            label = str(pred)
            confidence = float(probs.max())
            return label, confidence
        except Exception as e:
            logger.error(f"Prediction failed: {e}", exc_info=True)
            return "unknown", 0.0
