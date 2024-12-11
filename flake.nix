{
  description = "Crawler for Bitcoin's P2P network";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    maillog = {
      url = "github:virtu/maillog";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, poetry2nix, maillog }: {
    nixosModules.p2p-crawler = import ./module.nix self;
  } // flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = import nixpkgs {
        inherit system;
      };
      inherit (poetry2nix.lib.mkPoetry2Nix { inherit pkgs; }) mkPoetryApplication defaultPoetryOverrides;
      pkgsWithOverlays = import nixpkgs {
        inherit system;
        overlays = maillog.overlays.${system};
      };

    in
    {
      packages = {
        p2p-crawler = mkPoetryApplication {
          projectDir = ./.;

          # use python 3.9 due to breaking api change in asyncio
          python = pkgs.python39;

          # extra nativeBuildInputs for dependencies
          overrides = defaultPoetryOverrides.extend (final: super: {
            i2plib = super.i2plib.overridePythonAttrs
              (old: { nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ super.setuptools ]; });
            maillog = pkgsWithOverlays.maillog { python = pkgs.python39; };
          });
        };
        default = self.packages.${system}.p2p-crawler;
      };

      devShells.default = pkgs.mkShell {
        inputsFrom = [ self.packages.${system}.default ];
        packages = with pkgs; [ poetry ];
      };
    });
}
