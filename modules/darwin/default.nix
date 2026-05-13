{ pkgs, username, ... }:

{
  nix.enable = false;

  nixpkgs.config.allowUnfree = true;

  # nixpkgs の raycast (1.104.10) は既存ローカル DB より古く起動拒否されるため、
  # 公式リリースから最新版を取得する overlay を当てる。nixpkgs が追いついたら削除可。
  nixpkgs.overlays = [
    (_final: prev: {
      raycast = prev.raycast.overrideAttrs (_old: rec {
        version = "1.104.16";
        src = prev.fetchurl {
          name = "Raycast.dmg";
          url = "https://releases.raycast.com/releases/${version}/download?build=arm";
          hash = "sha256-y/MPOo6Iklf9hOH/RRBDOjdX7x8tvfIF9NB42grfPC8=";
        };
      });
    })
  ];

  homebrew = {
    enable = true;
    casks = [ "ghostty" ];
    onActivation = {
      cleanup = "none";
      autoUpdate = false;
      upgrade = false;
    };
  };

  environment.systemPackages = with pkgs; [
    git
    zed-editor
    raycast
    (callPackage ../../pkgs/agent-deck { })
  ];

  system = {
    stateVersion = 5;
    primaryUser = username;
    defaults.finder.CreateDesktop = false;
  };
  nixpkgs.hostPlatform = "aarch64-darwin";

  users.users.${username} = {
    name = username;
    home = "/Users/${username}";
  };

  # `nix run .#switch` を sudo パスワードなしで実行できるように darwin-rebuild のみ NOPASSWD 許可。
  # `flake.nix` 側で固定パス /run/current-system/sw/bin/darwin-rebuild を sudo するため、ここのパスと一致させる。
  environment.etc."sudoers.d/nix-darwin-rebuild".text = ''
    ${username} ALL=(ALL) NOPASSWD: /run/current-system/sw/bin/darwin-rebuild
  '';
}
