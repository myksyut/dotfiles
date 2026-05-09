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
  };

  outputs = { self, nixpkgs, nix-darwin, home-manager }:
  let
    system   = "aarch64-darwin";
    username = "miyakishota";
    hostname = "miyakinoMacBook-Air";

    mkPkgs = system: import nixpkgs {
      inherit system;
      config.allowUnfree = true;
    };

    pkgs = mkPkgs system;
  in {
    darwinConfigurations.${hostname} = nix-darwin.lib.darwinSystem {
      inherit system;
      specialArgs = { inherit username; };
      modules = [
        ./modules/darwin
        home-manager.darwinModules.home-manager
        {
          home-manager.useGlobalPkgs    = true;
          home-manager.useUserPackages  = true;
          home-manager.extraSpecialArgs = { inherit username; };
          home-manager.users.${username} = import ./modules/home;
        }
      ];
    };

    apps.${system} = {
      switch = {
        type = "app";
        program = toString (pkgs.writeShellScript "darwin-switch" ''
          set -eo pipefail
          echo "==> Building and switching darwin configuration..."
          sudo ${nix-darwin.packages.${system}.darwin-rebuild}/bin/darwin-rebuild \
            switch --flake "${self}#${hostname}" \
            |& ${pkgs.nix-output-monitor}/bin/nom
          echo "==> Done!"
        '');
      };

      build = {
        type = "app";
        program = toString (pkgs.writeShellScript "darwin-build" ''
          set -eo pipefail
          echo "==> Building darwin configuration (no switch)..."
          ${pkgs.nix-output-monitor}/bin/nom build "${self}#darwinConfigurations.${hostname}.system"
          echo "==> Build successful! Run 'nix run .#switch' to apply."
        '');
      };

      update = {
        type = "app";
        program = toString (pkgs.writeShellScript "flake-update" ''
          set -e
          cd ~/.config/nix-config
          echo "==> Updating flake.lock..."
          nix flake update
          echo "==> Done! Run 'nix run .#switch' to apply."
        '');
      };
    };
  };
}
