"""
main.py

The primary entry point of the accident_detector package. It
sets up signal handlers, parses arguments, and runs the system.
"""

import sys
import time
import signal
import argparse
from .logging_setup import setup_logging
from .system import AccidentDetectionSystem

def signal_handler(signal_received, frame):
    """
    Handles OS signals (e.g., SIGINT, SIGTERM). On receipt,
    shutdown the global system object if it exists.
    """
    logger = setup_logging()  # ensure logger is accessible
    logger.info(f"Received signal {signal_received}")
    global system
    if 'system' in globals():
        system.shutdown()
    sys.exit(0)

def main():
    """
    Parses command-line args, sets up logging, initializes
    and runs the AccidentDetectionSystem.
    """
    logger = setup_logging()
    parser = argparse.ArgumentParser(description="Accident Detection System")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    global system
    system = AccidentDetectionSystem(debug=args.debug)
    system.run()

if __name__ == "__main__":
    main()
