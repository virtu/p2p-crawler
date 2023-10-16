"""This module contains functionality related to Bitcoin's DNS seeds."""

import logging as log
import socket

from .address import Address
from .decorators import timing

DNS_SEEDS = [
    "seed.bitcoin.sipa.be",
    "dnsseed.bluematt.me",
    "dnsseed.bitcoin.dashjr.org",
    "seed.bitcoinstats.com",
    "seed.bitcoin.jonasschnelli.ch",
    "seed.btc.petertodd.org",
    "seed.bitcoin.sprovoost.nl",
    "dnsseed.emzy.de",
    "seed.bitcoin.wiz.biz",
]


@timing
def get_addresses_from_dns_seeds() -> dict[str, list[Address]]:
    """
    Queries DNS seeds for node addresses.

    Returns:
        Dictionary with DNS seeds as keys and obtained addresses as values.
    """

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
