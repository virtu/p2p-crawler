"""This module contains configuration options for the crawler."""

import argparse
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

__version__ = "2.0.0"


@dataclass
class BuildInfo:
    """Build information for crawler."""

    time: str  # time of build
    version: str  # version of build
    git_branch: str  # build branch
    git_commit: str  # build commit hash
    git_status: str  # repo status at time of build

    @classmethod
    def parse(cls, args):
        """Read build info and return instance."""
        path = args.build_info_path
        return cls(
            time=cls.read_file(path / "build-time.txt"),
            version=cls.read_file(path / "/build-version.txt"),
            git_branch=cls.read_file(path / "/build-git-branch.txt"),
            git_commit=cls.read_file(path / "/build-git-commit.txt"),
            git_status=cls.read_file(path / "/build-git-status.txt"),
        )

    @staticmethod
    def read_file(path: Path) -> str:
        """Read and return contents of file."""
        if not path.is_file():
            print("warning: unable to read build info from %s: not a file", path)
            return "unknown"
        with open(path, "r", encoding="UTF-8") as f:
            return f.readline().rstrip()


@dataclass
class ComponentSettings:
    """Base class for components."""

    def to_dict(self):
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class TimeoutSettings(ComponentSettings):
    """
    Timeouts for different network requests.

    All timeouts are in seconds:
      - connect: time to connect to node
      - message: time to wait for message replies
      - getaddr: total time for addr/addrv2 replies
    """

    connect: int
    message: int
    getaddr: int

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return {
            "ip": cls(
                connect=args.ip_connect_timeout,
                message=args.ip_message_timeout,
                getaddr=args.ip_getaddr_timeout,
            ),
            "tor": cls(
                connect=args.tor_connect_timeout,
                message=args.tor_message_timeout,
                getaddr=args.tor_getaddr_timeout,
            ),
            "i2p": cls(
                connect=args.i2p_connect_timeout,
                message=args.i2p_message_timeout,
                getaddr=args.i2p_getaddr_timeout,
            ),
        }


@dataclass
class LogSettings(ComponentSettings):
    """Paths for output files."""

    log_level: int
    store_debug_log: bool
    debug_log_path: Path

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        prefix = f"{args.result_path.name}/{args.timestamp + '_v' + __version__}"
        return cls(
            log_level=args.log_level.upper(),
            store_debug_log=args.store_debug_log,
            debug_log_path=Path(f"{prefix}_debug_log.txt"),
        )


@dataclass
class ResultSettings(ComponentSettings):
    """Paths for output files."""

    path: Path
    reachable_nodes: Path
    crawler_stats: Path
    address_stats: Path
    store_to_gcs: bool
    gcs_bucket: str
    gcs_location: str

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        prefix = f"{args.result_path.name}/{args.timestamp + '_v' + __version__}"
        return cls(
            path=Path(args.result_path.name),
            reachable_nodes=Path(f"{prefix}_reachable_nodes.csv"),
            crawler_stats=Path(f"{prefix}_crawler_stats.json"),
            address_stats=Path(f"{prefix}_address_stats.json"),
            store_to_gcs=args.store_to_gcs,
            gcs_bucket=args.gcs_bucket,
            gcs_location=args.gcs_location,
        )


@dataclass
class NodeSettings(ComponentSettings):
    """Settings for nodes."""

    timeouts: dict[str, TimeoutSettings]
    getaddr_retries: int

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return cls(
            timeouts=TimeoutSettings.parse(args),
            getaddr_retries=args.getaddr_retries,
        )


@dataclass
class CrawlerSettings(ComponentSettings):
    """Settings for the crawler."""

    build_info: BuildInfo
    delay_start: int
    num_workers: int
    node_share: float
    node_settings: NodeSettings
    result_settings: ResultSettings

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return cls(
            build_info=BuildInfo.parse(args),
            delay_start=args.delay_start,
            num_workers=args.num_workers,
            node_share=args.node_share,
            node_settings=NodeSettings.parse(args),
            result_settings=ResultSettings.parse(args),
        )


@dataclass
class Settings:
    """Configuration settings."""

    crawler_settings: CrawlerSettings
    result_settings: ResultSettings
    log_settings: LogSettings

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return cls(
            crawler_settings=CrawlerSettings.parse(args),
            result_settings=ResultSettings.parse(args),
            log_settings=LogSettings.parse(args),
        )


def add_timeout_args(parser):
    """Add command-line arguments related to network timeouts."""

    settings = {
        "IP": {"connect": 3, "message": 5, "getaddr": 30},
        "TOR": {"connect": 30, "message": 60, "getaddr": 120},
        "I2P": {"connect": 120, "message": 120, "getaddr": 240},
    }

    helps = {
        "connect": "Timeout for establishing connections using",
        "message": "Timeout for replies using",
        "getaddr": "Max. time to receive addr messages from peers using",
    }

    for net, timeouts in settings.items():
        for op, timeout in timeouts.items():
            argument = f"--{net.lower()}-{op.lower()}-timeout"
            default = os.environ.get(f"{net.upper()}_{op.upper()}_TIMEOUT", timeout)
            help_ = f"{helps[op]} {net}"
            parser.add_argument(argument, type=float, default=default, help=help_)


def add_general_args(parser):
    """Add command-line arguments related to crawler."""

    parser.add_argument(
        "--num-workers",
        type=int,
        default=os.environ.get("NUM_WORKERS", 20),
        help="Number of crawler coroutines",
    )

    parser.add_argument(
        "--node-share",
        type=float,
        default=os.environ.get("NODE_SHARE", 1.00),
        help="Share of nodes to query for peers",
    )

    parser.add_argument(
        "--delay-start",
        type=int,
        default=os.environ.get("DELAY_START", 10),
        help="Delay before starting to wait for tor and i2p containers. Default: 10s",
    )

    parser.add_argument(
        "--getaddr-retries",
        type=int,
        default=os.environ.get("GETADDR_RETRIES", 2),
        help="Number of retries for getaddr requests for reachable nodes",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Logging verbosity",
    )

    parser.add_argument(
        "--result-path",
        type=Path,
        default=os.environ.get("RESULT_PATH", "results"),
        help="Directory for results",
    )

    parser.add_argument(
        "--build-info-path",
        type=Path,
        default=Path(os.environ.get("BUILD_INFO_PATH", "/")),
        help="Path to build info files",
    )

    parser.add_argument(
        "--timestamp",
        default=os.environ.get(
            "TIMESTAMP", time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
        ),
        help="Timestamp for results",
    )

    parser.add_argument(
        "--store-debug-log",
        action=argparse.BooleanOptionalAction,
        default=str(os.environ.get("STORE_DEBUG_LOG", True)).lower() == "true",
        help="Store debug log",
    )

    # GCS settings
    parser.add_argument(
        "--store-to-gcs",
        action=argparse.BooleanOptionalAction,
        default=str(os.environ.get("STORE_TO_GCS", False)).lower() == "true",
        help="Store results to GCS",
    )
    parser.add_argument(
        "--gcs-bucket",
        type=str,
        default=os.environ.get("GCS_BUCKET", "bitcoin_p2p_crawler"),
        help="GCS bucket",
    )
    parser.add_argument(
        "--gcs-location",
        type=str,
        default=os.environ.get("GCS_LOCATION", "undefined"),
        help="GCS location",
    )


def parse_args():
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser()

    add_timeout_args(parser)
    add_general_args(parser)
    args = parser.parse_args()

    return args
