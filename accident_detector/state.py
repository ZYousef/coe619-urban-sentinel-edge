"""
state.py

Manages persistent system state across runs, including accident events,
cooldown timers, and resolution flags.
"""
import os
import time
import pickle
import threading
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("accident_detector")

class Status(Enum):
    REPORTED = "reported"
    VALIDATED = "validated"
    INVALID = "invalid"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"

class SystemState:
    """
    Thread-safe storage of system state persisted to disk.

    Tracks:
    - last_event_id
    - event_status
    - timestamp of last status change
    - unresolved flag
    """
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self._lock = threading.Lock()

        # Default state
        self.node_id: Optional[str] = None
        self.last_event_id: Optional[str] = None
        self.event_status: Status = Status.UNKNOWN
        self.last_timestamp: float = 0.0
        self.unresolved: bool = False

        # Attempt to load existing state
        self._load()

    def _load(self) -> None:
        """Loads state from file if it exists."""
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, 'rb') as f:
                data = pickle.load(f)
            with self._lock:
                self.node_id        = data.get('node_id')
                self.last_event_id = data.get('last_event_id')
                self.event_status = Status(data.get('event_status', Status.UNKNOWN.value))
                self.last_timestamp = data.get('last_timestamp', 0.0)
                self.unresolved = data.get('unresolved', False)
                logger.info(
                f"Loaded state from {self.filepath}: "
                f"node_id={self.node_id}, "
                f"last_event_id={self.last_event_id}, "
                f"unresolved={self.unresolved}, "
                f"last_timestamp={self.last_timestamp}"
                )
        except Exception as e:
            logger.error(f"Failed to load state: {e}", exc_info=True)

    def _save(self) -> None:
        """Saves state to file."""
        try:
            os.makedirs(os.path.dirname(self.filepath) or '.', exist_ok=True)
            with open(self.filepath, 'wb') as f:
                data = {
                    'node_id':        self.node_id,
                    'last_event_id': self.last_event_id,
                    'event_status': self.event_status.value,
                    'last_timestamp': self.last_timestamp,
                    'unresolved': self.unresolved
                }
                pickle.dump(data, f)
            logger.debug(f"State saved to {self.filepath}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}", exc_info=True)
            
    def mark_node_id(self, node_id: str) -> None:
        """Persist a newly assigned node_id."""
        with self._lock:
            self.node_id = node_id
        self._save()
        logger.info(f"State updated: node_id={node_id}")
        
    def mark_reported(self, event_id: str) -> None:
        """Marks a new accident event as reported (unresolved)."""
        with self._lock:
            self.last_event_id = event_id
            self.event_status = Status.REPORTED
            self.last_timestamp = time.time()
            self.unresolved = True
        self._save()
        logger.info(f"State updated: reported {event_id}")

    def mark_validated(self) -> None:
        """Marks the current event as validated."""
        with self._lock:
            self.event_status = Status.VALIDATED
            self.last_timestamp = time.time()
        self._save()
        logger.info("State updated: validated")

    def mark_invalid(self) -> None:
        """Marks the current event as invalid and resolves it."""
        with self._lock:
            self.event_status = Status.INVALID
            self.last_timestamp = time.time()
            self.unresolved = False
        self._save()
        logger.info("State updated: invalid (resolved)")
        
    def mark_resolved(self) -> None:
        """Marks the current event as resolved."""
        with self._lock:
            self.event_status   = Status.RESOLVED
            self.last_timestamp = time.time()
            self.unresolved     = False
        self._save()
        logger.info("State updated: resolved")

    def clear_unresolved(self) -> None:
        """Clears the unresolved flag after resolution."""
        with self._lock:
            self.unresolved = False
        self._save()
        logger.info("State updated: cleared unresolved flag")

    def is_unresolved(self) -> bool:
        """Returns True if there's an unresolved accident event."""
        with self._lock:
            return self.unresolved

    def is_in_cooldown(self, cooldown: float) -> bool:
        """
        Checks if we are within the post-validation cooldown period.
        Returns True if last status was VALIDATED and (now - last_timestamp) < cooldown
        """
        with self._lock:
            return (
                self.event_status == Status.VALIDATED and
                (time.time() - self.last_timestamp) < cooldown
            )

    def has_cooldown_elapsed(self, cooldown: float) -> bool:
        """
        Checks if the post-validation cooldown has elapsed.
        Returns True if last status was VALIDATED and (now - last_timestamp) >= cooldown
        """
        with self._lock:
            return (
                self.event_status == Status.VALIDATED and
                (time.time() - self.last_timestamp) >= cooldown
            )
