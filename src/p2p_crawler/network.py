"""This module contains the 'Address' and 'Socket' classes that handle network connections."""

import asyncio
import logging as log
import time
from dataclasses import dataclass, field

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

    async def disconnect(self):
        """Disconnect from address."""
        self._writer.close()

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
            raise NotImplementedError(f"cjdns currently unsupported: {addr}")
        else:
            raise NotImplementedError(f"unsupported address type: {addr}")

        self.stats["time_connect"] = int((time.time() - time_start) * 1000)

        log.debug(
            "Opened connection to %s in %dms (proxy: %dms)",
            addr,
            self.stats["time_connect"],
            self.stats["time_connect_proxy"],
        )

    async def _connect_ip(self, addr: Address, timeout: int):
        """Connect to IPv4/IPv6 node."""
        self.stats["time_connect_proxy"] = 0
        fut = asyncio.open_connection(addr.host, addr.port)
        self._reader, self._writer = await asyncio.wait_for(fut, timeout=timeout)

    async def _connect_onion(self, addr: Address, timeout: int):
        """Connect to Onion v2/v3 node."""
        time_start = time.time()
        conf = self.network_settings
        proxy = Proxy.from_url(f"socks5://{conf.tor_proxy_host}:{conf.tor_proxy_port}")
        fut = proxy.connect(dest_host=addr.host, dest_port=addr.port, timeout=timeout)
        sock = await asyncio.wait_for(fut, timeout=timeout)
        self.stats["time_connect_proxy"] = int((time.time() - time_start) * 1000)
        fut = asyncio.open_connection(sock=sock)
        self._reader, self._writer = await asyncio.wait_for(fut, timeout=timeout)

    async def _connect_i2p(self, addr: Address, timeout: int):
        """Connect to I2P node."""
        time_start = time.time()
        sid = i2plib.utils.generate_session_id()
        conf = self.network_settings
        fut = i2plib.create_session(
            sid, sam_address=(conf.i2p_sam_host, conf.i2p_sam_port)
        )
        await asyncio.wait_for(fut, timeout=timeout)
        self.stats["time_connect_proxy"] = int((time.time() - time_start) * 1000)
        fut = i2plib.stream_connect(
            sid, addr.host, sam_address=(conf.i2p_sam_host, conf.i2p_sam_port)
        )
        self._reader, self._writer = await asyncio.wait_for(fut, timeout=timeout)
