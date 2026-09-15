# Standalone host tools; does not activate Darwin/Home Manager or update flake.lock.
let
  pkgs =
    (builtins.getFlake "github:NixOS/nixpkgs/044bfe75bfe4c7bbe043dc17b5e42ea823b84a09")
    .legacyPackages.aarch64-darwin;
in
pkgs.buildEnv {
  name = "devbox-vm-tools";
  paths = [
    (pkgs.lima.override { withAdditionalGuestAgents = true; })
    pkgs.qemu
  ];
}
