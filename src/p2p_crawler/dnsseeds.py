"""This module contains functionality related to Bitcoin's DNS seeds."""

import logging as log
import re
import socket

import maillog
import requests

from .address import Address
from .decorators import timing

DNS_SEEDS = [
    "seed.bitcoin.sipa.be.",
    "dnsseed.bluematt.me.",
    "dnsseed.bitcoin.dashjr-list-of-p2p-nodes.us.",
    "seed.bitcoinstats.com.",
    "seed.bitcoin.jonasschnelli.ch.",
    "seed.btc.petertodd.net.",
    "seed.bitcoin.sprovoost.nl.",
    "dnsseed.emzy.de.",
    "seed.bitcoin.wiz.biz.",
    "seed.mainnet.achownodes.xyz.",
    "seed.btc.petertodd.net.",
]


@timing
def get_addresses_from_dns_seeds() -> dict[str, list[Address]]:
    """
    Queries DNS seeds for node addresses.

    Returns:
        Dictionary with DNS seeds as keys and obtained addresses as values.
    """

    # Check if the DNS seeds hardcoded in the crawler match those in Bitcoin Core
    compare_seeds_to_bitcoin_master()

    addrs_by_seed = {}
    for host in DNS_SEEDS:
        try:
            reply = socket.getaddrinfo(host, 53, proto=socket.IPPROTO_TCP)
        except OSError as e:
            log.warning("error getting seeds from %s: %s (%s)", host, e, repr(e))
            addrs_by_seed[host] = []
            continue

        # getaddrinfo() returns 5-tuple (family, type, proto, canonname, sockaddr);
        # IP address can be found in sockaddr, which is 2-tuple (address, port)
        # for IPv4 and 4-tuple (address, port, flowinfo, scope_id) for IPv6
        addrs = [Address(r[4][0]) for r in reply]
        addrs_by_seed[host] = addrs
        num_addrs = len(addrs)
        log.debug("dns_seed=%s, addresses=%d", host, num_addrs)

    num_addrs = sum(len(addrs) for addrs in addrs_by_seed.values())
    num_unique = len({node for addrs in addrs_by_seed.values() for node in addrs})
    log.info("discovered %d addrs (%d unique) via DNS seeds", num_addrs, num_unique)
    return addrs_by_seed


def compare_seeds_to_bitcoin_master() -> None:
    """Compares the list of DNS seeds hardcoded into the crawler to the list in Bitcoin Core."""

    # Download chainparams.cpp which contains the DNS seeds hardcoded in Bitcoin Core
    log.info("Fetching DNS seeds from Bitcoin Core master...")
    url = "https://raw.githubusercontent.com/bitcoin/bitcoin/master/src/kernel/chainparams.cpp"
    try:
        response = requests.get(url, timeout=10)
        cpp_content = response.text
    except requests.RequestException as e:
        maillog.warning(f"Error fetching DNS seeds from Bitcoin Core: {e}")
        return

    # Extract the class CMainParams from chainparams to get mainnet seeds
    start_index = cpp_content.find("class CMainParams")
    if start_index == -1:
        maillog.warning("Error extracting DNS seeds: class CMainParams not found")
        return
    brace_start = cpp_content.find("{", start_index)
    if brace_start == -1:
        maillog.warning("Error extracting DNS seeds: opening brace not found")
        return
    brace_level = 1
    pos = brace_start + 1
    while pos < len(cpp_content) and brace_level > 0:
        if cpp_content[pos] == "{":
            brace_level += 1
        elif cpp_content[pos] == "}":
            brace_level -= 1
        pos += 1
    if brace_level != 0:
        maillog.warning("Error extracting DNS seeds: closing brace not found")
        return
    class_content = cpp_content[brace_start + 1 : pos - 1]

    # Remove commentsm, then extract seeds
    class_content_no_comments = re.sub(
        r"//.*?$|/\*.*?\*/", "", class_content, flags=re.MULTILINE | re.DOTALL
    )
    pattern = r'vSeeds\.emplace_back\(\s*"([^"]+)"\s*\);'
    matches = re.findall(pattern, class_content_no_comments)
    seeds_master = set(matches)

    missing = seeds_master - set(DNS_SEEDS)
    extra = set(DNS_SEEDS) - seeds_master

    if missing:
        maillog.warning(
            f"DNS seeds: crawler is missing seeds: {','.join(missing) or 'none'} (extra={','.join(extra) or 'none'})"
        )

    log.info("DNS seeds: all addresses hardcoded in master present in crawler")
    if extra:
        log.info("DNS seeds: extra seeds in crawler: %s", ",".join(extra))
