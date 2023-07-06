"""Module for persisting crawler output."""

import bz2
import json
import logging as log
import os
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from address import Address
from config import LogSettings, ResultSettings
from google.cloud import storage

from crawler import Crawler


@dataclass
class Output:
    """Class to persist crawler results."""

    result_settings: ResultSettings
    log_settings: LogSettings
    crawler: Crawler

    @staticmethod
    def dict_to_bz2(path: Path, data: dict):
        """Write `data` to `path`."""
        time_start = time.time()
        data_bytes = json.dumps(data, indent=4, default=str).encode()
        with bz2.open(path, "wb") as f:
            f.write(data_bytes)
        runtime = time.time() - time_start
        log.info(
            "Wrote %s (size=%.1fkB, uncompressed=%.1fkB, ratio=%.1f, runtime=%.1fs)",
            path,
            path.stat().st_size / 1024,
            len(data_bytes) / 1024,
            len(data_bytes) / path.stat().st_size,
            runtime,
        )

    def persist(self):
        """
        Persist results.

        Depending on settings, this may include storing results locally as well
        as to GCS.
        """

        self.write_files()
        if self.result_settings.store_to_gcs:
            self.upload_files_to_gcs()

    def write_files(self):
        """Persist files to filesystem."""

        self.write_address_statistics()
        self.write_crawler_statistics()
        self.write_reachable_nodes()
        if self.log_settings.store_debug_log:
            self.compress_debug_log()

    def write_address_statistics(self):
        """
        Write address statistics.

        Convert dict's keys of type Address to string, and its values of type
        AddressStats (dataclass) to dict.
        """

        dest = Path(f"{self.result_settings.address_stats}.bz2")
        address_stats = self.crawler.stats.address_stats
        json_compatible_dict = {str(k): v.to_dict() for k, v in address_stats.items()}
        Output.dict_to_bz2(dest, json_compatible_dict)

    def write_crawler_statistics(self):
        """
        Write crawler statistics.

        Includes:
          - crawler settings
          - internal crawler statistics (time started, runtime, processed nodes)
          - number of advertised nodes (via addr messages)
          - dns seed data (node count and list)
          - reachable and unreachable node data (node count and list)
        """

        def get_node_count_stats(nodes) -> dict[str, int]:
            """
            Return node count statistics as dict.

            Includes total number of nodes, number of unknown nodes, and number of nodes of different network types.
            """
            networks = Address.supported_types
            result = {
                "total": len(nodes),
                "unknown": len([n for n in nodes if n.address.type not in networks]),
            }
            for net in networks:
                result[net] = len([n for n in nodes if n.address.type == net])
            return result

        crawler_data = {
            "crawler_settings": self.crawler.settings.to_dict(),
            "time_started": time.strftime(
                "%Y-%m-%dT%H-%M-%SZ", time.gmtime(self.crawler.stats.time_started)
            ),
            "runtime_seconds": self.crawler.stats.runtime,
            "num_processed_nodes": self.crawler.stats.num_processed_nodes,
            "num_reachable": get_node_count_stats(self.crawler.nodes.reachable),
            "num_unreachable": get_node_count_stats(self.crawler.nodes.unreachable),
            "num_advertised": len(self.crawler.stats.address_stats),
            "num_nodes_from_seed": {
                seed: get_node_count_stats(nodes)
                for seed, nodes in self.crawler.nodes.nodes_by_seed.items()
            },
            "list_reachable": [str(node) for node in self.crawler.nodes.reachable],
            "list_unreachable": [str(node) for node in self.crawler.nodes.unreachable],
            "list_nodes_from_seed": {
                seed: [str(node) for node in nodes]
                for seed, nodes in self.crawler.nodes.nodes_by_seed.items()
            },
        }

        dest = Path(f"{self.result_settings.crawler_stats}.bz2")
        Output.dict_to_bz2(dest, crawler_data)

    def write_reachable_nodes(self):
        """Write reachable nodes data as CSV."""
        time_start = time.time()
        df = pd.DataFrame([node.get_stats() for node in self.crawler.nodes.reachable])
        df = df.sort_values(by=["handshake_timestamp"])
        dest = Path(f"{self.result_settings.reachable_nodes}.bz2")
        df.to_csv(dest, index=False, compression="bz2")
        runtime = time.time() - time_start
        log.info(
            "Wrote %s (size=%.1fkB, uncompressed=%.1fkB, ratio=%.1f, runtime=%.1fs)",
            dest,
            dest.stat().st_size / 1024,
            df.memory_usage(index=True).sum() / 1024,
            df.memory_usage(index=True).sum() / dest.stat().st_size,
            runtime,
        )

    def compress_debug_log(self):
        """
        Compress the debug log.

        Identify and close the handler for the debug log file, then compress the file.
        """

        for handler in log.getLogger().handlers:
            if isinstance(handler, log.FileHandler):
                handler.close()

        path_in = self.log_settings.debug_log_path
        path_out = Path(f"{path_in}.bz2")
        time_start = time.time()
        with open(path_in, "rb") as f_in:
            with bz2.open(path_out, "wb") as f_out:
                f_out.writelines(f_in)
        runtime = time.time() - time_start
        log.info(
            "Wrote %s (size=%.1fkB, uncompressed=%.1fkB, ratio=%.1f, runtime=%.1fs)",
            path_out,
            path_out.stat().st_size / 1024,
            path_in.stat().st_size / 1024,
            path_in.stat().st_size / path_out.stat().st_size,
            runtime,
        )
        os.remove(path_in)
        log.debug("Removed uncompressed debug log %s", path_in)

    def upload_files_to_gcs(self):
        """Persist files to GCS."""

        storage_client = storage.Client()
        bucket = storage_client.bucket(self.result_settings.gcs_bucket)

        paths = [
            self.result_settings.address_stats,
            self.result_settings.reachable_nodes,
            self.result_settings.crawler_stats,
        ]
        if self.log_settings.store_debug_log:
            paths.append(self.log_settings.debug_log_path)

        for path in paths:
            blob_dest = self.result_settings.gcs_location + "/" + path.name + ".bz2"
            blob = bucket.blob(blob_dest)
            xfer_start = time.time()
            blob.upload_from_filename(f"{path}.bz2")
            log.info(
                "Uploaded %s to gs://%s/%s in %dms",
                path,
                self.result_settings.gcs_bucket,
                blob_dest,
                int((time.time() - xfer_start) * 1000),
            )
