"""This module contains the 'Address' and 'Socket' classes that handle network connections."""
import logging as log
import time
from dataclasses import dataclass
from functools import cached_property
from typing import ClassVar, Tuple

import mmh3

DEFAULT_MAINNET_PORT = 8333
TOR_V2_ADDR_LEN = 16 + len(".onion")
TOR_V3_ADDR_LEN = 56 + len(".onion")
I2P_ADDR_LEN = 52 + len(".b32.i2p")
CJDNS_PREFIX = "fc"


@dataclass(frozen=True)
class Address:
    """Class to represent addresses of Bitcoin nodes."""

    host: str
    port: int = DEFAULT_MAINNET_PORT
    timestamp: int = int(time.time())
    supported_types: ClassVar[list[str]] = [
        "ipv4",
        "ipv6",
        "onion_v2",
        "onion_v3",
        "i2p",
        "cjdns",
    ]
    # used by compress()
    _next_id: ClassVar[int] = 0
    _hash_to_id: ClassVar[dict] = {}
    _epoch: ClassVar[int] = int(time.time())

    def __eq__(self, other):
        """Ignore timestamp for equality check"""
        return self.host == other.host and self.port == other.port

    def __hash__(self):
        """Ignore timestamp when creating hash"""
        return hash((self.host, self.port))

    def __str__(self):
        """Format address as string.

        IPv6 (and CJDNS) addresses are surrounded by square brackets.
        """
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    @classmethod
    def from_str(cls, addr_str: str) -> "Address":
        """Create Address object from string."""
        if addr_str.startswith("[") and "]" in addr_str:
            host, port = addr_str[1:].split("]:")
        else:
            host, port = addr_str.split(":")
        return cls(host, int(port))

    @cached_property
    def type(self) -> str:  # pylint: disable=too-many-return-statements
        """Determine network type only when required."""
        if ":" in self.host and self.host.lower().startswith(CJDNS_PREFIX):
            return "cjdns"
        if ":" in self.host and not self.host.lower().startswith(CJDNS_PREFIX):
            return "ipv6"
        if self.host.endswith(".onion") and len(self.host) == TOR_V2_ADDR_LEN:
            return "onion_v2"
        if self.host.endswith(".onion") and len(self.host) == TOR_V3_ADDR_LEN:
            return "onion_v3"
        if self.host.endswith(".b32.i2p") and len(self.host) == I2P_ADDR_LEN:
            return "i2p"
        if len(octets := self.host.split(".")) == 4 and all(
            0 <= int(o) < 256 for o in octets
        ):
            return "ipv4"
        log.error("unsupported address=%s", self)
        return "unknown"

    @cached_property
    def is_ip(self) -> bool:
        """Determine if address is an IP address (IPv4 or IPv6 but not CJDNS)."""
        return self.type in ("ipv4", "ipv6")

    @cached_property
    def is_onion(self) -> bool:
        """Determine if address is an Onion address (v2 or v3)."""
        return self.type in ("onion_v2", "onion_v3")

    @cached_property
    def is_i2p(self) -> bool:
        """Determine if address is an I2P address."""
        return self.type == "i2p"

    @cached_property
    def is_cjdns(self) -> bool:
        """Determine if address is a CJDNS address."""
        return self.type == "cjdns"

    def compress(self) -> Tuple[int, int, int]:
        """
        Compress Address class information for serialization.

        Addresses (host+port) are first hashed to 32-bit signed integers using
        MurmurHash3. To reduce size further, hashes are mapped onto integers,
        starting from zero. The rationale for mapping the hashes onto small
        integers is that the data is serialized to a varint.

        Address last_seen timestamps are mapped onto smaller integers by
        subtracting them from epoch (at the time the crawler is run), then
        zigzag-encoded so they can be stored as varint.

        Network types are converted to integers.
        """
        addr_str = str(self)
        addr_hash = mmh3.hash(addr_str)
        if addr_hash not in self._hash_to_id:
            Address._hash_to_id[addr_hash] = Address._next_id
            Address._next_id += 1
        addr_id = Address._hash_to_id[addr_hash]

        delta = self._epoch - self.timestamp
        delta_zigzag = (delta << 1) ^ (delta >> 31)

        net_id = self.supported_types.index(self.type)

        return addr_id, delta_zigzag, net_id
