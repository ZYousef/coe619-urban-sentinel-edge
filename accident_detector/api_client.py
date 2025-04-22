"""
api_client.py

Encapsulates all HTTP communication with the backend:
- Node registration
- Heartbeats
- Accident event reporting (base64-encoded images)
- Accident status polling
- Node status updates
"""
import json
import logging
import base64
import time
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
            read=self.config.getint("API", "RetryAttempts"),
            backoff_factor=self.config.getfloat("API", "RetryBackoffFactor"),
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
            respect_retry_after_header=True,
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
        by POSTing to the edge-node endpoint with the full node info.
        """
        # start from your full registration payload
        payload = {
            "node_id":   self.config.get("Node", "ID"),
            "node_name": self.config.get("Node", "Name"),
            "latitude":  self.config.getfloat("Node", "Latitude"),
            "longitude": self.config.getfloat("Node", "Longitude"),
            "node_status": status
        }

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
            logger.info(f"Node status updated to '{status}' for node_id={payload['node_id']}")
            return True

        except requests.RequestException as e:
            logger.error(f"update_node_status failed: {e}")
            return False
    
    def send_accident_event(self, event_data: Dict[str, Any]) -> SendEventResponse:
        """
        Report an accident event. Builds a full payload including node metadata and base64-encoded image,
        logs backend error bodies on HTTP 4xx/5xx, and returns success/event_id.
        """
        # Always include node info and timestamp
        payload: Dict[str, Any] = {
            "node_id": self.config.get("Node", "ID"),
            "latitude": float(self.config.get("Node", "Latitude")),
            "longitude": float(self.config.get("Node", "Longitude")),
            "event_timestamp": int(time.time()),
            "event_type": "accident",
            "event_status": "reported",
        }
        img = event_data.get("image")
        if isinstance(img, (bytes, bytearray)):
            payload["image"] = base64.b64encode(img).decode('ascii')
        else:
            logger.error("send_accident_event: missing image bytes in event_data")
            return {"success": False, "event_id": None}

        headers = {"Content-Type": "application/json"}
        try:
            resp = self.session.post(
                self.event_url,
                json=payload,
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
        except requests.HTTPError as e:
            # Log full response body for debugging 400 errors
            logger.error(f"send_accident_event failed {resp.status_code}: {resp.text}")
            return {"success": False, "event_id": None}
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"send_accident_event failed: {e}")
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
        
    def update_event_status(self, event_id: str, status: str) -> bool:
        """
        Update an existing event’s status by PUTting to /event.
        """
        payload = {
            "event_id": event_id,
            "event_status": status
        }

        if self.debug:
            logger.info(f"[DEBUG] update_event_status -> {self.event_url}: {payload}")
            return True

        try:
            resp = self.session.put(
                self.event_url,
                json=payload,
                timeout=self.timeout
            )
            resp.raise_for_status()
            logger.info(f"Event status updated to '{status}' for event_id={event_id}")
            return True

        except requests.RequestException as e:
            # Try to capture response body for debugging
            body = resp.text if 'resp' in locals() else None
            logger.error(
                f"update_event_status failed: {e}"
                + (f" — response body: {body!r}" if body else "")
            )
            return False
