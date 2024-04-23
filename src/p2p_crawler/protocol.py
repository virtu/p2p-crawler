"""Module containing relevant parts of Bitcoin's network protocol."""
import asyncio
import base64
import logging as log
import socket
import time
from dataclasses import dataclass
from hashlib import sha3_256, sha256
from io import BytesIO
from ipaddress import IPv6Address
from random import randint
from typing import ClassVar

from .address import Address

MAINNET_NETWORK_MAGIC = b"\xF9\xBE\xB4\xD9"

BIP_0155_NETWORK_IDS = {
    0x01: ["ipv4", 4],
    0x02: ["ipv6", 16],
    0x03: ["torv2", 10],
    0x04: ["torv3", 32],
    0x05: ["i2p", 32],
    0x06: ["cjdns", 16],
}


class VarInt:
    """Class to handle Bitcoin varints."""

    @staticmethod
    def decode(stream):
        """Decode Bitcoin varint."""
        i = stream.read(1)[0]
        if i == 0xFD:
            return int.from_bytes(stream.read(2), "little")
        if i == 0xFE:
            return int.from_bytes(stream.read(4), "little")
        if i == 0xFF:
            return int.from_bytes(stream.read(8), "little")
        return i

    @staticmethod
    def encode(i):
        """Encode Bitcoin varint."""
        if i < 0xFD:
            return bytes([i])
        if i < 0x10000:
            return b"\xfd" + i.to_bytes(2, "little")
        if i < 0x100000000:
            return b"\xfe" + i.to_bytes(4, "little")
        if i < 0x10000000000000000:
            return b"\xff" + i.to_bytes(8, "little")
        raise ValueError(f"Number too large: {i}")


def decode_user_agent(s):
    """
    Decode user agent.

    Read varint, indicating size of user agent string. If non-zero, read bytes
    and try to decode.
    """
    size = VarInt.decode(s)
    if size == 0:
        return ""
    user_agent_bytes = s.read(size)
    try:
        user_agent = user_agent_bytes.decode("UTF-8")
    except UnicodeDecodeError:
        log.error("Error decoding user agent: %s", user_agent_bytes)
        user_agent = str(user_agent_bytes.hex())
    return user_agent


def hash256(message):
    """Compute double-SHA256 hash."""
    return sha256(sha256(message).digest()).digest()


@dataclass
class NetworkEnvelope:
    """
    Envelope for a Bitcoin network messages.

    Structure:
      - network magic: 4 bytes
      - command (with NULL padding): 12 bytes
      - payload size: 4 bytes (little endian)
      - checksum (first four bytes of hash256 of payload): 4 bytes
      - payload: remaining bytes
    """

    command: str
    payload: bytes
    magic: bytes = MAINNET_NETWORK_MAGIC

    def __repr__(self):
        command = self.command
        payload = self.payload.hex()
        return f"{command}: {payload}"

    @classmethod
    async def parse(cls, s):
        """Deserialize network message envelope."""
        magic = await s.readexactly(4)
        if magic != MAINNET_NETWORK_MAGIC:
            log.error("Wrong magic: %s", magic.hex())
        command = (await s.readexactly(12)).rstrip(b"\x00").decode("ASCII")
        payload_size = int.from_bytes(await s.readexactly(4), "little")
        checksum = await s.readexactly(4)
        payload = await s.readexactly(payload_size)
        expected_checksum = hash256(payload)[:4]
        if checksum != expected_checksum:
            log.error(
                "Checksum mismatch: sent=%s, computed=%s",
                expected_checksum.hex(),
                checksum.hex(),
            )

        return cls(command, payload)

    def serialize(self):
        """Serialize network message envelope."""
        ser = self.magic
        ser += self.command.encode("ASCII") + b"\00" * (12 - len(self.command))
        ser += len(self.payload).to_bytes(4, "little")
        ser += hash256(self.payload)[:4]
        ser += self.payload
        return ser

    def stream(self):
        """Return a stream to the payload."""
        return BytesIO(self.payload)


@dataclass
class VersionMessage:  # pylint: disable=too-many-instance-attributes
    """Class for 'version' message.

    Structure:
      - version: 4 bytes (little endian)
      - services (bitfield of features to enable for connection): 8 bytes (little endian)
      - timestamp (seconds since epoch): 8 bytes (little endian)
      - receiver of message: 26 bytes
        - receiver services: 8 bytes (little endian)
        - receiver ip: 16 bytes
        - receiver port: 2 bytes (big endian)
      [fields below require version >= 106]
      - sender of message: 26 bytes
        - sender services: 8 bytes (little endian)
        - sender ip: 16 bytes
        - sender port: 2 bytes (big endian)
      - nonce (randomly generated for each msg): 8 bytes (little endian)
      - user agent: variable
        - length: varint
        - user agent string: length bytes (see line above)
      - latest block (seen by message sender): 4 bytes (little endian)
      [fields below require version >= 70001]
      - relay (whether peer should announce relayed transactions): 1 byte

    """

    command: ClassVar[str] = "version"
    version: int = 70015
    services: int = 0  # 1033 for NODE_NETWORK, NODE_SEGWIT, NODE_NETWORK_LIMITED
    timestamp: int = int(time.time())
    receiver_services: int = 0
    receiver_ip: IPv6Address = IPv6Address("::ffff:0.0.0.0")
    receiver_port: int = 0
    sender_services: int = 0
    sender_ip: IPv6Address = IPv6Address("::ffff:0.0.0.0")
    sender_port: int = 0
    nonce: int = randint(0, 2**64)
    user_agent: str = "/Satoshi:23.0.0/"
    latest_block: int = 0
    relay: bool = False

    @classmethod
    def parse(cls, s):  # pylint: disable=too-many-locals
        """Deserialize version message."""

        version = int.from_bytes(s.read(4), "little")
        services = int.from_bytes(s.read(8), "little")
        timestamp = int.from_bytes(s.read(8), "little")
        receiver_services = int.from_bytes(s.read(8), "little")
        receiver_ip = IPv6Address(s.read(16))
        receiver_port = int.from_bytes(s.read(2), "big")
        if version < 106:
            return cls(
                version,
                services,
                timestamp,
                receiver_services,
                receiver_ip,
                receiver_port,
            )

        sender_services = int.from_bytes(s.read(8), "little")
        sender_ip = IPv6Address(s.read(16))
        sender_port = int.from_bytes(s.read(2), "big")
        nonce = int.from_bytes(s.read(8), "little")
        user_agent = decode_user_agent(s)
        latest_block = int.from_bytes(s.read(4), "little")
        if version < 70001:
            return cls(
                version,
                services,
                timestamp,
                receiver_services,
                receiver_ip,
                receiver_port,
                sender_services,
                sender_ip,
                sender_port,
                nonce,
                user_agent,
                latest_block,
            )

        relay = bool(int.from_bytes(s.read(1), "little"))
        return cls(
            version,
            services,
            timestamp,
            receiver_services,
            receiver_ip,
            receiver_port,
            sender_services,
            sender_ip,
            sender_port,
            nonce,
            user_agent,
            latest_block,
            relay,
        )

    def serialize(self):
        """Serialize version message."""
        ser = self.version.to_bytes(4, "little")
        ser += self.services.to_bytes(8, "little")
        ser += self.timestamp.to_bytes(8, "little")
        ser += self.receiver_services.to_bytes(8, "little")
        ser += self.receiver_ip.packed
        ser += self.receiver_port.to_bytes(2, "big")
        ser += self.sender_services.to_bytes(8, "little")
        ser += self.sender_ip.packed
        ser += self.sender_port.to_bytes(2, "big")
        ser += self.nonce.to_bytes(8, "little")
        ser += VarInt.encode(len(self.user_agent))
        ser += self.user_agent.encode("UTF-8")
        ser += self.latest_block.to_bytes(4, "little")
        ser += b"\x01" if self.relay else b"\x00"  # 01 for relay, 00 for no relay
        return ser


class SimpleMessage:
    """
    Base class for simple messages.

    Simple messages have no payload apart from a command. This base class
    includes dummy parse() and serialization() methods.
    """

    @classmethod
    def parse(cls, _):
        """Dummy parse method."""
        return cls()

    def serialize(self):
        """Dummy serialize method."""
        return b""


@dataclass
class GetAddrMessage(SimpleMessage):
    """Class for 'getaddr' message."""

    command: ClassVar[str] = "getaddr"


@dataclass
class SendAddrV2Message(SimpleMessage):
    """Class for 'sendaddrv2' message."""

    command: ClassVar[str] = "sendaddrv2"


@dataclass
class VerAckMessage(SimpleMessage):
    """Class for 'verack' message."""

    command: ClassVar[str] = "verack"


@dataclass
class PingMessage:
    """
    Class for 'ping' message.

    Structure:
      - nonce (randomly generated for each ping): 8 bytes (little endian)
    """

    command: ClassVar[str] = "ping"
    nonce: int = randint(0, 2**64)

    @classmethod
    def parse(cls, s):
        """Deserialize ping message."""
        nonce = int.from_bytes(s.read(8), "little")
        return cls(nonce)

    def serialize(self):
        """Serialize ping message."""
        return self.nonce.to_bytes(8, "little")


@dataclass
class PongMessage:
    """
    Class for 'pong' message.

    Structure:
      - nonce (taken from corresponding ping): 8 bytes (little endian)
    """

    command: ClassVar[str] = "pong"
    nonce: int

    @classmethod
    def parse(cls, s):
        """Deserialize pong message."""
        nonce = int.from_bytes(s.read(8), "little")
        return cls(nonce)

    def serialize(self):
        """Serialize pong message."""
        return self.nonce.to_bytes(8, "little")


@dataclass
class AddrMessage:
    """
    Class for 'addr' message.

    Structure:
      - number of addresses: varint
      - address list, each entry comprising:
        - timestamp (last successful connection): 4 bytes (only if version >= 31402)
        - services: 8 bytes (little endian)
        - ip: 16 bytes (ipv4-mapped ipv6 address)
        - port: 2 bytes (big endian)
    """

    command: ClassVar[str] = "addr"
    addresses: list[Address]

    @classmethod
    def parse(cls, s):
        """
        Deserialize 'addr' message.

        In theory, the node version is required to determine whether address
        records contain a timestamp or not (version >= 31402), but since nodes
        that old are no longer around, timestamps are assumed implicitly.
        """
        try:
            num_addresses = VarInt.decode(s)
        except asyncio.IncompleteReadError:
            log.info("Error deserializing number of addresses in addr message")
            return []

        addresses = []
        for _ in range(num_addresses):
            timestamp = int.from_bytes(s.read(4), "little")
            _ = s.read(8)
            ip = IPv6Address(s.read(16))
            ip_str = str(ip.ipv4_mapped) if ip.ipv4_mapped else str(ip)
            port = int.from_bytes(s.read(2), "big")
            addresses.append(Address(ip_str, port, timestamp))
        return cls(addresses)


@dataclass
class AddrV2Message:
    """
    Class for 'addrv2' message.

    Structure:
      - number of addresses: varint

      - address list, each entry comprising:
        - timestamp (last successful connection): 4 bytes
        - services: varint
        - network (network type specifier): 1 byte
        - addr: size depends on network type
        - port: 2 bytes (big endian)
    """

    command: ClassVar[str] = "addrv2"
    addresses: list[Address]

    @staticmethod
    def decode_address(addr_type, addr_data) -> str:
        """Decode address data according to network type."""
        if addr_type == "ipv4":
            return socket.inet_ntop(socket.AF_INET, addr_data)

        if addr_type == "ipv6":
            ip = IPv6Address(addr_data)
            return str(ip.ipv4_mapped) if ip.ipv4_mapped else str(ip)

        if addr_type == "torv2":
            permanent_id = addr_data
            return base64.b32encode(permanent_id).decode("ascii").lower() + ".onion"

        if addr_type == "torv3":
            pubkey, version = addr_data, b"\x03"
            checksum = sha3_256(
                str.encode(".onion checksum") + pubkey + version
            ).digest()[:2]
            return (
                base64.b32encode(pubkey + checksum + version).decode("ascii").lower()
                + ".onion"
            )

        if addr_type == "i2p":
            return (
                base64.b32encode(addr_data).decode("ascii").lower().replace("=", "")
                + ".b32.i2p"
            )

        if addr_type == "cjdns":
            addr = socket.inet_ntop(socket.AF_INET6, addr_data)
            log.warning("CJDNS addresses currently unsupported: %s", addr)
            return addr

        raise ValueError("decode_address(): unsupported address type")

    @staticmethod
    def extract_address(stream) -> Address:
        """Extract a single address from addrv2 message."""
        timestamp = int.from_bytes(stream.read(4), "little")
        _ = VarInt.decode(stream)
        network_id = int.from_bytes(stream.read(1), byteorder="big", signed=False)
        addr_type, exp_addr_size = BIP_0155_NETWORK_IDS[network_id]
        act_addr_size = VarInt.decode(stream)
        if act_addr_size != exp_addr_size:
            raise ValueError(
                f"addr size inconsistency: network_id={network_id}, "
                f"addr_type={addr_type}, expected_size={exp_addr_size}, actual_size={act_addr_size}"
            )
        addr_data = stream.read(act_addr_size)
        addr = AddrV2Message.decode_address(addr_type, addr_data)
        port = int.from_bytes(stream.read(2), "big")
        return Address(addr, port, timestamp)

    @classmethod
    def parse(cls, stream):
        """Deserialize 'addrv2' message."""
        try:
            num_addresses = VarInt.decode(stream)
        except asyncio.IncompleteReadError:
            log.info("error parsing addrv2 msg (num_addresses): got 0 addresses")
            return []

        addresses = []
        for _ in range(num_addresses):
            try:
                address = AddrV2Message.extract_address(stream)
            except (asyncio.IncompleteReadError, KeyError, ValueError) as e:
                log.info(
                    "error parsing addrv2 msg: %s (%s): got %d/%d addresses",
                    e,
                    repr(e),
                    len(addresses),
                    num_addresses,
                )
                break
            addresses.append(address)

        return cls(addresses)
