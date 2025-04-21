"""
api_client.py

Encapsulates all HTTP communication with the backend:
- Node registration
- Heartbeats
- Accident event reporting
- Accident status polling
- Node status updates
"""
import json
import logging
from typing import Any, Dict, Optional, TypedDict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config

logger = logging.getLogger("accident_detector")

class ApiError(Exception):
    """Generic exception for API-related errors."""
    pass

class SendEventResponse(TypedDict):
    success: bool
    event_id: Optional[str]

class APIClient:
    """
    HTTP client with built-in retry logic for interacting with the accident-detection backend.
    """
    def __init__(self, config: Config, debug: bool = False) -> None:
        self.debug = debug
        self.config = config
        self.base_url = config.get("API", "BaseURL")
        self.timeout = config.getint("API", "Timeout")

        # Prepare Session with retries
        retries = Retry(
            total=self.config.getint("API", "RetryAttempts"),
            backoff_factor=self.config.getfloat("API", "RetryBackoffFactor"),
            status_forcelist=[500, 502, 503, 504]
        )
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Endpoint URLs
        self.register_url = f"{self.base_url}edge-node"
        self.heartbeat_url = f"{self.base_url}heartbeat"
        self.event_url = f"{self.base_url}event"
        self.status_url = f"{self.base_url}event?event_id="

    def register_node(self, node_info: Dict[str, Any]) -> bool:
        """
        Register the edge node. On success, stores new node ID in config.
        """
        if self.debug:
            logger.info(f"[DEBUG] Register node -> {self.register_url}: {node_info}")
            simulated_id = "simulated-node-id"
            self.config.set("Node", "ID", simulated_id)
            return True

        try:
            resp = self.session.post(
                self.register_url,
                json=node_info,
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            node_id = data.get("node_id")
            if not node_id:
                logger.error("register_node: 'node_id' missing in response")
                return False
            self.config.set("Node", "ID", node_id)
            logger.info(f"Node registered (ID={node_id})")
            return True
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"register_node failed: {e}")
            return False

    def send_heartbeat(self, node_info: Dict[str, Any]) -> bool:
        """
        Send a heartbeat to keep the node marked as active.
        """
        if self.debug:
            logger.info(f"[DEBUG] Heartbeat -> {self.heartbeat_url}: {node_info}")
            return True

        try:
            resp = self.session.put(
                self.heartbeat_url,
                json=node_info,
                timeout=self.timeout
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"send_heartbeat failed: {e}")
            return False
        
    def update_node_status(self, status: str) -> bool:
        """
        Update this node’s status (e.g. 'online', 'offline', etc.)
        by POSTing to the edge-node endpoint.
        """
        node_id = self.config.get("Node", "ID")
        payload = {"node_id": node_id, "node_status": status}

        if self.debug:
            logger.info(f"[DEBUG] update_node_status -> {self.register_url}: {payload}")
            return True

        try:
            resp = self.session.post(
                self.register_url,
                json=payload,
                timeout=self.timeout
            )
            resp.raise_for_status()
            logger.info(f"Node status updated to '{status}' for node_id={node_id}")
            return True

        except requests.RequestException as e:
            logger.error(f"update_node_status failed: {e}")
            return False
    
    def send_accident_event(self, event_data: Dict[str, Any]) -> SendEventResponse:
        """
        Report an accident event. Returns a dict indicating success and event_id.
        """
        if self.debug:
            eid = "simulated-event-id"
            # record when we “reported” this event
            logger.info(f"[DEBUG] send_accident_event -> {self.event_url}: {event_data}")
            return {"success": True, "event_id": eid}

        headers = {"Content-Type": "application/json"}
        try:
            resp = self.session.post(
                self.event_url,
                json=event_data,
                headers=headers,
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            eid = data.get("event_id")
            if not eid:
                logger.error("send_accident_event: 'event_id' missing in response")
                return {"success": False, "event_id": None}
            logger.info(f"Accident event sent (event_id={eid})")
            return {"success": True, "event_id": eid}
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"send_accident_event failed: {e}")
            return {"success": False, "event_id": None}

    def check_accident_status(self, event_id: str) -> str:
        """
        Polls the backend once for the status of a given event_id.
        Returns one of: 'reported', 'validated', 'invalid', or 'unknown'.
        """
        if self.debug:
            return "validated"

        try:
            resp = self.session.get(
                f"{self.status_url}{event_id}",
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("event_status", "unknown")
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"check_accident_status failed: {e}")
            return "unknown"
