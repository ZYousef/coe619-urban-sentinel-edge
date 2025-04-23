"""
config.py

Manages application configuration by merging defaults with values loaded from
environment variables (.env) and a config.ini file, while enforcing validation.
"""
import os
import configparser
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import Any, Dict, Union
import logging

logger = logging.getLogger("accident_detector")

@dataclass(frozen=True)
class ConfigDefaults:
    """
    Default configuration values by section.
    Add new defaults here as needed.
    """
    defaults: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "System": {
            "DebugMode": "False",
            "HeartbeatInterval": "60",
            "StateFile": "state.pkl",
            "ThreadPoolSize": "4"
        },
        "Performance": {
            "FrameQueueSize": "5",
            "FrameCaptureInterval": "0.1",
            "ReportedCheckInterval": "60",
            "AccidentCooldown": "1800",
            "MotionThresholdPixels": "500",
            "MotionPixelDiffThreshold": "25"
        },
        "Detection": {
            "AccidentConfidenceThreshold": "0.7",
            "RequiredConsecutiveFrames": "2"
        },
        "Image": {
            "ResizeWidth": "224",
            "ResizeHeight": "224",
            "CompressionQuality": "70"
        },
        "Model": {
            "Path": "helpers/model.pkl",
            "DownloadURL": "https://huggingface.co/spaces/arionganit/accident-detector/resolve/main/export.pkl",
            
        },
        "API": {
            "BaseURL": "https://q1zx95ecqc.execute-api.me-south-1.amazonaws.com/prod/",
            "Timeout": "10",
            "RetryAttempts": "3",
            "RetryBackoffFactor": "0.3"
        },
        "Node": {
            "Name": "",
            "ID": "",
            "Latitude": "0.0",
            "Longitude": "0.0"
        },
        "Logging": {
            "LogFile": "logs/accident_detector.log"
        },
        "Camera": {
            "Source": "helpers/loop.mp4",
            "Width": "640",
            "Height": "480",
            "FPS": "10",
            "WarmupFrames": "5",
            "LoopMode": "rewind"
        }
    })

class Config:
    """
    Loads configuration from defaults, a .env file, and a config.ini file;
    provides typed getters with validation and explicit persistence.
    """
    def __init__(self, config_file: str = "config.ini") -> None:
        load_dotenv()  # load environment variables
        self.config_file = config_file

        # initialize parser with defaults…
        self.parser = configparser.ConfigParser()
        for section, entries in ConfigDefaults().defaults.items():
            self.parser[section] = entries.copy()

        # overlay from any existing config.ini
        if os.path.exists(self.config_file):
            self.parser.read(self.config_file)

        # now merge in NODE_* env vars into [Node] via our existing setter
        env_to_key = {
            "NODE_NAME":      "Name",
            "NODE_ID":        "ID",
            "NODE_LATITUDE":  "Latitude",
            "NODE_LONGITUDE": "Longitude",
        }
        for env_var, node_key in env_to_key.items():
            val = os.getenv(env_var)
            if val is not None:
                # set() writes it out immediately
                self.set("Node", node_key, val)

        # finally validate ranges
        self._validate_ranges()

    def _validate_ranges(self) -> None:
        """
        Ensure numeric configuration values meet expected constraints.
        """
        if self.getint("Performance", "FrameQueueSize") < 1:
            raise ValueError("Performance.FrameQueueSize must be >= 1")
        if self.getfloat("Performance", "FrameCaptureInterval") <= 0:
            raise ValueError("Performance.FrameCaptureInterval must be > 0")
        if self.getint("Performance", "ReportedCheckInterval") <= 0:
            raise ValueError("Performance.ReportedCheckInterval must be > 0")
        if self.getint("Performance", "AccidentCooldown") < 0:
            raise ValueError("Performance.AccidentCooldown must be >= 0")

    def get(self, section: str, key: str) -> str:
        """Return the raw string value for a configuration key."""
        try:
            return self.parser.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            raise KeyError(f"Missing config {section}.{key}: {e}")

    def getint(self, section: str, key: str) -> int:
        """Return the value as an integer, raising if not parseable."""
        val = self.get(section, key)
        try:
            return int(val)
        except ValueError:
            raise ValueError(f"Invalid integer for {section}.{key}: '{val}'")

    def getfloat(self, section: str, key: str) -> float:
        """Return the value as a float, raising if not parseable."""
        val = self.get(section, key)
        try:
            return float(val)
        except ValueError:
            raise ValueError(f"Invalid float for {section}.{key}: '{val}'")

    def getboolean(self, section: str, key: str) -> bool:
        """Return the value as a boolean, raising if not recognizable."""
        val = self.get(section, key).lower()
        if val in ("true", "1", "yes", "on"):
            return True
        if val in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"Invalid boolean for {section}.{key}: '{val}'")

    def set(self, section: str, key: str, value: Union[str, int, float, bool]) -> None:
        """Set a configuration key and write immediately to disk."""
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        self.parser.set(section, key, str(value))
        self.save()

    def save(self) -> None:
        """Write the current configuration to the config_file."""
        try:
            with open(self.config_file, 'w') as f:
                self.parser.write(f)
        except Exception as e:
            raise IOError(f"Failed to save config to {self.config_file}: {e}")
