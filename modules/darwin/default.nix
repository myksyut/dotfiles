{ pkgs, username, ... }:

{
  nix.enable = false;

  environment.systemPackages = with pkgs; [
    git
  ];

  system.stateVersion  = 5;
  system.primaryUser   = username;
  nixpkgs.hostPlatform = "aarch64-darwin";

  users.users.${username} = {
    name = username;
    home = "/Users/${username}";
  };
}
