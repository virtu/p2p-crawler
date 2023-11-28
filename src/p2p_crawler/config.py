"""This module contains configuration options for the crawler."""

import argparse
import importlib.metadata
import os
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path

__version__ = importlib.metadata.version(__package__ or __name__)


@dataclass
class VersionInfo:
    """Version information for crawler."""

    version: str  # package version
    extra: str  # extra version info (e.g. git commit hash)

    @classmethod
    def get_info(cls, args):
        """Read version info and return instance."""
        return cls(
            version=__version__,
            extra=args.extra_version_info,
        )


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
        prefix = f"{args.result_path}/{args.timestamp + '_v' + __version__}"
        return cls(
            log_level=args.log_level.upper(),
            store_debug_log=args.store_debug_log,
            debug_log_path=Path(f"{prefix}_debug_log.txt"),
        )


@dataclass
class GCSSettings(ComponentSettings):
    """GCS-related settings."""

    store: bool
    bucket: str
    location: str
    credentials: str

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return cls(
            store=args.store_to_gcs,
            bucket=args.gcs_bucket,
            location=args.gcs_location,
            credentials=args.gcs_credentials,
        )


@dataclass
class ResultSettings(ComponentSettings):
    """Paths for output files."""

    path: Path
    reachable_nodes: Path
    crawler_stats: Path
    address_stats: Path
    gcs: GCSSettings

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        prefix = f"{args.result_path}/{args.timestamp + '_v' + __version__}"
        return cls(
            path=Path(args.result_path),
            reachable_nodes=Path(f"{prefix}_reachable_nodes.csv"),
            crawler_stats=Path(f"{prefix}_crawler_stats.json"),
            address_stats=Path(f"{prefix}_address_stats.json"),
            gcs=GCSSettings.parse(args),
        )


@dataclass
class NetworkSettings(ComponentSettings):
    """Settings related to networking."""

    tor_proxy_host: str
    tor_proxy_port: str
    i2p_sam_host: str
    i2p_sam_port: str

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return cls(
            tor_proxy_host=args.tor_proxy_host,
            tor_proxy_port=args.tor_proxy_port,
            i2p_sam_host=args.i2p_sam_host,
            i2p_sam_port=args.i2p_sam_port,
        )


@dataclass
class NodeSettings(ComponentSettings):
    """Settings for nodes."""

    timeouts: dict[str, TimeoutSettings]
    handshake_attempts: int
    getaddr_attempts: int
    network_settings: NetworkSettings

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return cls(
            timeouts=TimeoutSettings.parse(args),
            handshake_attempts=args.handshake_attempts,
            getaddr_attempts=args.getaddr_attempts,
            network_settings=NetworkSettings.parse(args),
        )


@dataclass
class CrawlerSettings(ComponentSettings):
    """Settings for the crawler."""

    version_info: VersionInfo
    delay_start: int
    num_workers: int
    node_share: float
    record_addr_stats: bool
    node_settings: NodeSettings
    result_settings: ResultSettings

    @classmethod
    def parse(cls, args):
        """Create class instance from arguments."""
        return cls(
            version_info=VersionInfo.get_info(args),
            delay_start=args.delay_start,
            num_workers=args.num_workers,
            node_share=args.node_share,
            record_addr_stats=args.record_addr_stats,
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
        "IP": {"connect": 3, "message": 30, "getaddr": 70},
        "TOR": {"connect": 100, "message": 40, "getaddr": 90},
        "I2P": {"connect": 30, "message": 80, "getaddr": 170},
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
        default=os.environ.get("NUM_WORKERS", 64),
        help="Number of crawler coroutines",
    )

    parser.add_argument(
        "--node-share",
        type=float,
        default=os.environ.get("NODE_SHARE", 1.00),
        help="Share of nodes to query for peers",
    )

    parser.add_argument(
        "--handshake-attempts",
        type=int,
        default=os.environ.get("HANDSHAKE_ATTEMPTS", 3),
        help="Number of times to attempt node handshake if it does not succeed at first",
    )

    parser.add_argument(
        "--delay-start",
        type=int,
        default=os.environ.get("DELAY_START", 10),
        help="Delay before starting to wait for tor and i2p containers. Default: 10s",
    )

    parser.add_argument(
        "--getaddr-attempts",
        type=int,
        default=os.environ.get("GETADDR_ATTEMPTS", 2),
        help="Number of times to attempt getaddr requests for reachable nodes",
    )

    parser.add_argument(
        "--tor-proxy-host",
        type=str,
        default="127.0.0.1",
        help="SOCKS5 proxy host for Tor",
    )

    parser.add_argument(
        "--tor-proxy-port",
        type=int,
        default=9050,
        help="SOCKS5 proxy port for Tor",
    )

    parser.add_argument(
        "--i2p-sam-host",
        type=str,
        default="127.0.0.1",
        help="SAM router host for I2P",
    )

    parser.add_argument(
        "--i2p-sam-port",
        type=int,
        default=7656,
        help="SAM router port for I2P",
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
        "--extra-version-info",
        type=str,
        default=None,
        help="Extra version info (e.g., git commit hash)",
    )

    parser.add_argument(
        "--timestamp",
        default=os.environ.get(
            "TIMESTAMP", time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
        ),
        help="Timestamp for results",
    )

    parser.add_argument(
        "--record-addr-stats",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Record and store address statistics",
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
        default=False,
        help="Store results to GCS (default: disabled)",
    )
    parser.add_argument(
        "--gcs-bucket",
        type=str,
        default=None,
        help="GCS bucket (default: None)",
    )
    parser.add_argument(
        "--gcs-location",
        type=str,
        default=f"sources/{socket.gethostname()}",
        help="GCS location (default: sources/<hostname>)",
    )
    parser.add_argument(
        "--gcs-credentials",
        type=str,
        default=None,
        help="GCS credentials (service account private key file file, default: None)",
    )


def parse_args():
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser()

    add_timeout_args(parser)
    add_general_args(parser)
    args = parser.parse_args()

    return args
