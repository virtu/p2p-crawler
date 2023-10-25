#!/usr/bin/env python3

"""Command-line interface for the crawler."""

import asyncio
import logging as log
import os
import sys
import time
from pathlib import Path

from .config import LogSettings, Settings, parse_args
from .crawler import Crawler
from .output import Output


def check_requirements():
    """Assert Python version requrements."""
    min_major, min_minor = (3, 9)
    if (sys.version_info.major, sys.version_info.minor) < (min_major, min_minor):
        print(f"This code requires Python {min_major}.{min_minor} or greater")
        sys.exit(1)


def sanity_check_settings(settings):
    """
    Carry out sanity checks.

    Logger has not been set up yet, so use print().
    Carries out the following checks:
      - Ensure GCS credentials are available when storing to GCS was requested
      - Create results directory if it does not exist
    """

    if settings.result_settings.store_to_gcs:
        env_var = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not env_var:
            print(
                "[ERROR] --store-to-gcs set but GOOGLE_APPLICATION_CREDENTIALS environment variable not set!"
            )
            sys.exit(os.EX_CONFIG)
        p = Path(env_var)
        if not p.is_file():
            print(f"[ERROR] --store-to-gcs set but file {p} does not exist!")
            sys.exit(os.EX_CONFIG)

    if not (p := settings.result_settings.path).exists():
        print(f"[WARNING] result path {p} does not exist.")
        p.mkdir(parents=True, exist_ok=True)
        print(f"[INFO] created result path {p}.")


def init_logger(settings: LogSettings):
    """Initilize the logger. Use UTC-based timestamps and log to file if requested."""

    log_fmt = log.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    log.Formatter.converter = time.gmtime
    root_logger = log.getLogger()
    root_logger.setLevel(log.NOTSET)

    console_handler = log.StreamHandler()
    console_handler.setFormatter(log_fmt)
    console_handler.setLevel(settings.log_level)
    root_logger.addHandler(console_handler)

    if settings.store_debug_log:
        file_handler = log.FileHandler(settings.debug_log_path)
        file_handler.setFormatter(log_fmt)
        file_handler.setLevel(log.DEBUG)
        root_logger.addHandler(file_handler)
        log.debug("Storing debug log to file %s", settings.debug_log_path.name)


def init():
    """
    Handle initialization.

    First, check requirements, then parse command-line arguments and create
    settings object. Next, sanity-check the settings and initialize the logger.
    """

    check_requirements()
    args = parse_args()
    settings = Settings.parse(args)
    sanity_check_settings(settings)
    init_logger(settings.log_settings)
    log.info("Run settings: %s", settings)
    return settings


def main():
    """Execution entry point.

    Initialize, execute crawler, and store results.
    """

    settings = init()
    crawler = Crawler(settings.crawler_settings)
    asyncio.run(crawler.run(), debug=False)
    Output(settings.result_settings, settings.log_settings, crawler).persist()


if __name__ == "__main__":
    main()
