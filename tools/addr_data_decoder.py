#!/usr/bin/env python3

"""Decode addr data from a p2p-address-data file."""

import argparse
import io
import lzma
import os
import time
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Optional


@dataclass
class Address:
    """Class representing an address."""

    id: int
    last_seen: int
    net_id: int

    def __post_init__(self):
        networks = ["ipv4", "ipv6", "onion_v2", "onion_v3", "i2p", "cjdns"]
        if not 0 <= self.net_id < len(networks):
            raise ValueError(f"Invalid network ID: {self.net_id}")
        self.network = networks[self.net_id]

    def __repr__(self):
        return (
            f"Address(id={self.id}, last_seen={self.last_seen}, network={self.network})"
        )


@dataclass
class AddrData:
    """Decoder for p2p-crawler address data."""

    file: Path

    _epoch_offset: Optional[int] = field(init=False, default=None)

    HEADER_MAGIC: ClassVar[str] = "p2p-addr-data"
    HEADER_VERSION: ClassVar[int] = 1
    EOF_MARKER: ClassVar[bytes] = "EOF".encode("ASCII")

    @cached_property
    def _buf(self):
        """Read and decompress input file."""
        time_start = time.time()
        with lzma.open(self.file, "rb") as f:
            data = f.read()
        elapsed = time.time() - time_start
        print(f"Decompressed input file '{self.file}' in {elapsed:.2f}s.")
        return io.BytesIO(data)

    @staticmethod
    def decode_zigzag(value: int) -> int:
        """Decode ZigZag-encoded signed integer."""
        return (value >> 1) ^ -(value & 1)

    def eof(self):
        """Check for end of file."""
        maybe_eof_marker = self._buf.read(len(AddrData.EOF_MARKER))
        if maybe_eof_marker != AddrData.EOF_MARKER:
            self._buf.seek(-len(AddrData.EOF_MARKER), os.SEEK_CUR)
            return False
        print("Reached end of file.")
        return True

    def check_header(self):
        """Read and verify file header."""
        magic = self._buf.read(len(AddrData.HEADER_MAGIC)).decode("ASCII")
        if magic != AddrData.HEADER_MAGIC:
            raise ValueError(f"Invalid file magic: {magic}")

        version = int.from_bytes(self._buf.read(1), "big")
        if version != AddrData.HEADER_VERSION:
            raise ValueError(f"Unsupported file version: {version}")

        epoch = int.from_bytes(self._buf.read(4), "big")
        self._epoch_offset = epoch

        terminator = self._buf.read(1).decode("ASCII")
        if terminator != "\n":
            raise ValueError(f"Invalid header terminator: {terminator}")

        print(f"read header (magic={magic}, version={version}, epoch={epoch})")

    def read_varint(self) -> int:
        """Read and decode variable length integer."""
        shift = 0
        result = 0
        while True:
            byte = self._buf.read(1)
            if not byte:
                raise IOError("Unexpected end of stream while reading varint")
            byte = ord(byte)
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
        return result

    def decode(self):
        """Decode input file."""
        time_start = time.time()

        self.check_header()

        result = {}
        while not self.eof():
            node_len = self.read_varint()
            node = self._buf.read(node_len).decode("ascii").strip()
            result[node] = []

            num_records = self.read_varint()
            for i in range(num_records):
                addr_net_id = self.read_varint()
                addr_id = addr_net_id >> 3
                net_id = addr_net_id & 0x07

                lastseen_delta_zigzag = self.read_varint()
                lastseen_delta = AddrData.decode_zigzag(lastseen_delta_zigzag)
                lastseen = self._epoch_offset - lastseen_delta

                result[node].append(Address(addr_id, lastseen, net_id))

                if len(result) % 1000 == 0 and i == num_records - 1:
                    elapsed = time.time() - time_start
                    print(f"decoded={len(result)}, elapsed={elapsed:.1f}s")

            if self._buf.read(1) != b"\n":
                raise ValueError("Record not properly terminated with newline")

        elapsed = time.time() - time_start
        print(f"Finished decoding: total runtime {elapsed:.2f}s.")

        return result


def inspect(data: dict):
    """Inspect data."""

    for i, (node, addr_records) in enumerate(data.items()):
        print(f"record={i}, node={node}, addr_recs=", end="")
        for j in range(min(3, len(addr_records))):
            print(f"{addr_records[j]}, ", end="")
        print(" (cropped to at most three records)")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Decode and display contents of a binary file formatted with address hashes."
    )
    parser.add_argument("file", help="The path to the binary file to decode.")
    args = parser.parse_args()

    decoder = AddrData(Path(args.file))
    data = decoder.decode()
    inspect(data)


if __name__ == "__main__":
    main()
