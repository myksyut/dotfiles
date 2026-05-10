{ pkgs, username, ... }:

{
  nix.enable = false;

  nixpkgs.config.allowUnfree = true;

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
