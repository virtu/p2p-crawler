"""This module contains the Crawler class, which is responsible for crawling the Bitcoin network."""

import asyncio
import logging as log
import random
import time
from dataclasses import asdict, dataclass, field

import maillog

from .address import Address
from .config import CrawlerSettings
from .decorators import print_runtime_stats, timing
from .dnsseeds import get_addresses_from_dns_seeds
from .history import History
from .node import Node


@dataclass
class AddressStats:
    """Address statistics."""

    ages: list[int]
    timestamps: list[int]

    def to_dict(self):
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class CrawlerStatistics:
    """Class for crawler statistics."""

    num_processed_nodes: int = 0
    time_started: int = int(time.time())
    runtime: int = field(init=False)
    address_stats: dict[Address, AddressStats] = field(default_factory=dict)


@dataclass
class CrawlerNodeSets:
    """Class for different sets of nodes mainted by the crawler.

    Contents:
      - nodes_by_seed: dict with list(!) of nodes from individual dns seeds
        (use list instead of set to detect bugs in DNS requests that might lead
        to duplicate addresses from a DNS seed)
      - reachable: set of nodes confirmed reachable via established connection
      - unreachable: set of nodes confirmed unreachable
      - pending: set of nodes currently pending processing (current seed distance)
      - next: set of nodes pending processing once current seed distance is done
      - processing: set of nodes currently being processed (required to avoid
        re-adding a node that is currently getting processed and thus neither
        in any of the pending or labeled sets; also used in code for switching
        between pending and next node sets)
      - address_stats: dict with Address keys and AddressStats values
    """

    nodes_by_seed: dict[str, list[Node]] = field(default_factory=dict)
    reachable: set[Node] = field(default_factory=set)
    unreachable: set[Node] = field(default_factory=set)
    pending: set[Node] = field(default_factory=set)
    next: set[Node] = field(default_factory=set)
    processing: set[Node] = field(default_factory=set)

    def init(self, addrs_by_seed: dict[str, list[Address]]):
        """
        Initialize crawler node sets with addresses from DNS seeds.

        The addresses advertised by individual DNS seeds are logged separately
        in `nodes_by_seed`. The set union of all addresses becomes the initial
        set of pending nodes (`pending`).
        """
        for seed, addrs in addrs_by_seed.items():
            nodes = [Node(addr, seed_distance=0) for addr in addrs]
            self.nodes_by_seed[seed] = nodes
            self.pending |= set(nodes)
        log.debug(
            "pending nodes initialized with %d nodes from DNS seeds.", len(self.pending)
        )

    async def nodes_left(self) -> bool:
        """
        Return whether work is left or not.

        Return true if there are any currently pending nodes in `pending`.

        If there are no more pending nodes but crawlers are still active
        (`processing`), wait for 5s for as long as necessary until all crawlers
        have finished adding to the `next` set. At some point, there will be no
        more pending nodes and no more active crawlers, leading to the `next`
        set becoming the `pending` set. Thus, check the `pending` set to exit
        the `processing` waiting loop.

        Once there are no more currently pending nodes, no more active
        crawlers, and no more future pending nodes, return False.
        """

        if self.pending:
            return True

        while self.processing:
            log.debug(
                "No pending nodes but %d other crawler(s) still active: waiting 5s...",
                len(self.processing),
            )
            log.debug("Processing: %s", self.processing)
            await asyncio.sleep(5)
            if self.pending:
                return True

        if self.next:
            log.info("Switching pending nodes to next seed distance.")
            self.pending = self.next
            self.next = set()
            return True

        return False

    @timing
    def get_node(self) -> Node:
        """
        Get a random node for processing.

        Nodes are always selected from the set of currently pending nodes
        (`pending`). Switching pending node sets is done in `nodes_left()`.
        """

        node = random.choice(tuple(self.pending))
        self.processing.add(node)
        self.pending.remove(node)
        return node

    @timing
    def set_reachable(self, node):
        """Mark node reachable and remove it from processing node set."""
        self.processing.remove(node)
        self.reachable.add(node)

    @timing
    def set_unreachable(self, node):
        """Mark node unreachable and remove it from processing node set."""
        self.processing.remove(node)
        self.unreachable.add(node)

    @timing
    def retry_or_give_up(self, node):
        """If node has retries left, decrement handshake retry counter and
        reinsert node into pending node set so it can be retried later. If
        retries have been used up, give up (i.e., don't attempt another
        handshake; however, mark node as reachable because a connection could
        be established)."""
        if node.has_handshake_attempts_left():
            self.processing.remove(node)
            self.pending.add(node)
        else:
            self.set_reachable(node)

    @timing
    def add_node_peers(self, node, adv_nodes):
        """
        Add nodes advertised (`adv_nodes`) by `node` to the set of nodes.

        Determines previously unseen nodes (`new_nodes`) by removing known
        nodes from advertised nodes (`adv_nodes`). Applies a threshold to all
        previously unseen nodes to filter out stale (thus likely unreachable)
        nodes. Inserts unseen fresh nodes into set of pending nodes for next
        DNS seed distance (`next`).
        """

        threshold = int(time.time()) - (2 * 24 * 60 * 60)
        known_nodes = (
            self.reachable
            | self.unreachable
            | self.pending
            | self.next
            | self.processing
        )
        new_nodes = adv_nodes - known_nodes
        fresh_new_nodes = {n for n in new_nodes if n.address.timestamp > threshold}
        self.next.update(fresh_new_nodes)
        log.info(
            "Added %d node(s) advertised by %s (total=%d, known=%d, new_stale=%d)",
            len(fresh_new_nodes),
            node,
            len(adv_nodes),
            len(adv_nodes) - len(new_nodes),
            len(new_nodes) - len(fresh_new_nodes),
        )


@dataclass
class Crawler:
    """Class for crawling logic."""

    settings: CrawlerSettings
    nodes: CrawlerNodeSets = field(default_factory=CrawlerNodeSets)
    stats: CrawlerStatistics = field(default_factory=CrawlerStatistics)

    async def run(self):
        """
        Run the node crawler.

        If desired, the crawler will wait by `delay_start` seconds (e.g., to
        wait for Tor and/or I2P Docker containers to be ready).

        Initially, the crawler will request addresses from the DNS seeds to
        bootstrap its node sets. Next, `num_workers` crawler instances are
        launched along with a monitoring thread.

        If the `--reachable-node-history` command-line option is set, nodes
        discovered during previous runs but not during this run will be tried
        next.
        """

        if delay := self.settings.delay_start:
            log.info("Delaying start for %d seconds...", delay)
            time.sleep(delay)

        Node.configure(self.settings.node_settings)
        addrs_by_seed = get_addresses_from_dns_seeds()
        self.nodes.init(addrs_by_seed)

        tasks = [self.crawler() for _ in range(self.settings.num_workers)]
        tasks.append(self.monitor())
        await asyncio.gather(*tasks)

        if self.settings.result_settings.history_settings.enable:
            history = History(
                settings=self.settings.result_settings.history_settings,
                version=self.settings.version_info.version,
                timestamp=self.settings.result_settings.timestamp,
            )
            historical_nodes = history.get_reachable_nodes()
            historical_reached = historical_nodes & self.nodes.reachable
            historical_not_reached = historical_nodes & self.nodes.unreachable
            historical_unseen = (
                historical_nodes - historical_reached - historical_not_reached
            )
            log.info(
                "Read %d historical nodes (reached=%d, not_reached=%d, unseen=%d)",
                len(historical_nodes),
                len(historical_reached),
                len(historical_not_reached),
                len(historical_unseen),
            )
            self.nodes.pending |= historical_unseen
            tasks = [self.crawler() for _ in range(self.settings.num_workers)]
            tasks.append(self.monitor())
            await asyncio.gather(*tasks)
            history.update_and_persist(reachable_nodes_now=self.nodes.reachable)

        print_runtime_stats()
        log.info(
            "Processed %d nodes in %.1fs: reachable=%d, unreachable=%d",
            self.stats.num_processed_nodes,
            self.stats.runtime,
            len(self.nodes.reachable),
            len(self.nodes.unreachable),
        )

    async def crawler(self):
        """
        Crawling loop executed by each worker.

        If there are nodes to process left, a crawler will obtain a random node
        from the set of unprocessed nodes. The crawler then tries to connect
        and carry out a handshake with the node. Next, addresses are solicited
        from the node depending on the the `node_share` setting (i.e., the
        share of reachable nodes to ask for known addresses via a `getaddr`
        message).
        """

        while True:
            if not await self.nodes.nodes_left():
                log.debug("No more nodes left: exiting!")
                return

            node = self.nodes.get_node()
            success = await node.connect()
            self.stats.num_processed_nodes += 1
            if not success:
                await node.disconnect()
                self.nodes.set_unreachable(node)
                continue

            success = await node.handshake()
            if not success:
                await node.disconnect()
                self.nodes.retry_or_give_up(node)
                continue

            if random.random() < self.settings.node_share:
                await self._get_and_process_peers(node)

            await node.disconnect()
            self.nodes.set_reachable(node)

    @timing
    def _write_addr_data(self, node: Node, addrs: list[Address]):
        """
        Record hashes of addresses provided by each node.

        Data is written using a custom format to preserve space.
        The header is a magic string followed by a version byte, a 4-byte epoch
        timestamp (used to reconstruct address seen_by timestamps) and a newline.

        Node records consist of the length of the node string as varint followed by the node string.
        The addr data for each node record consists of the number of address
        records encoded as varint, followed by address record. Each address
        record consists of a varint that holds the address id shifted by three
        bits to the left and ANDed with the network_id, as well as
        a zigzag+varint-encoded timestamp delta.

        All text is encoded using ascii; numbers are encoded using big endian.
        When the crawler finishes running, 'EOF' is inserted at the end of the
        file.
        """

        def to_varint(value: int) -> bytes:
            """Encode an integer as varint."""
            buf = bytearray()
            while value > 0x7F:
                buf.append((value & 0x7F) | 0x80)
                value >>= 7
            buf.append(value)
            return buf

        with open(self.settings.result_settings.addr_data, "ab") as f:
            data = b""
            # header
            if f.tell() == 0:
                magic = "p2p-addr-data".encode("ascii")
                version = 1
                epoch = Address._epoch
                data += magic
                data += version.to_bytes(1, "big")
                data += epoch.to_bytes(4, "big")
                data += "\n".encode("ascii")

            # node that sent the addr reply
            data += to_varint(len(str(node.address)))
            data += str(node.address).encode("ascii")

            # number of records, followed by records
            data += to_varint(len(addrs))
            for addr in addrs:
                addr_id, addr_timestamp_delta_zigzag, net_id = addr.compress()
                addr_net_id = (addr_id << 3) | net_id
                data += to_varint(addr_net_id)
                data += to_varint(addr_timestamp_delta_zigzag)
            data += "\n".encode("ascii")
            f.write(data)

    @timing
    async def _get_and_process_peers(self, node):
        """
        Obtain and process a node's peers.

        Sends 'getaddr' to peer and wait for `addr` replies. Converts addresses
        from 'addr' messages to `Node`s and adds suitable ones to set of
        pending nodes (via `node.add_node_peers()`).

        Optional:
        - If `--record-addr-data` is set, write addr data provided by each node
          into a (compressed) file.
        """

        addrs = await node.get_peer_addrs()
        if not addrs:
            return

        if self.settings.record_addr_data:
            self._write_addr_data(node, addrs)

        peers = {
            Node(
                address=addr,
                seed_distance=node.seed_distance + 1,
            )
            for addr in addrs
        }
        self.nodes.add_node_peers(node, peers)

    async def monitor(self):
        """Output status information every five seconds. Return when no more crawlers are active"""
        while True:
            log.info(
                "[STATUS] Elapsed time: %.1fh Nodes: %d active, %d unreachable, %d pending, %d processing",
                (time.time() - self.stats.time_started) / 3600,
                len(self.nodes.reachable),
                len(self.nodes.unreachable),
                len(self.nodes.pending) + len(self.nodes.next),
                len(self.nodes.processing),
            )

            if not (self.nodes.pending or self.nodes.processing or self.nodes.next):
                log.info("[STATUS] No more nodes and no more active crawlers: exiting")
                self.stats.runtime = int(time.time() - self.stats.time_started)
                if self.stats.runtime > (12 * 3600):
                    log.warning(
                        "Crawler runtime of %.1fh exceeded 12 hours.",
                        self.stats.runtime / 3600,
                    )
                return

            await asyncio.sleep(5)
