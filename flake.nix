{
  description = "Crawler for Bitcoin's P2P network";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, poetry2nix }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        inherit (poetry2nix.lib.mkPoetry2Nix { inherit pkgs; }) mkPoetryApplication defaultPoetryOverrides;
      in
      {
        packages = {
          p2p-crawler = mkPoetryApplication {
            projectDir = self;

            # use python 3.9 due to breaking api change in asyncio
            python = pkgs.python39;

            # extra nativeBuildInputs for dependencies
            overrides = defaultPoetryOverrides.extend
              (self: super: {
                i2plib = super.i2plib.overridePythonAttrs
                  (old: { nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ super.setuptools ]; });
              });
          };
          default = self.packages.${system}.p2p-crawler;
        };

        devShells.default = pkgs.mkShell {
          packages = [ pkgs.poetry ];
        };
      });
}
