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
  in {
    darwinConfigurations.${hostname} = nix-darwin.lib.darwinSystem {
      inherit system;
      modules = [
        ({ pkgs, ... }: {
          nix.enable = false;

          environment.systemPackages = with pkgs; [
            git
          ];

          system.stateVersion   = 5;
          system.primaryUser    = username;
          nixpkgs.hostPlatform  = system;

          users.users.${username} = {
            name = username;
            home = "/Users/${username}";
          };
        })

        home-manager.darwinModules.home-manager
        {
          home-manager.useGlobalPkgs    = true;
          home-manager.useUserPackages  = true;
          home-manager.users.${username} = { ... }: {
            home.stateVersion = "24.11";

            programs.tmux = {
              enable   = true;
              mouse    = true;
              terminal = "screen-256color";
            };
          };
        }
      ];
    };
  };
}
