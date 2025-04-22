import sys
import time
import logging
import threading
import concurrent.futures
import queue
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any, Dict

from .config import Config
from .state import SystemState, Status
from .api_client import APIClient
from .model_manager import ModelManager
from .image_processor import ImageProcessor
from .camera_manager import CameraManager

logger = logging.getLogger("accident_detector")

@dataclass(frozen=True)
class PerformanceConfig:
    """
    Holds all timing and performance-related configuration.
    """
    frame_queue_size: int
    frame_capture_interval: float
    reported_check_interval: int
    accident_cooldown: int
    heartbeat_interval: int
    accident_confidence_threshold: float
    required_consecutive_frames: int
    thread_pool_size: int

class AccidentDetectionSystem:
    """
    Orchestrates camera capture, image processing, model inference,
    accident reporting, and status polling.
    """
    def __init__(
        self,
        debug: bool = False
    ):
        self.config = Config()
        self.debug = debug or self.config.getboolean("System", "DebugMode")

        # Load performance settings once (no fallback values)
        self.perf = PerformanceConfig(
            frame_queue_size=self.config.getint("Performance", "FrameQueueSize"),
            frame_capture_interval=(0.05 if self.debug else 
                                     self.config.getfloat("Performance", "FrameCaptureInterval")),
            reported_check_interval=self.config.getint("Performance", "ReportedCheckInterval"),
            accident_cooldown=(10 if self.debug else 
                               self.config.getint("Performance", "AccidentCooldown")),
            heartbeat_interval=(100 if self.debug else 
                                self.config.getint("System", "HeartbeatInterval")),
            accident_confidence_threshold=self.config.getfloat(
                "Detection", "AccidentConfidenceThreshold"
            ),
            required_consecutive_frames=self.config.getint(
                "Detection", "RequiredConsecutiveFrames"
            ),
            thread_pool_size=self.config.getint("System", "ThreadPoolSize")
        )

        # Core components
        self.state = SystemState(self.config.get("System", "StateFile"))
        # if we already have a node_id saved, reuse it
        if saved := self.state.node_id:
            self.config.set("Node", "ID", saved)
            logger.info(f"Reusing saved node_id={saved}; skipping registration")
        # otherwise registration will happen in start()
        
        self.api_client = APIClient(self.config, debug=self.debug)
        self.model_manager = ModelManager(self.config)
        self.image_processor = ImageProcessor(self.config)
        self.camera_manager = CameraManager(self.config)

        # Concurrency primitives
        self.shutdown_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=self.perf.frame_queue_size)
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.perf.thread_pool_size
        )
        self.threads: Dict[str, threading.Thread] = {}

        if self.debug:
            logger.info(
                f"Debug Mode timings: capture={self.perf.frame_capture_interval}s, "
                f"cooldown={self.perf.accident_cooldown}s, heartbeat={self.perf.heartbeat_interval}s"
            )

    def get_node_info(self) -> Dict[str, Any]:
        return {
            "node_status": "active",
            "node_name": self.config.get("Node", "Name"),
            "node_id": self.config.get("Node", "ID"),
            "latitude": self.config.getfloat("Node", "Latitude"),
            "longitude": self.config.getfloat("Node", "Longitude"),
        }

    def register_node(self) -> bool:
        return self.api_client.register_node(self.get_node_info())

    def start(self) -> bool:
        logger.info("Starting AccidentDetectionSystem")
        if not self.model_manager.download_model():
            logger.error("Model download failed")
            return False

        if not self.state.node_id:
            # first run: register
            if not (rid := self.api_client.register_node(self.get_node_info())) and not self.debug:
                logger.error("Node registration failed")
                return False
            # capture the newly‑assigned ID
            assigned = self.config.get("Node", "ID")
            self.state.mark_node_id(assigned)
        else:
            # already in config & state
            logger.debug("Node registration skipped (node_id already set)")


        # launch core loops
        for name, target in (
            ("video",      self._video_loop),
            ("processing", self._processing_loop),
            ("heartbeat",  self._heartbeat_loop),
            ("monitor",    self._monitor_loop)
        ):
            self._start_thread(name, target)

        logger.info("All threads started")

        # resume any in-flight event 
        eid = self.state.last_event_id
        if eid and (self.state.is_unresolved() or
                    self.state.is_in_cooldown(self.perf.accident_cooldown)):
            logger.info(f"Resuming monitor for previous event {eid}")
            # pool it so it's not part of self.threads
            self.thread_pool.submit(self._poll_event_status, eid)

        return True

    def run(self) -> None:
        """
        Blocks until shutdown; logs uptime periodically.
        """
        if not self.start():
            sys.exit(1)

        start_time = time.time()
        try:
            while not self.shutdown_event.is_set():
                uptime_hours = (time.time() - start_time) / 3600
                if int(uptime_hours) and uptime_hours.is_integer():
                    logger.info(f"System uptime: {uptime_hours:.0f}h")
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt caught, shutting down")
            self.shutdown()

    def shutdown(self) -> None:
        """Initiate graceful shutdown of all threads and resources."""
        logger.info("Shutdown initiated")
        self.shutdown_event.set()

        # Wait for threads to exit
        for name, thread in self.threads.items():
            thread.join(timeout=2)
            if thread.is_alive():
                logger.warning(f"Thread '{name}' did not exit cleanly")

        self.thread_pool.shutdown(wait=False)
        self.camera_manager.release()
        if self.debug:
            import cv2
            cv2.destroyAllWindows()

        logger.info("Shutdown complete")

    # --- Thread Starters ---
    def _start_thread(self, name: str, target: callable) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self.threads[name] = thread
        logger.debug(f"Thread '{name}' started")

    # --- Worker Loops ---
    def _heartbeat_loop(self) -> None:
        logger.info("Heartbeat thread running")
        interval = self.perf.heartbeat_interval
        while not self.shutdown_event.is_set():
            self.api_client.send_heartbeat({"node_id": self.config.get("Node", "ID")})
            self.shutdown_event.wait(interval)
        logger.info("Heartbeat thread exiting")

    def _video_loop(self) -> None:
        logger.info("Video capture thread running")
        if not self.camera_manager.initialize():
            logger.error("CameraManager initialization failed")
            return

        interval = self.perf.frame_capture_interval
        try:
            while not self.shutdown_event.is_set():
                if self.shutdown_event.wait(interval):
                    break

                ret, frame = self.camera_manager.read_frame()
                if not ret:
                    self.camera_manager.release()
                    self.camera_manager.initialize()
                    continue

                if self.image_processor.detect_motion(frame):
                    try:
                        self.frame_queue.put(frame, block=False)
                    except queue.Full:
                        _ = self.frame_queue.get()
                        self.frame_queue.put(frame)
        finally:
            self.camera_manager.release()
            logger.info("Video capture thread exiting")

    def _processing_loop(self) -> None:
        logger.info("Frame processing thread running")
        if not self.model_manager.load_model():
            logger.error("Model load failed")
            return

        consecutive = 0
        while not self.shutdown_event.is_set():
            # Skip if unresolved or in cooldown
            if self.state.is_unresolved():
                self.shutdown_event.wait(1)
                continue
            if self.state.is_in_cooldown(self.perf.accident_cooldown):
                self.shutdown_event.wait(1)
                continue

            try:
                frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            buffer, resized = self.image_processor.compress(frame)
            pred, conf = self.model_manager.predict(resized)
            logger.debug(f"Prediction={pred} conf={conf:.2f}")

            if pred == "accident" and conf >= self.perf.accident_confidence_threshold:
                consecutive += 1
                if consecutive >= self.perf.required_consecutive_frames:
                    self._report_and_monitor(buffer)
                    consecutive = 0
            else:
                consecutive = 0

            self.frame_queue.task_done()
        logger.info("Frame processing thread exiting")

    def _monitor_loop(self) -> None:
        logger.info("Monitor thread running")
        while not self.shutdown_event.is_set():
            for name, thread in list(self.threads.items()):
                if not thread.is_alive():
                    logger.warning(f"Thread '{name}' died, restarting")
                    target = getattr(self, f"_{name}_loop", None)
                    if target:
                        self._start_thread(name, target)
            self.shutdown_event.wait(2)
        logger.info("Monitor thread exiting")

    # --- Accident Reporting ---
    def _report_and_monitor(self, buffer: bytes) -> None:
        """
        Reports an accident and polls its status until resolution.
        """
        try:
            event_id = self._report_event(buffer)
            if not event_id:
                return
            self.state.mark_reported(event_id)
            self._poll_event_status(event_id)
        except Exception as e:
            logger.error("Error in report_and_monitor", exc_info=True)
            self.state.clear_unresolved()

    def _report_event(self, buffer: bytes) -> Optional[str]:
        result = self.api_client.send_accident_event({"image": buffer})
        if result.get("success") and (eid := result.get("event_id")):
            logger.info(f"Event reported: {eid}")
            return eid
        logger.error(f"Failed to report event: {result}")
        return None

    def _poll_event_status(self, event_id: str) -> None:
        """
        Polls the API for event status and handles:
          1) initial REPORT → wait for VALIDATED / INVALID / RESOLVED
          2) if VALIDATED, enter cooldown loop (re‑polling)
          3) on INVALID or RESOLVED at any time, mark and bring node online
          4) if cooldown elapses with no invalidation, auto‑resolve remotely
        """
        # ---- phase 1: wait for VALIDATED / INVALID / RESOLVED ----
        while not self.shutdown_event.is_set():
            status_str = self.api_client.check_accident_status(event_id)
            logger.info(f"Event {event_id} status: {status_str}")

            if status_str == Status.REPORTED.value:
                self.shutdown_event.wait(self.perf.reported_check_interval)
                continue

            if status_str == Status.INVALID.value:
                # immediate resolution
                self.state.mark_invalid()
                self.api_client.update_node_status("online")
                return

            if status_str == Status.RESOLVED.value:
                # someone already marked it resolved
                self.state.mark_resolved()
                self.api_client.update_node_status("online")
                return

            if status_str == Status.VALIDATED.value:
                # move into cooldown phase
                self.state.mark_validated()
                break

            # unknown / error → retry
            logger.error(f"Unexpected status '{status_str}'")
            self.shutdown_event.wait(self.perf.reported_check_interval)

        # ---- phase 2: cooldown + re‑poll loop ----
        cooldown = self.perf.accident_cooldown
        start    = time.time()

        while not self.shutdown_event.is_set():
            elapsed = time.time() - start
            if elapsed >= cooldown:
                # cooldown expired without invalidation → auto-resolve
                break

            # re‑poll remote status in the meantime
            status_str = self.api_client.check_accident_status(event_id)
            logger.info(f"[Cooldown] Event {event_id} status: {status_str}")

            if status_str == Status.INVALID.value:
                self.state.mark_invalid()
                self.api_client.update_node_status("online")
                return

            if status_str == Status.RESOLVED.value:
                self.state.mark_resolved()
                self.api_client.update_node_status("online")
                return

            # still validated (or some other transition) → keep waiting
            if status_str != Status.VALIDATED.value:
                logger.warning(f"Status changed to '{status_str}' during cooldown")

            self.shutdown_event.wait(self.perf.reported_check_interval)

        # ---- phase 3: cooldown elapsed → auto‑resolve remotely & locally ----
        # 1) tell backend we're resolved
        self.api_client.update_event_status(event_id, Status.RESOLVED.value)
        # 2) update our local state
        self.state.mark_resolved()
        # 3) bring ourselves back online
        self.api_client.update_node_status("online")
