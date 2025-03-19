"""
api_client.py

Contains the APIClient class, which encapsulates communication
with remote services (register node, send events, etc.).
"""

import json
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("accident_detector")

class APIClient:
    """
    Handles all API interactions for node registration, heartbeats,
    accident event reporting, and checking accident resolution.
    """
    def __init__(self, config, debug=False):
        self.debug = debug
        self.config = config  
        self.base_url = config.get("API", "BaseUrl")
        self.timeout = config.getint("API", "Timeout", 5)
        self.retry_attempts = config.getint("API", "RetryAttempts", 5)
        self.retry_backoff_factor = config.getfloat("API", "RetryBackoffFactor", 1.0)
        self.session = requests.Session()

        # Configure retries
        retries = Retry(
            total=self.retry_attempts,
            backoff_factor=self.retry_backoff_factor,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        # Endpoints
        self.register_node_url = f"{self.base_url}edge-node"
        self.accident_event_url = f"{self.base_url}event"
        self.accident_check_url = f"{self.base_url}event?event_id="
        self.heartbeat_url = f"{self.base_url}heartbeat"

    def register_node(self, node_info):
        """Registers the node with the backend and updates node_id from the registration response, and updates config with the new node_id."""
        if self.debug:
            logger.info(f"Debug Mode - Simulated API Call: POST {self.register_node_url} with data: {json.dumps(node_info)}")
            simulated_node_id = "simulated-node-id"
            self.config.set('Node', 'ID', simulated_node_id)
            return {"success": True, "node_id": simulated_node_id}
        try:
            response = self.session.post(self.register_node_url, json=node_info, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            node_id = data.get("node_id", None)
            if node_id:
                logger.info(f"Node registered successfully with node_id: {node_id}")
                self.config.set('Node', 'ID', node_id)
                return {"success": True, "node_id": node_id}
            else:
                logger.error("Node registration failed: node_id not found in the response")
                return {"success": False, "node_id": None}
        except requests.exceptions.RequestException as e:
            logger.error(f"Node registration failed: {e}")
            return {"success": False, "node_id": None}

    def send_heartbeat(self, node_info):
        """Sends periodic heartbeats to indicate the node is alive."""
        if self.debug:
            logger.info(f"Debug Mode - Simulated API Call: POST {self.heartbeat_url} with data: {json.dumps(node_info)}")
            return True
        try:
            response = self.session.post(self.heartbeat_url, json=node_info, timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False

    def send_accident_event(self, event_data):
        """Reports an accident event with required fields and an optional image."""
        headers = {"Content-Type": "application/json"}
        if self.debug:
            # Safely handle missing image field
            payload_size = len(event_data.get("image", "")) / 1024
            logger.info(f"Debug Mode - Simulated API Call: POST {self.accident_event_url} (size: {payload_size:.2f} KB)")
            return True
        # Safely handle missing image field
        payload_size = len(event_data.get("image", "")) / 1024
        logger.info(f"Sending accident report, size: {payload_size:.2f} KB")
        try:
            response = self.session.post(
                self.accident_event_url,
                json=event_data,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info("Accident reported successfully")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send accident event: {e}")
            return False

    def check_accident_resolved(self, check_interval=10, max_interval=60, backoff_factor=1.5, shutdown_event=None):
        """
        Polls the backend to see if the accident has been resolved.
        Uses exponential backoff between requests, up to max_interval.
        If 'shutdown_event' is set, exit early if signaled.
        """
        if self.debug:
            logger.info(f"Debug Mode - Simulated API Call: GET {self.accident_check_url}")
            return True
        interval = check_interval
        while True:
            if shutdown_event and shutdown_event.is_set():
                logger.info("Shutdown requested while waiting for accident resolution")
                return False
            try:
                response = self.session.get(self.accident_check_url, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                if data.get("resolved", False):
                    logger.info("Accident marked as resolved by central system")
                    return True
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to check accident status: {e}")
            if shutdown_event:
                if shutdown_event.wait(interval):
                    return False
            else:
                time.sleep(interval)
            interval = min(interval * backoff_factor, max_interval)
