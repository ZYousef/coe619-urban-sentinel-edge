import sys
import signal
import argparse
import logging
from .logging_setup import setup_logging
from .system import AccidentDetectionSystem
from .config import Config

VERSION = "1.0.0"


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments and subcommands.

    If no subcommand is provided, defaults to 'run'.
    """
    parser = argparse.ArgumentParser(
        prog="accident_detector",
        description="Real-time accident detection system"
    )
    parser.add_argument(
        "--version", action="version", version=VERSION,
        help="Show program version and exit"
    )
    # Global debug flag
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode"
    )

    subparsers = parser.add_subparsers(dest="command")
    # set default command to 'run'
    parser.set_defaults(command="run")

    # run command
    subparsers.add_parser(
        "run", help="Start the accident detection system"
    )

    # check-config command
    subparsers.add_parser(
        "check-config", help="Validate configuration file and exit"
    )

    return parser.parse_args()


def handle_signal(system: AccidentDetectionSystem, signum: int, frame: any) -> None:
    """
    Signal handler that triggers graceful shutdown.
    """
    logging.info(f"Signal {signum} received, shutting down...")
    system.shutdown()


def main() -> None:
    """
    Main entry point: parses arguments, sets up logging, and dispatches commands.
    """
    args = parse_args()
    setup_logging()
    logger = logging.getLogger("accident_detector")

    if args.command == "check-config":
        try:
            cfg = Config()
            _ = cfg.get("Node", "ID")
            logger.info("Configuration file parsed successfully.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            sys.exit(1)

    # args.command == 'run'
    debug = args.debug
    system = AccidentDetectionSystem(debug=debug)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, lambda s, f: handle_signal(system, s, f))
    signal.signal(signal.SIGTERM, lambda s, f: handle_signal(system, s, f))

    # Run
    try:
        system.run()
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
