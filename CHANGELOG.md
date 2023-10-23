# Changelog

All notable changes are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
