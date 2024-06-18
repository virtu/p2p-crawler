"""This module contains the 'Address' and 'Socket' classes that handle network connections."""

import asyncio
import logging as log
import time
from dataclasses import dataclass, field
from typing import ClassVar

import i2plib
from python_socks.async_.asyncio import Proxy

from .address import Address
from .config import NetworkSettings
from .protocol import NetworkEnvelope, PingMessage, PongMessage


@dataclass
class Socket:
    """Class to represent connections to Bitcoin nodes."""

    network_settings: NetworkSettings
    connected: bool = False
    stats: dict[str, int] = field(default_factory=dict)
    _reader: asyncio.StreamReader = field(init=False)
    _writer: asyncio.StreamWriter = field(init=False)
    i2p_session_id: ClassVar = None

    def send(self, message):
        """Send message via socket."""
        envelope = NetworkEnvelope(message.command, message.serialize())
        self._writer.write(envelope.serialize())

    async def receive(self, *message_classes, timeout: int):
        """Receive message via socket."""
        command = None
        command_to_class = {m.command: m for m in message_classes}
        while command not in command_to_class.keys():
            fut = NetworkEnvelope.parse(self._reader)
            envelope = await asyncio.wait_for(fut, timeout=timeout)
            command = envelope.command
            if command == PingMessage.command:
                self.send(PongMessage(PingMessage.nonce))
        try:
            parsed = command_to_class[command].parse(envelope.stream())
        except Exception as e:
            raise Exception(f"Parsing command {command} failed: {e}", command, e) from e
        return parsed

    async def disconnect(self, timeout=1):
        """
        Disconnect from address.

        All data has been collected so default to a timeout of 1.
        """
        self._writer.close()
        fut = self._writer.wait_closed()
        await asyncio.wait_for(fut, timeout=timeout)

    async def connect(self, addr: Address, timeout: int):
        """Connect to address using approropriate proxies and timeouts."""
        log.debug("Trying to open connection to %s (timeout=%d)...", addr, timeout)

        time_start = time.time()

        if addr.is_ip:
            await self._connect_ip(addr, timeout)
        elif addr.is_onion:
            await self._connect_onion(addr, timeout)
        elif addr.is_i2p:
            await self._connect_i2p(addr, timeout)
        elif addr.is_cjdns:
            await self._connect_ip(addr, timeout)
        else:
            raise NotImplementedError(f"unsupported address type: {addr}")

        self.stats["time_connect"] = int((time.time() - time_start) * 1000)

        log.debug("Opened connection to %s in %dms", addr, self.stats["time_connect"])

    async def _connect_ip(self, addr: Address, timeout: int):
        """Connect to an IPv4 or IPv6 (including CJDNS) node."""
        fut = asyncio.open_connection(addr.host, addr.port)
        self._reader, self._writer = await asyncio.wait_for(fut, timeout=timeout)

    async def _connect_onion(self, addr: Address, timeout: int):
        """Connect to Onion v2/v3 node."""
        conf = self.network_settings
        proxy = Proxy.from_url(f"socks5://{conf.tor_proxy_host}:{conf.tor_proxy_port}")
        fut = proxy.connect(dest_host=addr.host, dest_port=addr.port, timeout=timeout)
        sock = await asyncio.wait_for(fut, timeout=timeout)
        fut = asyncio.open_connection(sock=sock)
        self._reader, self._writer = await asyncio.wait_for(fut, timeout=timeout)

    async def _get_i2p_session_id(self):
        """Return I2P session. Create session if it does not exist yet."""
        if Socket.i2p_session_id:
            return Socket.i2p_session_id

        ns = self.network_settings
        sid = i2plib.utils.generate_session_id()
        await i2plib.create_session(sid, sam_address=(ns.i2p_sam_host, ns.i2p_sam_port))
        Socket.i2p_session_id = sid
        return sid

    async def _connect_i2p(self, addr: Address, timeout: int):
        """Connect to I2P node."""
        conf = self.network_settings
        fut = i2plib.stream_connect(
            await self._get_i2p_session_id(),
            addr.host,
            sam_address=(conf.i2p_sam_host, conf.i2p_sam_port),
        )
        self._reader, self._writer = await asyncio.wait_for(fut, timeout=timeout)
