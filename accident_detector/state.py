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
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger("accident_detector")

class Status(Enum):
    """
    Possible statuses for an accident event.
    """
    REPORTED = "reported"
    VALIDATED = "validated"
    INVALID = "invalid"
    UNKNOWN = "unknown"

class SystemState:
    """
    Manages persistent system state across runs:
      - Last event_id
      - Whether an accident is unresolved
      - Timestamp of the last validation/invalid action (for cooldown)
    """
    def __init__(self, state_file: str):
        self._lock = threading.Lock()
        self.state_file = state_file

        # Default in-memory state
        self.event_id: Optional[str] = None
        self.unresolved: bool = False
        self.last_accident_time: Optional[float] = None

        # Load from disk if available
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        with self._lock:
            if not os.path.exists(self.state_file):
                return
            try:
                with open(self.state_file, "rb") as f:
                    data: Dict[str, Any] = pickle.load(f)
                self.event_id = data.get("event_id")
                self.unresolved = data.get("unresolved", False)
                self.last_accident_time = data.get("last_accident_time")
            except Exception as e:
                logger.error(f"Failed loading system state: {e}", exc_info=True)

    def _save_state(self) -> None:
        """Persist current state to disk."""
        with self._lock:
            data: Dict[str, Any] = {
                "event_id": self.event_id,
                "unresolved": self.unresolved,
                "last_accident_time": self.last_accident_time,
            }
            try:
                os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                with open(self.state_file, "wb") as f:
                    pickle.dump(data, f)
            except Exception as e:
                logger.error(f"Failed saving system state: {e}", exc_info=True)

    def mark_reported(self, event_id: str) -> None:
        """
        Called when an event is first reported.
        Marks it unresolved and stores the event_id.
        """
        with self._lock:
            self.event_id = event_id
            self.unresolved = True
            # last_accident_time set only on validation or invalid
            self._save_state()

    def mark_validated(self) -> None:
        """
        Called when an event becomes validated.
        Starts the cooldown period from now.
        """
        with self._lock:
            self.last_accident_time = time.time()
            # still unresolved until cleared
            self._save_state()

    def mark_invalid(self) -> None:
        """
        Called when an event is deemed invalid.
        Ends the unresolved state immediately and starts cooldown.
        """
        with self._lock:
            self.last_accident_time = time.time()
            self.unresolved = False
            self._save_state()

    def clear_unresolved(self) -> None:
        """
        Clears the unresolved flag (called after cooldown completes or on shutdown).
        """
        with self._lock:
            self.unresolved = False
            self._save_state()

    def is_unresolved(self) -> bool:
        """
        Returns True if an accident is currently unresolved.
        """
        with self._lock:
            return self.unresolved

    def is_in_cooldown(self, cooldown: int) -> bool:
        """
        Returns True if still within the cooldown period since last validation/invalid action.
        """
        with self._lock:
            if self.last_accident_time is None:
                return False
            return (time.time() - self.last_accident_time) < cooldown
