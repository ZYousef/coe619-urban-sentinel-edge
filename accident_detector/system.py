"""
system.py

Defines the main AccidentDetectionSystem class, which orchestrates all
the components (camera, model, API client, etc.). It starts threads for
video capture, frame processing, heartbeat, and monitoring.
"""

import os
import sys
import cv2
import time
import base64
import json
import queue
import threading
import concurrent.futures
import logging
from queue import Empty
from fastai.vision.all import PILImage

# Relative imports from our package modules
from .config import Config
from .state import SystemState
from .api_client import APIClient
from .model_manager import ModelManager
from .image_processor import ImageProcessor
from .camera_manager import CameraManager

logger = logging.getLogger("accident_detector")

class AccidentDetectionSystem:
    """
    High-level system manager that initializes all modules, starts worker
    threads, polls frames, runs inference, sends events, and coordinates
    shutdown logic.
    """
    def __init__(self, debug=False):
        self.config = Config()
        self.debug = debug or self.config.getboolean("System", "DebugMode", False)

        self.state = SystemState(self.config.get("System", "StateFile"))
        self.api_client = APIClient(self.config, debug=self.debug)
        self.model_manager = ModelManager(self.config)
        self.image_processor = ImageProcessor(self.config)
        self.camera_manager = CameraManager(self.config)

        self.frame_queue_size = self.config.getint("Performance", "FrameQueueSize", 5)
        self.frame_capture_interval = 0.05 if self.debug else self.config.getfloat("Performance", "FrameCaptureInterval", 0.1)
        self.accident_cooldown = 10 if self.debug else self.config.getint("Performance", "AccidentCooldown", 1800)
        self.heartbeat_interval = 100 if self.debug else self.config.getint("System", "HeartbeatInterval", 60)

        self.accident_confidence_threshold = self.config.getfloat("Detection", "AccidentConfidenceThreshold", 0.7)
        self.required_consecutive_frames = self.config.getint("Detection", "RequiredConsecutiveFrames", 2)
        self.thread_pool_size = self.config.getint("System", "ThreadPoolSize", 2)

        self.shutdown_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=self.frame_queue_size)
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_pool_size)
        self.threads = {}

        if self.debug:
            logger.info(
                f"Debug Mode: Adjusted timings - Heartbeat: {self.heartbeat_interval}s, "
                f"Cooldown: {self.accident_cooldown}s, Frame Interval: {self.frame_capture_interval}s"
            )

    def get_node_info(self):
        """Returns a dict containing basic node data for API calls."""
        return {
            "node_status": "active",
            "node_name": self.config.get("Node", "Name"),
            "node_id": self.config.get("Node", "ID"),
            "latitude": self.config.getfloat("Node", "Latitude"),
            "longitude": self.config.getfloat("Node", "Longitude")
        }

    def register_node(self):
        """Registers this node with the remote API."""
        return self.api_client.register_node(self.get_node_info())

    def heartbeat_worker(self):
        """
        Periodically sends heartbeats to the remote API while the system
        is running. Exits when the shutdown_event is triggered.
        """
        logger.info("Starting heartbeat thread")
        while not self.shutdown_event.is_set():
            node_info = {
            "node_id": self.config.get("Node", "ID"),
        }
            self.api_client.send_heartbeat(node_info)
            if self.shutdown_event.wait(self.heartbeat_interval):
                break
        logger.info("Heartbeat thread exiting")

    def send_accident_event(self, buffer, frame=None):
        """
        Sends an accident event (and image) to the remote API based on Postman specification.
        In debug mode, it shows the text overlay on the local frame window.
        """
        if self.debug:
            try:
                image_base64 = base64.b64encode(buffer).decode('utf-8')
                event_data = {
                    "event_type": "car accident",
                    "edge_node_id": self.config.get("Node", "ID"),
                    "event_timestamp": str(int(time.time())),  # Stringified UNIX timestamp
                    "event_status": "reported",
                    "latitude": self.config.getfloat("Node", "Latitude"),
                    "longitude": self.config.getfloat("Node", "Longitude"),
                    "image": "/9j/4AAQSkZJRg..."
                }
                payload_size = len(event_data["image"]) / 1024
                logger.info(
                    f"Debug Mode - Simulated API Call (size: {payload_size:.2f} KB): "
                    f"{json.dumps(event_data, indent=2)}"
                )

                # Optional local display
                if frame is not None:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    cv2.putText(frame, f"Accident Detected - {timestamp}",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    # cv2.imshow("Accident Detection Debug", frame)
                    # if cv2.waitKey(1) & 0xFF == ord('q'):
                    #     sys.exit(0)

                self.state.update_accident_state()
            except Exception as e:
                logger.error(f"Debug mode display error: {e}")
        else:
            # Production mode: actually POST to the remote API
            try:
                image_base64 = base64.b64encode(buffer).decode('utf-8')
                event_data = {
                    "event_type": "car accident",
                    "edge_node_id": self.config.get("Node", "ID"),
                    "event_timestamp": str(int(time.time())),  # Stringified UNIX timestamp
                    "event_status": "reported",
                    "latitude": self.config.getfloat("Node", "Latitude"),
                    "longitude": self.config.getfloat("Node", "Longitude"),
                    "image": image_base64
                }
                if self.api_client.send_accident_event(event_data):
                    self.state.update_accident_state()
                    logger.info("Accident reported and state updated. Waiting for resolution...")
                    self.api_client.check_accident_resolved(shutdown_event=self.shutdown_event)
            except Exception as e:
                logger.error(f"Error preparing accident report: {e}")

    def process_video(self):
        """
        Runs in a dedicated thread: captures frames from CameraManager,
        checks for motion, and (if motion is detected) adds frames to
        a processing queue.
        """
        logger.info("Starting video capture thread")
        if not self.camera_manager.initialize():
            logger.error("Failed to initialize camera, exiting video thread")
            return

        frame_count = 0
        last_frame_time = time.time()
        try:
            while not self.shutdown_event.is_set():
                current_time = time.time()
                elapsed = current_time - last_frame_time
                if elapsed < self.frame_capture_interval:
                    time.sleep(self.frame_capture_interval - elapsed)
                last_frame_time = time.time()

                ret, frame = self.camera_manager.read_frame()
                if not ret:
                    # If it's a file-based source, loop back
                    self.camera_manager.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    if not self.camera_manager.initialize():
                        logger.error("Failed to reinitialize camera after failure")
                        time.sleep(5)
                    continue

                frame_count += 1
                # For speed, only run motion detection every N frames
                if frame_count % 3 == 0:
                    if self.image_processor.detect_motion(frame):
                        try:
                            if not self.frame_queue.full():
                                self.frame_queue.put_nowait(frame)
                                logger.debug("Added frame to processing queue")
                            else:
                                # If queue is full, remove one before adding
                                try:
                                    self.frame_queue.get_nowait()
                                    self.frame_queue.put_nowait(frame)
                                    logger.debug("Queue full, replaced oldest frame")
                                except queue.Empty:
                                    logger.warning("Queue state changed unexpectedly")
                        except queue.Full:
                            logger.warning("Frame queue full, dropping frame")
        finally:
            self.camera_manager.release()

    def process_frames(self):
        """
        Runs in a dedicated thread: fetches frames from the frame_queue,
        compresses them, runs a model prediction, and if an accident is
        detected in multiple consecutive frames, sends an event.
        """
        logger.info("Starting frame processing thread")
        if not self.model_manager.load_model():
            logger.error("Cannot start processing thread - model failed to load")
            return

        consecutive_accident_frames = 0
        last_processed_time = 0

        while not self.shutdown_event.is_set():
            if self.state.is_in_cooldown(self.accident_cooldown):
                remaining = int(self.accident_cooldown - (time.time() - self.state.last_accident_time))
                logger.debug(f"In cooldown period, {remaining} seconds remaining")
                if self.shutdown_event.wait(5 if not self.debug else 1):
                    break
                continue

            try:
                frame = self.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            current_time = time.time()
            # Throttle processing if we just did a frame
            if current_time - last_processed_time < 0.2:
                self.frame_queue.task_done()
                continue
            last_processed_time = current_time

            try:
                # Compress the frame in a thread-pool future
                future = self.thread_pool.submit(self.image_processor.compress_image, frame)
                buffer, resized_frame = future.result(timeout=2)

                # Make a PILImage for the fastai model
                img = PILImage.create(resized_frame)
                prediction, confidence = self.model_manager.predict(img)
                logger.debug(f"Prediction: {prediction} (confidence: {confidence:.2f})")

                # Optional debug visualization
                if self.debug:
                    display_frame = frame.copy()
                    text = f"{prediction}: {confidence:.2f}"
                    color = (0, 255, 0) if prediction != "accident" else (0, 0, 255)
                    cv2.putText(display_frame, text, (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    # cv2.imshow("Accident Detection Debug", display_frame)
                    # if cv2.waitKey(1) & 0xFF == ord('q'):
                    #     sys.exit(0)

                # Check if prediction is "accident" above threshold
                if prediction == "accident" and confidence > self.accident_confidence_threshold:
                    consecutive_accident_frames += 1
                    logger.info(
                        f"Potential accident detected ({consecutive_accident_frames}/"
                        f"{self.required_consecutive_frames}) with confidence {confidence:.2f}"
                    )
                    if consecutive_accident_frames >= self.required_consecutive_frames:
                        logger.warning(
                            f"Accident confirmed after {self.required_consecutive_frames} consecutive detections!"
                        )
                        self.send_accident_event(buffer, frame if self.debug else None)
                        consecutive_accident_frames = 0
                else:
                    # Slightly reduce consecutive count if this frame is not "accident"
                    consecutive_accident_frames = max(0, consecutive_accident_frames - 1)

                self.frame_queue.task_done()

            except Exception as e:
                logger.error(f"Error processing frame: {e}")
                self.frame_queue.task_done()
                time.sleep(0.5)

    def monitor_threads(self):
        """
        Runs in a dedicated thread: periodically checks if worker threads
        have died, and restarts them if needed.
        """
        logger.info("Starting thread monitor")
        while not self.shutdown_event.is_set():
            for name, thread in list(self.threads.items()):
                if not thread.is_alive():
                    logger.warning(f"{name.capitalize()} thread died, restarting...")
                    self._start_thread(name)
            if self.shutdown_event.wait(5 if not self.debug else 1):
                break
        logger.info("Thread monitor exiting")

    def _start_thread(self, name):
        """
        Internal helper to create and start a named thread
        for video capture, frame processing, heartbeat, or monitoring.
        """
        target_map = {
            "video": self.process_video,
            "processing": self.process_frames,
            "heartbeat": self.heartbeat_worker,
            "monitor": self.monitor_threads
        }
        if name in target_map:
            thread = threading.Thread(target=target_map[name], daemon=True, name=name)
            thread.start()
            self.threads[name] = thread
            return thread
        logger.error(f"Unknown thread name: {name}")
        return None

    def start(self):
        """
        Starts the system: downloads the model if needed, registers the node,
        then spawns all worker threads.
        """
        logger.info("Starting accident detection system")
        if not self.model_manager.download_model():
            logger.error("Failed to download required model. Exiting.")
            return False

        if self.debug:
            logger.info("Debug Mode: Simulating node registration")
            self.register_node()
        else:
            if not self.register_node():
                logger.warning("Failed to register node. Exiting!")
                sys.exit(1)

        for thread_name in ["video", "processing", "heartbeat", "monitor"]:
            self._start_thread(thread_name)

        logger.info("System initialized and running")
        return True

    def run(self):
        """
        Main entry point to start the system. Blocks until a shutdown
        event is triggered or an interrupt occurs.
        """
        if not self.start():
            return False

        startup_time = time.time()
        try:
            while not self.shutdown_event.is_set():
                # Log a status message every ~hour
                if (time.time() - startup_time) % 3600 < 1:
                    logger.info(f"System running for {(time.time() - startup_time) / 3600:.1f} hours")
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Manual interrupt received")
            self.shutdown()

        logger.info("Main loop exiting")
        return True

    def shutdown(self):
        """Initiates a graceful shutdown of the system and worker threads."""
        logger.info("Shutting down gracefully...")
        self.shutdown_event.set()
        logger.info("Waiting for threads to finish...")
        time.sleep(2)
        self.thread_pool.shutdown(wait=False)
        self.camera_manager.release()
        if self.debug:
            cv2.destroyAllWindows()
        logger.info("Shutdown complete")
