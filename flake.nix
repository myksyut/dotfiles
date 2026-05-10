{
  description = "miyakishota's macOS configuration";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    nix-darwin = {
      url = "github:LnL7/nix-darwin";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-index-database = {
      url = "github:nix-community/nix-index-database";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      nix-darwin,
      home-manager,
      nix-index-database,
      treefmt-nix,
      git-hooks,
    }:
    let
      system = "aarch64-darwin";
      username = "miyakishota";
      hostname = "miyakinoMacBook-Air";

      mkPkgs =
        system:
        import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

      pkgs = mkPkgs system;

      treefmtEval = treefmt-nix.lib.evalModule pkgs {
        projectRootFile = "flake.nix";
        programs = {
          nixfmt.enable = true;
          statix.enable = true;
          deadnix.enable = true;
        };
      };

      preCommitCheck = git-hooks.lib.${system}.run {
        src = ./.;
        hooks = {
          treefmt = {
            enable = true;
            package = treefmtEval.config.build.wrapper;
          };
          statix.enable = true;
          deadnix.enable = true;
        };
      };
    in
    {
      darwinConfigurations.${hostname} = nix-darwin.lib.darwinSystem {
        inherit system;
        specialArgs = { inherit username; };
        modules = [
          ./modules/darwin
          home-manager.darwinModules.home-manager
          {
            home-manager = {
              useGlobalPkgs = true;
              useUserPackages = true;
              extraSpecialArgs = { inherit username; };
              users.${username} = {
                imports = [
                  nix-index-database.homeModules.nix-index
                  ./modules/home
                ];
              };
            };
          }
        ];
      };

      apps.${system} = {
        switch = {
          type = "app";
          program = toString (
            pkgs.writeShellScript "darwin-switch" ''
              set -eo pipefail
              echo "==> Building and switching darwin configuration..."
              # 固定パスの darwin-rebuild を使う (sudoers の NOPASSWD ルールがマッチするように)
              sudo /run/current-system/sw/bin/darwin-rebuild \
                switch --flake "${self}#${hostname}" \
                |& ${pkgs.nix-output-monitor}/bin/nom
              echo "==> Done!"
            ''
          );
        };

        build = {
          type = "app";
          program = toString (
            pkgs.writeShellScript "darwin-build" ''
              set -eo pipefail
              echo "==> Building darwin configuration (no switch)..."
              ${pkgs.nix-output-monitor}/bin/nom build "${self}#darwinConfigurations.${hostname}.system"
              echo "==> Build successful! Run 'nix run .#switch' to apply."
            ''
          );
        };

        update = {
          type = "app";
          program = toString (
            pkgs.writeShellScript "flake-update" ''
              set -e
              cd ~/.config/nix-config
              echo "==> Updating flake.lock..."
              nix flake update
              echo "==> Done! Run 'nix run .#switch' to apply."
            ''
          );
        };

        fmt = {
          type = "app";
          program = toString (
            pkgs.writeShellScript "treefmt-wrapper" ''
              exec ${treefmtEval.config.build.wrapper}/bin/treefmt "$@"
            ''
          );
        };
      };

      formatter.${system} = treefmtEval.config.build.wrapper;

      checks.${system} = {
        formatting = treefmtEval.config.build.check self;
        pre-commit = preCommitCheck;
      };

      devShells.${system}.default = pkgs.mkShell {
        inherit (preCommitCheck) shellHook;
      };
    };
}
