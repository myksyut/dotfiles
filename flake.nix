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
  };
}
