# Accident Detection System

This repository contains a Python-based edge computing solution for detecting traffic accidents in real-time using computer vision and AI. The system uses [OpenCV](https://opencv.org/), [Fastai](https://www.fast.ai/), and [requests](https://pypi.org/project/requests/) (among others) to capture frames from a camera or video file, detect accidents using a trained model, and report these events to a remote API endpoint.

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Usage](#usage)
  - [Configuration](#configuration)
  - [Running the System](#running-the-system)
- [Project Structure](#project-structure)
- [Customization](#customization)
- [Logging](#logging)
- [Contributing](#contributing)
- [License](#license)

---

## Features

1. **Camera/Video Input**  
   Reads frames from a local camera or a video file (configurable).  

2. **Motion Detection**  
   Utilizes frame differencing to detect motion above a threshold before attempting any classification, reducing unnecessary computations.  

3. **AI-Powered Accident Detection**  
   Leverages a Fastai-trained model (default name: `export.pkl`) that classifies frames into "accident" or "no_accident".  

4. **Automatic Model Download & Verification**  
   Downloads the model from a specified URL if it doesn't exist locally, then verifies integrity by attempting to load it.  

5. **Accident Reporting & Cooldown**  
   Once an accident is detected with sufficient confidence in consecutive frames, the system sends a report to a remote API. Then it waits for a cooldown period before detecting again.  

6. **Heartbeat Mechanism**  
   Periodically sends a heartbeat (status update) to a remote API endpoint to indicate the node is active.  

7. **Threaded Architecture**  
   Uses multiple threads: 
   - One for capturing frames, 
   - One for processing frames, 
   - One for sending heartbeats, 
   - One for monitoring and restarting threads if they crash.  

8. **Graceful Shutdown**  
   Catches signals (SIGINT, SIGTERM) and shuts down threads/camera gracefully.

---

## How It Works

1. **Initialization**  
   - A configuration file (`config.ini`) is read or created with default values if it doesn't exist.  
   - The system checks or downloads the AI model (`export.pkl`).  
   - The node registers itself to a central API (if configured).  

2. **Video Capture & Motion Detection**  
   - The system reads frames from the camera or a specified video file in a loop.  
   - If motion is detected above certain thresholds, the frame is queued for classification.  

3. **Accident Detection**  
   - A separate thread processes queued frames using the loaded AI model.  
   - If the model predicts "accident" with confidence above `AccidentConfidenceThreshold` for a required number of consecutive frames (`RequiredConsecutiveFrames`), an accident event is triggered.  

4. **Accident Reporting**  
   - The system sends an event (including a compressed base64-encoded image) to the specified API endpoint.  
   - Enters a "cooldown" period where no further accident events are reported for a configured duration.  

5. **Heartbeat & Monitoring**  
   - The system sends periodic heartbeats to the API.  
   - A monitor thread checks health of all other threads, restarting them if necessary.  

6. **Graceful Shutdown**  
   - On receiving a termination signal (SIGINT, SIGTERM) or a KeyboardInterrupt, the system attempts to shut down all threads, save state, and release camera resources.  

---

## Installation

Follow these steps to set up and run the Accident Detection System.

1. **Clone this repository**:

   ```bash
   git clone https://github.com/your-username/accident-detection-system.git
   cd accident-detection-system
   ```

2. **Create and activate a virtual environment (recommended)**:

   ```bash
   # Using Python's built-in venv
   python -m venv venv
   source venv/bin/activate  # On Linux/macOS
   # or
   venv\Scripts\activate     # On Windows
   ```

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

   The `requirements.txt` should contain (at a minimum):
   - `opencv-python`
   - `requests`
   - `fastai`
   - `numpy`
   - `configparser`
   - `dataclasses; python_version<"3.7"` (if needed for older Python versions)
   - `logging` (standard library)
   - `python-dotenv` (optional, if you prefer environment-based configs)

4. **(Optional) Place your AI model**  
   - If you already have a trained model named `export.pkl`, place it in the same directory as the Python script. Otherwise, the system will attempt to download it from the configured URL in `config.ini`.

---

## Usage

### Configuration

This system uses a `config.ini` file for managing settings. Upon first run, it will create one with default values if `config.ini` does not exist. Below are some key sections and parameters:

- **System**  
  ```ini
  [System]
  ModelPath = export.pkl
  ModelUrl = https://huggingface.co/.../export.pkl
  StateFile = state.pkl
  HeartbeatInterval = 60
  ThreadPoolSize = 2
  ```
- **API**  
  ```ini
  [API]
  BaseUrl = https://your-api-endpoint/
  Timeout = 5
  RetryBackoffFactor = 1
  RetryAttempts = 5
  ```
- **Performance**  
  ```ini
  [Performance]
  FrameQueueSize = 5
  FrameCaptureInterval = 0.1
  AccidentCooldown = 1800
  MotionThresholdPixels = 500
  MotionPixelDiffThreshold = 25
  ```
- **Image**  
  ```ini
  [Image]
  ResizeWidth = 224
  ResizeHeight = 224
  CompressionQuality = 70
  ```
- **Camera**  
  ```ini
  [Camera]
  Width = 640
  Height = 480
  FPS = 10
  WarmupFrames = 5
  loop_video = loop.mp4
  ```
- **Detection**  
  ```ini
  [Detection]
  AccidentConfidenceThreshold = 0.7
  RequiredConsecutiveFrames = 2
  ```
- **Node**  
  ```ini
  [Node]
  Name = edge_node_1
  ID = default-node-id
  Latitude = 37.7749
  Longitude = -122.4194
  ```

You can customize these values as needed. For example, if you want to change the video source, update the `loop_video` parameter in the `[Camera]` section to another file or device index.

### Running the System

1. **Run the main Python script**:

   ```bash
   python accident_detector.py
   ```

2. **Watch the logs**  
   The script will produce console output (INFO level) and also log to `accident_detector.log` with more verbosity (DEBUG level on certain messages).

3. **Shutdown**  
   - Press `Ctrl + C` (SIGINT) or send SIGTERM to gracefully stop the system.  
   - The script attempts to save the current state (`state.pkl`) and closes all resources.

---

## Project Structure

A high-level overview of the main components:

```
accident_detector/
├── accident_detector.py   # Main script containing classes & logic
├── config.ini             # Configuration file (auto-generated if missing)
├── requirements.txt       # Python dependencies
├── accident_detector.log  # Log file (created at runtime)
├── state.pkl              # Pickle file to store state (created at runtime)
└── ...
```

- **Config**  
  A simple wrapper around `configparser` that sets default values and reads/writes `config.ini`.
- **SystemState**  
  Handles saving and loading persistent state (e.g., last accident time) via a pickle file.
- **APIClient**  
  Responsible for sending requests (registration, heartbeat, accident events) to a remote server.
- **ModelManager**  
  Downloads, verifies, and loads the AI model. Provides a `predict` method to classify frames.
- **ImageProcessor**  
  Provides image compression, resizing, motion detection, etc.
- **CameraManager**  
  Handles video capture initialization, reading frames, and cleanup.
- **AccidentDetectionSystem**  
  Orchestrates all components, managing threads for video capture, frame processing, heartbeats, and monitoring.

---

## Customization

- **Model**  
  If you have your own Fastai-based model, you can replace the `export.pkl` or update the `ModelUrl` in the `[System]` section of `config.ini`.
- **APIs**  
  Update the `BaseUrl` to point to your own server endpoints.
- **Motion Detection**  
  Tune thresholds in `[Performance]` to reduce false positives or capture more subtle movements.
- **Threading & Performance**  
  Adjust `ThreadPoolSize`, `FrameQueueSize`, `FrameCaptureInterval`, etc., to optimize CPU/GPU usage.

---

## Logging

- **Console**  
  Logs at the INFO level are printed directly to the console.
- **File Logging**  
  A rotating file handler writes logs to `accident_detector.log`. The file can grow up to 10 MB before being rotated (with up to 5 backups by default).
- **Debugging**  
  To see more detailed logs, search for `logger.debug()` calls within the codebase or raise the logger’s level at the top of `setup_logging()`.

---

## Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to check [issues page](https://github.com/your-username/accident-detection-system/issues) if you want to contribute.

1. Fork the project.
2. Create your feature branch (`git checkout -b feature/my-feature`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature/my-feature`).
5. Open a Pull Request.

---

## License

[MIT License](LICENSE) - Feel free to use, modify, and distribute this software as permitted under the MIT license. If you incorporate significant modifications or improvements, please consider contributing them back to the community.

---

**Thank you for using the Accident Detection System!** If you have any questions or run into any issues, please open an issue or submit a PR. Happy coding!