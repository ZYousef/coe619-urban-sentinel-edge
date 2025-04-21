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
        """
        Downloads model, registers node, and starts all worker threads.
        """
        logger.info("Starting AccidentDetectionSystem")
        if not self.model_manager.download_model():
            logger.error("Model download failed")
            return False

        if not (self.register_node() or self.debug):
            logger.error("Node registration failed")
            return False

        # Launch threads
        for name, target in (
            ("video", self._video_loop),
            ("processing", self._processing_loop),
            ("heartbeat", self._heartbeat_loop),
            ("monitor", self._monitor_loop)
        ):
            self._start_thread(name, target)

        logger.info("All threads started")
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
        Polls the API for event status and handles transitions.
        """
        start_validated: Optional[float] = None
        while not self.shutdown_event.is_set():
            status_str = self.api_client.check_accident_status(event_id)
            try:
                status = Status(status_str)
            except ValueError:
                status = Status.UNKNOWN

            logger.info(f"Event {event_id} status: {status.value}")

            if status == Status.REPORTED:
                self.shutdown_event.wait(self.perf.reported_check_interval)
                continue
            if status == Status.VALIDATED:
                self.state.mark_validated()
                # now block here while state.is_in_cooldown remains True
                while self.state.is_in_cooldown(self.perf.accident_cooldown):
                    self.shutdown_event.wait(min(60, self.perf.accident_cooldown))
                # as soon as that returns False, we know the cooldown elapsed
                self.api_client.update_node_status("online")
                self.state.clear_unresolved()
                break
            if status == Status.INVALID:
                self.state.mark_invalid()
                break

            # Unknown or error, retry
            logger.error(f"Unexpected status '{status_str}'")
            self.shutdown_event.wait(self.perf.reported_check_interval)

        if self.shutdown_event.is_set():
            self.state.clear_unresolved()
