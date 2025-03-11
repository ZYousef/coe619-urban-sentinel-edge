"""
state.py

Defines the SystemState class, which is responsible for persisting and
loading application state between runs (e.g., last accident timestamps).
"""

import os
import time
import pickle
import threading
import logging

logger = logging.getLogger("accident_detector")

class SystemState:
    """
    Maintains and persists the system's state (e.g., the last time an
    accident was reported). Uses a pickled file for persistence.
    """
    def __init__(self, state_file):
        self.state_file = state_file
        self._lock = threading.Lock()
        self.last_accident_time = 0
        self.load()

    def load(self):
        """Loads state from disk if it exists; otherwise uses defaults."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "rb") as f:
                    state = pickle.load(f)
                self.last_accident_time = state.get("last_accident_time", 0)
                logger.info(f"Loaded state from {self.state_file}")
                return True
            except Exception as e:
                logger.error(f"State file corrupted: {e}")
                self._backup_corrupted_file()
                with self._lock:
                    self.last_accident_time = 0
                return False
        return True

    def _backup_corrupted_file(self):
        """
        Renames the corrupted state file so it doesn't keep failing
        on subsequent runs.
        """
        backup_path = f"{self.state_file}.corrupted.{int(time.time())}"
        try:
            os.rename(self.state_file, backup_path)
            logger.warning(f"Moved corrupted state to {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup corrupted state: {e}")

    def save(self):
        """Persists the current state to disk by pickling."""
        try:
            with self._lock:
                state_data = {"last_accident_time": self.last_accident_time}
            with open(self.state_file, "wb") as f:
                pickle.dump(state_data, f)
            logger.debug("State saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    def update_accident_time(self, timestamp=None):
        """Updates the last_accident_time and saves."""
        with self._lock:
            self.last_accident_time = timestamp or time.time()
        self.save()

    def is_in_cooldown(self, cooldown_period):
        """
        Returns True if the current time is still within 'cooldown_period'
        seconds of the last accident time; otherwise False.
        """
        with self._lock:
            return time.time() - self.last_accident_time < cooldown_period
