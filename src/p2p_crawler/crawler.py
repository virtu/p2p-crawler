"""This module contains the Crawler class, which is responsible for crawling the Bitcoin network."""

import asyncio
import logging as log
import random
import time
from dataclasses import asdict, dataclass, field

from .address import Address
from .config import CrawlerSettings, NodeSettings
from .decorators import print_runtime_stats, timing
from .dnsseeds import get_addresses_from_dns_seeds
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

    @timing
    def update_address_stats(self, addrs):
        """
        Update address statistics.

        For each address received in an `addr` message, log the timestamp when
        the `addr` message was received and when the peer that sent the message
        was last connected to the advertised address.
        """

        now = int(time.time())
        num_added = 0
        num_updated = 0
        for addr in addrs:
            timestamp = addr.timestamp
            age = now - timestamp
            if addr not in self.address_stats:
                self.address_stats[addr] = AddressStats([age], [timestamp])
                num_added += 1
            else:
                stat = self.address_stats[addr]
                stat.ages.append(age)
                stat.timestamps.append(timestamp)
                num_updated += 1
        log.info(
            "Updated address statistics: (total=%d, new=%d, updated=%d)",
            len(self.address_stats),
            num_added,
            num_updated,
        )


@dataclass
class CrawlerNodeSets:
    """Class for different sets of nodes mainted by the crawler.

    Contents:
      - nodes_by_seed: dict with list(!) of nodes from individual dns seeds
        (use list instead of set to detect bugs in DNS requests that might lead
        to duplicate addresses from a DNS seed)
      - reachable: set of nodes confirmed reachable via completed handshake
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

    def init(self, addrs_by_seed: dict[str, list[Address]], settings: NodeSettings):
        """
        Initialize crawler node sets with addresses from DNS seeds.

        The addresses advertised by individual DNS seeds are logged separately
        in `nodes_by_seed`. The set union of all addresses becomes the initial
        set of pending nodes (`pending`).
        """
        for seed, addrs in addrs_by_seed.items():
            nodes = [Node(addr, settings, seed_distance=0) for addr in addrs]
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
    def retry_or_set_unreachable(self, node):
        """If node has retries left, decrement handshake retry counter and
        reinsert node into pending node set so it can be retried later. If
        retries have been used up, mark node as unreachable."""
        if node.has_handshake_attempts_left():
            self.processing.remove(node)
            self.pending.add(node)
        else:
            self.set_unreachable(node)

    @timing
    def add_node_peers(self, node, adv_nodes):
        """
        Add nodes advertised (`adv_nodes`) by `node` to the set of nodes.

        Determines previously unseed nodes (`new_nodes`) by removing known
        nodes from advertised nodes (`adv_nodes`). Applies a threshold to all
        previously unseen nodes to filter out stale (thus likely unreachable)
        nodes. Inserts unseed fresh nodes into set of pending nodes for next
        DNS seed distance (`next`).
        """

        threshold = int(time.time()) - (24 * 60 * 60)
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
        """

        if delay := self.settings.delay_start:
            log.info("Delaying start for %d seconds...", delay)
            time.sleep(delay)

        addrs_by_seed = get_addresses_from_dns_seeds()
        self.nodes.init(addrs_by_seed, self.settings.node_settings)

        tasks = [self.crawler() for _ in range(self.settings.num_workers)]
        tasks.append(self.monitor())
        await asyncio.gather(*tasks)

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
                self.nodes.retry_or_set_unreachable(node)
                continue

            if random.random() < self.settings.node_share:
                await self._get_and_process_peers(node)

            await node.disconnect()
            self.nodes.set_reachable(node)

    @timing
    async def _get_and_process_peers(self, node):
        """
        Obtain and process a node's peers.

        Sends 'getaddr' to peer and wait for `addr` replies. Updates address
        statistics (via `node.update_address_stats()`), then converts addresses
        to nodes and adds suitable ones to set of pending nodes (via
        `node.add_node_peers()`)
        """

        addrs = await node.get_peer_addrs()
        if not addrs:
            return

        self.stats.update_address_stats(addrs)
        peers = {
            Node(
                address=addr,
                settings=self.settings.node_settings,
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
                return

            await asyncio.sleep(5)
