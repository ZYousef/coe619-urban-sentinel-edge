"""
config.py

This module contains the Config class, which manages application configuration
settings from a local config.ini file. It provides a fallback to defaults if
no config file is found.
"""

import os
import configparser
from dotenv import load_dotenv

class Config:
    """
    Manages reading/writing settings from a config file (e.g., config.ini).
    Provides convenient methods to parse integers, floats, booleans, etc.
    """
    def __init__(self, config_file="config.ini"):
        load_dotenv()
        self.config = configparser.ConfigParser()
        self._set_defaults()
        if os.path.exists(config_file):
            self.config.read(config_file)
        else:
            with open(config_file, 'w') as f:
                self.config.write(f)

    def _set_defaults(self):
        """
        Private method that sets default config values in memory (i.e., if no
        config file exists yet).
        """
        self.config["System"] = {
            "ModelPath": "helpers/export.pkl",
            "ModelUrl": "https://huggingface.co/spaces/arionganit/accident-detector/resolve/main/export.pkl",
            "StateFile": "state.pkl",
            "HeartbeatInterval": "60",
            "ThreadPoolSize": "2",
            "DebugMode": "False"
        }
        self.config["API"] = {
            "BaseUrl": "https://may87uhma3.execute-api.me-south-1.amazonaws.com/prod/",
            "Timeout": "5",
            "RetryBackoffFactor": "1",
            "RetryAttempts": "5"
        }
        self.config["Performance"] = {
            "FrameQueueSize": "5",
            "FrameCaptureInterval": "0.1",
            "AccidentCooldown": "1800",
            "MotionThresholdPixels": "500",
            "MotionPixelDiffThreshold": "25"
        }
        self.config["Image"] = {
            "ResizeWidth": "224",
            "ResizeHeight": "224",
            "CompressionQuality": "70"
        }
        self.config["Camera"] = {
            "Width": "640",
            "Height": "480",
            "FPS": "10",
            "WarmupFrames": "5",
            "loop_video": "helpers/loop.mp4"
            # "loop_video": "rtsp://localhost:9999/stream"
        }
        self.config["Detection"] = {
            "AccidentConfidenceThreshold": "0.7",
            "RequiredConsecutiveFrames": "2"
        }
        self.config["Node"] = {
            "Name": os.getenv("NODE_NAME", "edge_node_1"),
            "ID": os.getenv("NODE_ID", "default-node-id"),
            "Latitude": os.getenv("LATITUDE", "37.7749"),
            "Longitude": os.getenv("LONGITUDE", "-122.4194")
        }

    def get(self, section, key, fallback=None):
        """Returns a string value from config, with optional fallback."""
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section, key, fallback=None):
        """Returns an integer value from config, with optional fallback."""
        return self.config.getint(section, key, fallback=fallback)

    def getfloat(self, section, key, fallback=None):
        """Returns a float value from config, with optional fallback."""
        return self.config.getfloat(section, key, fallback=fallback)

    def getboolean(self, section, key, fallback=None):
        """Returns a boolean value from config, with optional fallback."""
        return self.config.getboolean(section, key, fallback=fallback)
