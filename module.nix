flake: { config, pkgs, lib, ... }:

with lib;

let
  inherit (flake.packages.${pkgs.stdenv.hostPlatform.system}) p2p-crawler;
  cfg = config.services.p2p-crawler;
in
{
  options = {
    services.p2p-crawler = {
      enable = mkEnableOption "p2p-crawler";
      tor = {
        enable = mkEnableOption "TOR" // { default = true; };
        proxy-host = mkOption {
          type = types.str;
          default = "127.0.0.1";
          example = "10.0.0.1";
          description = mdDoc "SOCKS5 proxy host for TOR.";
        };
        proxy-port = mkOption {
          type = types.port;
          default = 9050;
          example = 19050;
          description = mdDoc "SOCKS5 proxy port for TOR.";
        };
      };
      i2p = {
        enable = mkEnableOption "I2P" // { default = true; };
        sam-host = mkOption {
          type = types.str;
          default = "127.0.0.1";
          example = "10.0.0.1";
          description = mdDoc "SAM host for I2P.";
        };
        sam-port = mkOption {
          type = types.port;
          default = 7656;
          example = 17656;
          description = mdDoc "SAM port for I2P.";
        };
      };

      schedule = mkOption {
        type = types.str;
        default = "*-*-* 00,12:00:00 UTC";
        example = "daily";
        description = mdDoc "Systemd OnCalendar interval for running the crawler.";
      };

      timestamp = mkOption {
        type = types.nullOr types.str;
        default = null;
        example = "2023-10-26T10:55:00Z";
        description = mdDoc "Manually set crawler started timestamp.";
      };

      node-share = mkOption {
        type = types.float;
        default = 1.0;
        example = 0.05;
        description = mdDoc "Share of reachable nodes to ask for peers via getaddr.";
      };

      workers = mkOption {
        type = types.int;
        default = 64;
        example = 30;
        description = mdDoc "Number of crawler coroutines.";
      };

      delay-start = mkOption {
        type = types.int;
        default = 10;
        example = 5;
        description = mdDoc "Seconds to wait before starting the crawler.";
      };

      getaddr-attempts = mkOption {
        type = types.int;
        default = 2;
        example = 3;
        description = mdDoc "Number of attempts for getaddr requests.";
      };

      log-level = mkOption {
        type = types.str;
        default = "INFO";
        example = "DEBUG";
        description = mdDoc "Log verbosity for console.";
      };

      result-path = mkOption {
        type = types.path;
        default = "/home/p2p-crawler/";
        example = "/scratch/results/p2p-crawler";
        description = mdDoc "Directory for results.";
      };

      store-debug-log = mkEnableOption "storing the debug log" // { default = true; };

      gcs = {
        enable = mkEnableOption "storing to GCS";
        bucket = mkOption {
          type = types.nullOr types.str;
          default = null;
          example = "bitcoin_p2p_crawler";
          description = mdDoc "GCS bucket.";
        };
        location = mkOption {
          type = types.nullOr types.str;
          default = null;
          example = "foo/bar";
          description = mdDoc "Location in GCS bucket.";
        };
        credentials = mkOption {
          type = types.nullOr types.path;
          default = null;
          example = "secrets/key.json";
          description = mdDoc "Path to GCS credentials file.";
        };
      };

      timeout = {
        ip =
          {
            connect = mkOption {
              type = types.int;
              default = 3;
              example = 10;
              description = mdDoc "Timeout for establishing connections via IPv4 and IPv6.";
            };
            message = mkOption {
              type = types.int;
              default = 30;
              example = 10;
              description = mdDoc "Timeout for replies from peer via IPv4 and IPv6.";
            };
            getaddr = mkOption {
              type = types.int;
              default = 70;
              example = 10;
              description = mdDoc "Max. duration for receiving addr messages via IPv4 and IPv6.";
            };
          };
        tor =
          {
            connect = mkOption {
              type = types.int;
              default = 100;
              example = 10;
              description = mdDoc "Timeout for establishing connections via TOR.";
            };
            message = mkOption {
              type = types.int;
              default = 40;
              example = 10;
              description = mdDoc "Timeout for replies from peer via TOR.";
            };
            getaddr = mkOption {
              type = types.int;
              default = 90;
              example = 10;
              description = mdDoc "Max. duration for receiving addr messages via TOR.";
            };
          };
        i2p =
          {
            connect = mkOption {
              type = types.int;
              default = 30;
              example = 10;
              description = mdDoc "Timeout for establishing connections via I2P.";
            };
            message = mkOption {
              type = types.int;
              default = 80;
              example = 10;
              description = mdDoc "Timeout for replies from peer via I2P.";
            };
            getaddr = mkOption {
              type = types.int;
              default = 170;
              example = 10;
              description = mdDoc "Max. duration for receiving addr messages via I2P.";
            };
          };
      };
    };
  };

  config = mkIf cfg.enable {

    services.tor = mkIf (cfg.tor != false) {
      enable = true;
      client.enable = true;
    };

    services.i2pd = mkIf (cfg.i2p != false) {
      enable = true;
      proto.sam.enable = true;
    };

    users = {
      users.p2p-crawler = {
        isSystemUser = true;
        group = "p2p-crawler";
        home = "/home/p2p-crawler";
        createHome = true;
        homeMode = "755";
      };
      groups.p2p-crawler = { };
    };

    systemd.timers.p2p-crawler = {
      wantedBy = [ "timers.target" ];
      timerConfig =
        {
          OnCalendar = cfg.schedule;
          Unit = [ "p2p-crawler.service" ];
        };
    };

    systemd.services.p2p-crawler = {
      description = "p2p-crawler";
      # service should only run when scheduled, not when system is booted so no
      # wantedBy = [ "multi-user.target" ];
      after = [ "network-online.target" ];

      serviceConfig = {
        ExecStart = ''${p2p-crawler}/bin/p2p-crawler \
          --node-share ${toString cfg.node-share} \
          --delay-start ${toString cfg.delay-start} \
          --num-workers ${toString cfg.workers} \
          --getaddr-attempts ${toString cfg.getaddr-attempts} \
          --log-level ${cfg.log-level} \
          --result-path ${cfg.result-path} \
          ${if cfg.store-debug-log then "--store-debug-log" else "--no-store-debug-log"} \
          ${if cfg.gcs.enable
then "--store-to-gcs ${optionalString (cfg.gcs.bucket != null) "--gcs-bucket ${cfg.gcs.bucket}"} ${optionalString (cfg.gcs.location != null) "--gcs-location ${cfg.gcs.location}"} ${optionalString (cfg.gcs.credentials != null) "--gcs-credentials ${cfg.gcs.credentials}"}"
else "--no-store-to-gcs"} \
          ${optionalString (cfg.timestamp != null) "--timestamp=${cfg.timestamp}" } \
          ${optionalString (cfg.tor.enable != false) "--tor-proxy-host=${cfg.tor.proxy-host} --tor-proxy-port=${toString cfg.tor.proxy-port}" } \
          ${optionalString (cfg.i2p.enable != false) "--i2p-sam-host=${cfg.i2p.sam-host} --i2p-sam-port=${toString cfg.i2p.sam-port}" } \
          --ip-connect-timeout ${toString cfg.timeout.ip.connect} \
          --ip-message-timeout ${toString cfg.timeout.ip.message} \
          --ip-getaddr-timeout ${toString cfg.timeout.ip.getaddr} \
          --tor-connect-timeout ${toString cfg.timeout.tor.connect} \
          --tor-message-timeout ${toString cfg.timeout.tor.message} \
          --tor-getaddr-timeout ${toString cfg.timeout.tor.getaddr} \
          --i2p-connect-timeout ${toString cfg.timeout.i2p.connect} \
          --i2p-message-timeout ${toString cfg.timeout.i2p.message} \
          --i2p-getaddr-timeout ${toString cfg.timeout.i2p.getaddr}
        '';
        MemoryDenyWriteExecute = true;
        ReadWriteDirectories = "/home/p2p-crawler/";
        DynamicUser = true;
        User = "p2p-crawler";
        Group = "p2p-crawler";
      };
    };
  };
}
