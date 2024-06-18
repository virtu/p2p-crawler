# Changelog

All notable changes are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 3.6.0 - 2024.06-17

- Add support for CJDNS. Timeouts can be set via the
  `--cjdns-{connect,message,getaddr}-timeout` command line arguments
- Increase age threshold for advertised nodes from one to two days to account for
  addrman cache lifetime of around one day
- Remove `CrawlerSettings` from the (`repr()`-based) string representation of `Node` the
  node class

## [3.5.0] - 2024-05-06

### Changed

  - Add support to log addresses received in `addr` messages on a per-peer basis. This
    new feature is enabled via the `--record-addr-data` command-line argument.
  - Obsolete the `--record-addr-stats` option to collect timestamps for all advertised
    addresses since this data can be extracted from the data collected using the newly
    introduced `--record-addr-data` option.

## [3.4.0] - 2023-12-05

### Changed

  - Log nodes to which a connection could be established but which did not complete the
    handshake, and introduce `handshake_successful` field in the reachable nodes log to
    differentiate between nodes that successfully completed the handshake and those that
    did not.

## [3.3.0] - 2023-12-04

### Changed

  - Include node address network type in reachable nodes log

## [3.2.0] - 2023-11-28

### Changed

  - Add command-line settings to configure collecting and storing address statistics.
    Address statistics are disabled by default.

## [3.1.5] - 2023-11-27

### Changed

  - Fix bug during parsing of addr messages

## [3.1.4] - 2023-11-27

### Changed

  - Remove logging of tor proxy connect time (`time_connect_proxy`)

## [3.1.3] - 2023-11-26

### Changed

  - Fix timeout issue when uploading large files to GCS

## [3.1.2] - 2023-11-26

### Changed

  - Increase the default number of workers from 20 to 64

## [3.1.1] - 2023-11-24

### Changed

  - Default timeouts have been changed to minimize crawler runtime while maintaining
    99.9% coverage of nodes (the analysis on which the new timeouts are based is
    available here)

## [3.1.0] - 2023-11-20

### Changed

  - Retry node handshake in case it fails the first time(s). Number of handshake
    attempts can be specified using `--handshake-attempts` and defaults to three.
  - Increase handshake and getaddr timeouts for IP connections to sixty seconds.

## [3.0.0] - 2023-11-06

### Changed

  - Provide flake support (`flake run/develop` and nix services)
  - Update `README.md`
  - Improve handling of storing to GCS
    - Set the default GCS location to `sources/<hostname>`
    - Allow specifying GCS credential file via `--gcs-credentials` command-line argument
    - Minor internal improvements (better default settings, dedicated dataclass for GCS
      settings, better sanity checks, etc.)

### Changed

## [2.2.2] - 2023-10-28

### Changed

  - Fix socket leak where SAM sessions were created for each I2P stream instead of
    reusing a single one

## [2.2.1] - 2023-10-27

### Changed

  - Fix socket file descriptor leak where connections where not properly closed when
    encountering connection problems

## [2.2.0] - 2023-10-27

### Changed

  - Introduced command line settings to parametrize TOR proxy and I2P SAM router
    addresses and ports: `--tor-proxy-{host,port}` and `--i2p-sam-{host,port}`

## [2.1.3] - 2023-10-26

### Changed

  - Single source version info (from `pyproject.toml`)
  - Simplify version information (remove auto-detection of git info using `gitpython`
    dependency; instead use new `--extra-version-info` argument to specify additional
    build info (such as a git commit hash)

## [2.1.2] - 2023-10-26

### Changed

  - Fix bug with result output directory breaking when using nested directories
  - Replace build info (read from files) with version info (from source and git)

## [2.1.1] - 2023-10-25

### Changed

  - Making python `logging` timestamps use UTC

## [2.1.0] - 2023-10-23

### Changed

  - Removed docker integration
  - Added nix flake
  - Removed `pandas` as dependency (using `csv` instead)

## [2.0.0] - 2023-07-06

### Changed

  - Refactored the P2P network crawler's source code. This includes several incompatible
    interface changes, as well as incompatible changes to the format of the result files
    written by the crawler.
