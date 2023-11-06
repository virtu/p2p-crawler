# Changelog

All notable changes are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
