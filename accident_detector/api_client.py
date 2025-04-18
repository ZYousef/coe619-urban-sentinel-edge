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
        """Sends periodic heartbeats to indicate the node is alive using PUT instead of POST."""
        if self.debug:
            logger.info(f"Debug Mode - Simulated API Call: PUT {self.heartbeat_url} with data: {json.dumps(node_info)}")
            return True
        try:
            response = self.session.put(self.heartbeat_url, json=node_info, timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False

    def send_accident_event(self, event_data):
        """Reports an accident event with required fields and an optional image."""
        headers = {"Content-Type": "application/json"}
        if self.debug:
            logger.info(f"Debug Mode - Simulated API Call: POST {self.accident_event_url}")
            # Simulating an event_id generation in debug mode
            return {"success": True, "event_id": "simulated-event-id"}
        try:
            response = self.session.post(
                self.accident_event_url,
                json=event_data,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            event_id = data.get("event_id", None)
            if event_id:
                logger.info(f"Accident reported successfully with event_id: {event_id}")
                return {"success": True, "event_id": event_id}
            else:
                logger.error("Failed to obtain event_id from the response")
                return {"success": False, "event_id": None}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send accident event: {e}")
            return {"success": False, "event_id": None}

    def check_accident_resolved(self, event_id):
            """
            Queries the backend once to check if the accident is resolved based on event_id.
            Returns True if validated, False otherwise.
            """
            if not event_id:
                logger.error("No event_id provided to check accident resolution")
                return False

            try:
                response = self.session.get(f"{self.accident_check_url}{event_id}", timeout=self.config.getint('API', 'Timeout', 10))
                response.raise_for_status()
                data = response.json()
                event_status = data.get("event_status", "unknown")
                logger.info(f"Checked accident status for event_id {event_id}: '{event_status}'")
                return event_status == "validated"
            except requests.exceptions.RequestException as e:
                logger.error(f"Error while checking accident status: {e}")
                return False