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
        self.event_id = None
        self.event_status = None
        self.load()

    def load(self):
        """Loads state from disk if it exists; otherwise initializes defaults."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "rb") as f:
                    state = pickle.load(f)
                self.last_accident_time = state.get("last_accident_time", 0)
                self.event_id = state.get("event_id", None)
                self.event_status = state.get("event_status", None)
            except Exception as e:
                self.reset_state()

    def reset_state(self):
        """Resets the system's state to default values."""
        with self._lock:
            self.last_accident_time = 0
            self.event_id = None
            self.event_status = None
        self.save()

    def save(self):
        """Saves the current state to disk."""
        with self._lock:
            state_data = {
                "last_accident_time": self.last_accident_time,
                "event_id": self.event_id,
                "event_status": self.event_status
            }
        with open(self.state_file, "wb") as f:
            pickle.dump(state_data, f)

    def update_accident_state(self, timestamp=None, event_id=None, event_status=None):
        """Updates the accident-related state and saves it."""
        with self._lock:
            self.last_accident_time = timestamp or time.time()
            self.event_id = event_id
            self.event_status = event_status
        self.save()

    def is_in_cooldown(self, cooldown_period):
        """Checks if the system is within the cooldown period."""
        with self._lock:
            if self.event_status != "validated":
                logger.info("Skipping cooldown due to non-validated event status.")
                return False
            return time.time() - self.last_accident_time < cooldown_period
