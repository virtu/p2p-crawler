"""This module contains classes used to represent Bitcoin nodes."""

from __future__ import annotations

import asyncio
import logging as log
import time
from dataclasses import asdict, dataclass, field
from functools import cached_property

from .config import NodeSettings, TimeoutSettings
from .decorators import timing
from .network import Address, Socket
from .protocol import (AddrMessage, AddrV2Message, GetAddrMessage,
                       SendAddrV2Message, VerAckMessage, VersionMessage)


@dataclass
class Node:
    """Class representing Bitcoin nodes."""

    address: Address
    settings: NodeSettings
    seed_distance: int = 0
    stats: dict[str, str | int | bool] = field(default_factory=dict)

    @cached_property
    def _socket(self) -> Socket:
        """Lazy-create socket."""
        return Socket(self.settings.network_settings)

    @cached_property
    def _timeouts(self) -> TimeoutSettings:
        """Lazy-create timeouts."""
        if self.address.is_ip:
            return self.settings.timeouts["ip"]
        if self.address.is_onion:
            return self.settings.timeouts["tor"]
        if self.address.is_i2p:
            return self.settings.timeouts["i2p"]
        raise NotImplementedError("Unknown address type")

    def __str__(self):
        """Format node as string."""
        return str(self.address)

    def __eq__(self, other):
        """Compare nodes by address."""
        return self.address == other.address

    def __hash__(self):
        """Hash nodes by address."""
        return hash(self.address)

    @timing
    async def connect(self) -> bool:
        """Try to open connection to node and return outcome."""
        try:
            await self._socket.connect(self.address, timeout=self._timeouts.connect)
            log.debug("Successfully connected to node %s", self)
            self.stats.update(self._socket.stats)
            return True
        except Exception as e:  # pylint: disable=broad-except
            log.debug("Could not connect to node %s: %s", self, repr(e))
            return False

    @timing
    async def disconnect(self):
        """Disconnect from node."""
        try:
            await self._socket.disconnect()
            log.debug("Successfully disconnected from node: %s", self)
        except Exception as e:  # pylint: disable=broad-except
            log.debug("Could not disconnect to from %s: %s", self, repr(e))

    def has_handshake_attempts_left(self):
        """Return true if node has handshake attempts left; false otherwise."""
        if "handshake_attempts" not in self.stats:
            return True
        if self.stats["handshake_attempts"] < self.settings.handshake_attempts:
            return True
        return False

    @timing
    async def handshake(self) -> bool:
        """
        Perform node handshake and return outcome.

        Send a version messages and wait for reply. Record timestamp handshake
        was sent, whether handshake as successful, and, if it was, the version
        message sent by the peer.
        """

        self.stats["handshake_attempts"] = self.stats.get("handshake_attempts", 0) + 1
        time_start = time.time()
        self.stats["handshake_timestamp"] = int(time_start)
        self._socket.send(VersionMessage())

        try:
            msg = await self._socket.receive(
                VersionMessage, timeout=self._timeouts.message
            )
        except Exception as e:  # pylint: disable=broad-except
            log.debug(
                "Handshake attempt %d/%d with node %s failed: %s",
                self.stats["handshake_attempts"],
                self.settings.handshake_attempts,
                self,
                repr(e),
            )
            self.stats["handshake_successful"] = False
            return False

        self.stats["handshake_successful"] = True
        self.stats["handshake_duration"] = int((time.time() - time_start) * 1000)
        log.debug(
            "Handshake attempt %d/%d with node %s successful (duration: %dms)",
            self.stats["handshake_attempts"],
            self.settings.handshake_attempts,
            self,
            self.stats["handshake_duration"],
        )
        self._socket.send(SendAddrV2Message())
        self._socket.send(VerAckMessage())
        self._process_version_message(msg)
        return True

    def _process_version_message(self, msg: VersionMessage):
        """Process version message.

        Convert dataclass to dict and change the 'timestamp' key to
        'version_reply_timestamp' to avoid confusion. Add data to self.stats.
        """
        data = asdict(msg)
        data["version_reply_timestamp_remote"] = data.pop("timestamp")
        self.stats.update(data)

    @timing
    async def get_peer_addrs(self) -> list[Address]:
        """Request and receive addresses from node.

        Send 'getaddr' message and receive multiple 'addr' or 'addrv2' messages
        from node for up to 'getaddr' seconds. Stop early when no new 'addr' or
        'addrv2' message is received for 'message' seconds."""

        self.stats.update({"requested_addrs": True})

        try:
            self._socket.send(GetAddrMessage())
            log.debug("Sent getaddr message to %s", self)
        except Exception as e:  # pylint: disable=broad-except
            log.debug("Error sending getaddr message to %s: %s", self, repr(e))

        addresses = set()
        start = int(time.time())
        time_remaining = self._timeouts.getaddr
        while time_remaining > 0:
            timeout = min(time_remaining, self._timeouts.message)
            try:
                msg = await self._socket.receive(
                    AddrMessage, AddrV2Message, timeout=timeout
                )
            except asyncio.TimeoutError:
                log.debug(
                    "Timeout exceeded waiting for addr message of node %s (timeout=%d)",
                    self,
                    timeout,
                )
                break
            except Exception as e:  # pylint: disable=broad-except
                log.debug(
                    "Error while waiting for addr message of node %s: %s",
                    self,
                    repr(e),
                )
                break
            addresses.update(set(msg.addresses))
            time_remaining -= int(time.time() - start)

        self._create_address_statistics(addresses)
        return addresses

    @timing
    def _create_address_statistics(self, addresses):
        """Create simple statistics for addresses received by node.

        Statistics include:
          - total number of addresses
          - number of addresses by network type
        """

        stats = {"advertised_addrs_total": len(addresses)}
        for net in Address.supported_types:
            stats[f"advertised_addrs_{net}"] = len(
                [a for a in addresses if a.type == net]
            )
        self.stats.update(stats)

    def get_stats(self) -> dict[str, str | int | bool]:
        """
        Return relevant statistics.

        The following data is not considered relevant
          - receiver_services: what we sent in version message
          - receiver_ip and receiver_port: crawler's address
          - sender_services: duplicate of services
          - sender_ip and sender_port: often set to zero, duplicate of address
          - handshake_successful: always true for reachable nodes
          - nonce: random number
        """
        stats = {
            "host": self.address.host,
            "port": self.address.port,
            "network": self.address.type,
            "seed_distance": self.seed_distance,
        }

        relevant_stats = [
            "handshake_timestamp",
            "time_connect",
            "handshake_attempts",
            "handshake_duration",
            "version",
            "services",
            "user_agent",
            "latest_block",
            "relay",
            "version_reply_timestamp_remote",
            "requested_addrs",
            "advertised_addrs_total",
            "advertised_addrs_ipv4",
            "advertised_addrs_ipv6",
            "advertised_addrs_onion_v2",
            "advertised_addrs_onion_v3",
            "advertised_addrs_i2p",
            "advertised_addrs_cjdns",
        ]
        for stat in relevant_stats:
            if stat == "requested_addrs":
                stats[stat] = self.stats.get(stat, False)
            elif stat.startswith("advertised_addrs_"):
                stats[stat] = self.stats.get(stat, 0)
            else:
                stats[stat] = self.stats[stat]
        return stats
