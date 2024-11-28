#!/usr/bin/env python3

"""
A script to fill in missing data from previous runs.

Although multiple crawler instances are collecting data on different VPS, in
some cases network problems (e.g. an attack on the TOR network) lead to runs
taking longer than 24 hours, leading to missing data for certain days.
"""

import datetime as dt
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List


@dataclass
class CrawlerOutput:
    """Class representing output files created by the crawler."""

    FILES: ClassVar[List[str]] = [
        "reachable_nodes.csv.bz2",
        "crawler_stats.json.bz2",
        "debug_log.txt.bz2",
    ]
    path: Path
    timestamp: dt.datetime

    def __post_init__(self):
        """Assert none of the expected files are missing."""
        # Get list of files matching the timestamp
        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        file_list = [f for f in os.listdir(self.path) if f.startswith(timestamp_str)]

        # Make sure there's only one version, then set version
        versions = {f.split("_")[1] for f in file_list}
        if len(versions) != 1:
            raise ValueError(f"Expecting exactly one version. Found: {versions}")
        self.version = versions.pop()

        # Check for exact match of the expected files and number
        expected_files = [
            f"{timestamp_str}_{self.version}_{suffix}" for suffix in self.FILES
        ]
        for expected_file in expected_files:
            if expected_file not in file_list:
                raise ValueError(
                    f"Expected file not found: {expected_file} found: {file_list}"
                )


@dataclass
class MissingOutput:
    """Dataclass representing missing runs."""

    MARKER: ClassVar[dt.time] = dt.time(12, 34, 56)
    date: dt.date
    source: CrawlerOutput

    def fill(self, path: Path):
        """Fill in missing data by copying files from the source timestamp to the missing date."""
        src_base = f"{str(path)}/{self.source.timestamp.strftime('%Y-%m-%dT%H-%M-%SZ')}_{self.source.version}_"
        dst_timestamp = dt.datetime.combine(self.date, self.MARKER)
        dst_base = f"{str(path)}/{dst_timestamp.strftime('%Y-%m-%dT%H-%M-%SZ')}_{self.source.version}_"
        for file in self.source.FILES:
            src = src_base + file
            dst = dst_base + file
            print(f"Copying {src} to {dst}")
            shutil.copyfile(src, dst)


def get_outputs(path: Path) -> List[CrawlerOutput]:
    """
    Find all runs in the given directory.

    First, collect all unique timestamps of bz2 files. Next, initialize
    CrawlerOutput objects, which automatically assert that all of the expected
    output files exist; then return the list of runs.
    """

    timestamps = set()
    for f in path.iterdir():
        if not f.is_file() or f.suffix != ".bz2":
            continue
        try:
            timestamp_str = f.name.split("_")[0]
            timestamp = dt.datetime.strptime(timestamp_str, "%Y-%m-%dT%H-%M-%SZ")
        except ValueError:
            print(f"Could not parse timestamp of file '{f}'. Skipping.")
            continue
        timestamps.add(timestamp)
    print(f"Found {len(timestamps)} unique timestamps.")

    outputs = [CrawlerOutput(path, timestamp) for timestamp in timestamps]
    print(f"Found {len(outputs)} valid runs.")
    return outputs


def find_missing_outputs(outputs: List[CrawlerOutput]) -> List[MissingOutput]:
    """Find missing runs."""

    date_start = min(outputs, key=lambda x: x.timestamp).timestamp.date()
    date_end = max(outputs, key=lambda x: x.timestamp).timestamp.date()
    date_range = [
        date_start + dt.timedelta(days=x)
        for x in range((date_end - date_start).days + 1)
    ]
    run_dates = [output.timestamp.date() for output in outputs]
    missing_dates = [date for date in date_range if date not in run_dates]
    print(f"Total missing dates: {len(missing_dates)}")
    missing_outputs = []
    for missing_date in missing_dates:
        missing_timestamp = dt.datetime.combine(missing_date, dt.time.min)
        source = min(outputs, key=lambda x, ts=missing_timestamp: abs(x.timestamp - ts))
        print(f"missing date: {missing_date}, filled from source: {source.timestamp}")
        missing_output = MissingOutput(missing_date, source)
        missing_outputs.append(missing_output)
    return missing_outputs


def get_path():
    """Get the path from the command line arguments."""
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        print("Usage: python fill_missing_data.py <path>")
        sys.exit(1)
    if not os.path.isdir(path):
        print(f"Error: The path '{path}' does not exist or is not a directory.")
        sys.exit(1)
    return Path(path)


def prompt_proceed():
    """Prompt the user to proceed."""
    print("Proceed to fill missing data? (y/N)")
    return input().lower() == "y"


def fill_missing_data(missing_outputs: List[MissingOutput], path: Path):
    """Fill missing data by copying files from the source timestamp to the missing date."""

    for missing_output in missing_outputs:
        missing_output.fill(path)


def main():
    """Main function."""

    path = get_path()
    outputs = get_outputs(path)
    missing = find_missing_outputs(outputs)
    if prompt_proceed():
        fill_missing_data(missing, path)


if __name__ == "__main__":
    main()
