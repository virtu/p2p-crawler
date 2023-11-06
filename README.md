# Bitcoin P2P network crawler

Crawler for the Bitcoin P2P network with IPv4, IPv6, Onion and I2P support with a
comprehensive scope in terms of data collection. Simple [deployment via Nix
flake](#deployment).

## Deployment

Although the python code in this repository can be run directly for testing purposes,
continuous deployments are best done through NixOS.

### Deployment via NixOS

In addition to package and development shell outputs, the `flake.nix` file also
provides an NixOS module output (see `module.nix` for details).

Deploying via NixOS is thus simply done as follows:

1. Including this repository as input in your system configuration flake:

```nix
inputs = {
  nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  p2p-crawler.url = "github:virtu/p2p-crawler";
};
  ```

2. Importing the module in your system configuration:

```nix
imports = [
  ./hardware-configuration.nix
  p2p-crawler.nixosModules.p2p-crawler
];
```

3. Enabling the crawler:

```nix
services.p2p-crawler.enable = true;
```

Consult `module.nix` for a list of supported configuration options.

### Testing

Most of the crawler's functionality can be tested by crawling only a small fraction of
the P2P network (as opposed to a time-consuming run covering the entire network).

To this end, the share of nodes to be queried for peers can be reduced with the
`--node-share` setting. The run can be sped up further by reducing various timeouts.

Example:

```bash
nix run . -- \
  --no-store-to-gcs \
  --node-share 0.03 \
  --delay-start 5 \
  --ip-connect-timeout 2 --ip-message-timeout 2 --ip-getaddr-timeout 2 \
  --tor-connect-timeout 2 --tor-message-timeout 2 --tor-getaddr-timeout 2 \
  --i2p-connect-timeout 2 --i2p-message-timeout 2 --i2p-getaddr-timeout 2
```

## Settings

The following settings are supported by the crawler.

```text
  --ip-connect-timeout IP_CONNECT_TIMEOUT
                        Timeout for establishing connections using IP
  --ip-message-timeout IP_MESSAGE_TIMEOUT
                        Timeout for replies using IP
  --ip-getaddr-timeout IP_GETADDR_TIMEOUT
                        Max. time to receive addr messages from peers using IP
  --tor-connect-timeout TOR_CONNECT_TIMEOUT
                        Timeout for establishing connections using TOR
  --tor-message-timeout TOR_MESSAGE_TIMEOUT
                        Timeout for replies using TOR
  --tor-getaddr-timeout TOR_GETADDR_TIMEOUT
                        Max. time to receive addr messages from peers using TOR
  --i2p-connect-timeout I2P_CONNECT_TIMEOUT
                        Timeout for establishing connections using I2P
  --i2p-message-timeout I2P_MESSAGE_TIMEOUT
                        Timeout for replies using I2P
  --i2p-getaddr-timeout I2P_GETADDR_TIMEOUT
                        Max. time to receive addr messages from peers using I2P
  --num-workers NUM_WORKERS
                        Number of crawler coroutines
  --node-share NODE_SHARE
                        Share of nodes to query for peers
  --delay-start DELAY_START
                        Delay before starting to wait for tor and i2p containers. Default: 10s
  --getaddr-retries GETADDR_RETRIES
                        Number of retries for getaddr requests for reachable nodes
  --tor-proxy-host TOR_PROXY_HOST
                        SOCKS5 proxy host for Tor
  --tor-proxy-port TOR_PROXY_PORT
                        SOCKS5 proxy port for Tor
  --i2p-sam-host I2P_SAM_HOST
                        SAM router host for I2P
  --i2p-sam-port I2P_SAM_PORT
                        SAM router port for I2P
  --log-level LOG_LEVEL
                        Logging verbosity
  --result-path RESULT_PATH
                        Directory for results
  --extra-version-info EXTRA_VERSION_INFO
                        Extra version info (e.g., git commit hash)
  --timestamp TIMESTAMP
                        Timestamp for results
  --store-debug-log, --no-store-debug-log
                        Store debug log (default: True)
  --store-to-gcs, --no-store-to-gcs
                        Store results to GCS (default: disabled) (default: False)
  --gcs-bucket GCS_BUCKET
                        GCS bucket (default: None)
  --gcs-location GCS_LOCATION
                        GCS location (default: sources/<hostname>)
  --gcs-credentials GCS_CREDENTIALS
                        GCS credentials (service account private key file file, default: None)
```
