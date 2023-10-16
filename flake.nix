{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgs = forAllSystems (system: nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (system: {
        default = pkgs.${system}.poetry2nix.mkPoetryApplication {
          projectDir = self;

          # use python 3.9 due to breaking api change in asyncio
          python = pkgs.${system}.python39;

          # extra dependencies for dependencies
          overrides = pkgs.${system}.poetry2nix.defaultPoetryOverrides.extend
            (self: super: {
              i2plib = super.i2plib.overridePythonAttrs
                (old: { buildInputs = (old.buildInputs or [ ]) ++ [ super.setuptools ]; });
            });
        };
      });

      devShells = forAllSystems (system: {
        default = pkgs.${system}.mkShellNoCC
          {
            packages = with pkgs.${system}; [
              (poetry2nix.mkPoetryEnv {
                projectDir = self;

                # use python 3.9 due to breaking api change in asyncio
                python = python39;

                # extra dependencies for dependencies
                overrides = poetry2nix.defaultPoetryOverrides.extend
                  (self: super: {
                    i2plib = super.i2plib.overridePythonAttrs
                      (old: { buildInputs = (old.buildInputs or [ ]) ++ [ super.setuptools ]; });
                  });
              })
              poetry
            ];
            shellHook = ''
              echo "Executed devShell shell hook."
              alias testrun="poetry run p2p-crawler --help"
            '';
          };
      });
    };
}

