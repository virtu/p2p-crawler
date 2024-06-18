"""Module for dealing with node data from previous runs."""

import bz2
import json
import logging as log
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .address import Address
from .config import CrawlerSettings
from .node import Node


@dataclass
class History:
    """
    Class for handling reachable node data from previous runs.

    Uses bz2-compressed JSON format, with `_metadata` as key for a metadata
    dict (featuring `last_run` and `version`) and `reachable_nodes` as key for
    a node dict (with node addresses as keys to dicts containing `network_type`
    and `retries_left`).
    """

    settings: CrawlerSettings
    history_path: Path = field(init=False)

    def __post_init__(self):
        """Read data from the reachable nodes history JSON file."""
        self.history_settings = self.settings.result_settings.history_settings
        self.history_path = Path(f"{self.history_settings.path}.bz2")
        try:
            with bz2.open(self.history_path, "rt") as file:
                self.data = json.load(file)
                log.debug(
                    "Read reachable nodes history (last_run=%s, version=%s)",
                    self.data["_metadata"]["last_run"],
                    self.data["_metadata"]["version"],
                )
        except FileNotFoundError:
            log.warning("History file %s not found.", self.history_path)
            self.data = {"_metadata": {"stats": []}, "reachable_nodes": {}}

    def get_reachable_nodes(self) -> set[Node]:
        """Return list of reachable nodes from previous runs."""

        if not self.data["reachable_nodes"]:
            return set()

        reachable_nodes_history = set(
            Node(
                address=Address.from_str(addr),
                settings=self.settings.node_settings,
                seed_distance=100,
            )
            for addr in self.data["reachable_nodes"]
        )
        return reachable_nodes_history

    def update_and_persist(self, reachable_nodes_now: set[Node]):
        """
        Update and store the reachable node history.
        1. Update reachable node history
            - Identify and add new nodes to history
            - Decrement retries_left for unreachable nodes, removing them when appropriate
            - Reset retries_left for reachable nodes
        2. Update metadata
            - Update last_run and version
            - Append statistics
        3. Persist history to file
        """

        reachable_nodes_history = self.get_reachable_nodes()
        max_retries = self.history_settings.max_retries

        # add reachable nodes not seen previously to history
        new_nodes = reachable_nodes_now - reachable_nodes_history
        for new_node in new_nodes:
            address = str(new_node.address)
            self.data["reachable_nodes"][address] = {
                "network_type": new_node.address.type,
                "retries_left": max_retries,
            }

        # decrement retries for previously seen historical nodes that were unreachable during this run
        unreachable_nodes = reachable_nodes_history - reachable_nodes_now
        num_removed = 0
        for unreachable_node in unreachable_nodes:
            address = str(unreachable_node.address)
            self.data["reachable_nodes"][address]["retries_left"] -= 1
            if self.data["reachable_nodes"][address]["retries_left"] == 0:
                del self.data["reachable_nodes"][address]
                num_removed += 1

        # reset retries for previously seen historical nodes that were reachable during this run
        nodes_to_reset = reachable_nodes_history - unreachable_nodes
        for node_to_reset in nodes_to_reset:
            address = str(node_to_reset.address)
            self.data["reachable_nodes"][address]["retries_left"] = max_retries

        # update metadata
        self.data["_metadata"]["last_run"] = self.settings.result_settings.timestamp
        self.data["_metadata"]["version"] = self.settings.version_info.version
        num_net_type = defaultdict(int)
        for addr_stats in self.data["reachable_nodes"].values():
            net_type = addr_stats["network_type"]
            num_net_type[net_type] += 1
        num_net_type_ordered = dict(sorted(num_net_type.items()))
        stats = {self.settings.result_settings.timestamp: num_net_type_ordered}
        self.data["_metadata"]["stats"].append(stats)

        # persist and output stats
        with bz2.open(self.history_path, "wt") as file:
            json.dump(self.data, file, indent=4, sort_keys=True)
        log.info(
            "Updated reachable nodes history (added=%d "
            "[ipv4=%d, ipv6=%d, onion=%d, i2p=%d, cjdns=%d], "
            "retries_reset=%d, retries_decr=%d, removed=%d, old_hist_size=%d, new_hist_size=%d)",
            len(new_nodes),
            num_net_type["ipv4"],
            num_net_type["ipv6"],
            num_net_type["onion_v2"] + num_net_type["onion_v3"],
            num_net_type["i2p"],
            num_net_type["cjdns"],
            len(nodes_to_reset),
            len(unreachable_nodes),
            num_removed,
            len(reachable_nodes_history),
            len(self.data["reachable_nodes"]),
        )
