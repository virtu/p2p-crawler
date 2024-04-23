"""Module for persisting crawler output."""

import bz2
import csv
import json
import logging as log
import lzma
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from google.cloud import storage

from .address import Address
from .config import LogSettings, ResultSettings
from .crawler import Crawler


@dataclass
class Output:
    """Class to persist crawler results."""

    result_settings: ResultSettings
    log_settings: LogSettings
    crawler: Crawler

    @staticmethod
    def lzma_compress_file(path_in: Path, delete_input: bool = True):
        """Compress file using LZMA."""

        time_start = time.time()
        path_out = Path(f"{path_in}.xz")
        with path_in.open("rb") as f_in:
            with lzma.open(path_out, "wb") as f_out:
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
        if delete_input:
            os.remove(path_in)
            log.debug("Removed uncompressed input file %s", path_in)

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
        if self.result_settings.gcs.store:
            self.upload_files_to_gcs()

    def write_files(self):
        """Persist files to filesystem."""

        self.write_crawler_statistics()
        self.write_reachable_nodes()
        if self.crawler.settings.record_addr_data:
            self.write_addr_data_eof()
            Output.lzma_compress_file(self.result_settings.addr_data)
        if self.log_settings.store_debug_log:
            self.compress_debug_log()

    def write_addr_data_eof(self):
        """Write 'EOF' to addr data file."""

        eof = "EOF".encode("ascii")
        with open(self.result_settings.addr_data, "ab") as f:
            f.write(eof)

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
        """Write reachable nodes data as CSV. Order by handshake timestamp."""
        time_start = time.time()

        reachable_nodes = [node.get_stats() for node in self.crawler.nodes.reachable]
        if not reachable_nodes:
            log.warning("No reachable nodes found. Not writing reachable nodes CSV.")
            return
        reachable_nodes.sort(key=lambda x: x["handshake_timestamp"])

        dest = Path(f"{self.result_settings.reachable_nodes}.bz2")
        with bz2.open(dest, "wt") as csv_compressed:
            fieldnames = reachable_nodes[0].keys()
            writer = csv.DictWriter(csv_compressed, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(reachable_nodes)

        runtime = time.time() - time_start
        size = sum(sys.getsizeof(node.values()) for node in reachable_nodes)
        log.info(
            "Wrote %s (size=%.1fkB, uncompressed=%.1fkB, ratio=%.1f, runtime=%.1fs)",
            dest,
            dest.stat().st_size / 1024,
            size / 1024,
            size / dest.stat().st_size,
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

        storage_client = storage.Client.from_service_account_json(
            self.result_settings.gcs.credentials
        )
        bucket = storage_client.bucket(self.result_settings.gcs.bucket)

        def add_suffix(path: Path, suffix: str) -> Path:
            return path.with_suffix(path.suffix + suffix)

        paths = [
            add_suffix(self.result_settings.reachable_nodes, ".bz2"),
            add_suffix(self.result_settings.crawler_stats, ".bz2"),
        ]
        if self.crawler.settings.record_addr_data:
            paths.append(add_suffix(self.result_settings.addr_data, ".xz"))
        if self.log_settings.store_debug_log:
            paths.append(add_suffix(self.log_settings.debug_log_path, ".bz2"))

        for path in paths:
            blob_dest = self.result_settings.gcs.location + "/" + path.name
            blob = bucket.blob(blob_dest)
            # workaround for a GCS timeout issue when uploading large files
            # (see https://github.com/googleapis/python-storage/issues/74)
            blob._chunk_size = 8 * 1024 * 1024  # 8 MB
            xfer_start = time.time()
            blob.upload_from_filename(path)
            log.info(
                "Uploaded %s to gs://%s/%s in %dms",
                path,
                self.result_settings.gcs.bucket,
                blob_dest,
                int((time.time() - xfer_start) * 1000),
            )
