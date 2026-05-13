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
    casks = [
      "ghostty"
      # kanata が要求する Karabiner-DriverKit-VirtualHIDDevice を install するためだけに
      # karabiner-elements の cask を使う。driver-only の cask は無い。
      # Karabiner-Elements 本体は Settings > General で「自動起動 OFF」にしておけば
      # kanata と HID 取り合いにならない。
      "karabiner-elements"
    ];
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
    kanata
    (callPackage ../../pkgs/agent-deck { })
  ];

  # kanata 設定。LaunchDaemon は root 権限で動くので home ではなく /etc に置く。
  environment.etc."kanata/mac.kbd".source = ../kanata/mac.kbd;

  # `sudo launchctl kickstart -k system/org.nixos.kanata` で再起動。
  # 初回は「システム設定 > プライバシーとセキュリティ > 入力監視」で
  # /run/current-system/sw/bin/kanata を手動で許可する必要がある。
  launchd.daemons.kanata = {
    serviceConfig = {
      Label = "org.nixos.kanata";
      ProgramArguments = [
        "${pkgs.kanata}/bin/kanata"
        "--cfg"
        "/etc/kanata/mac.kbd"
      ];
      KeepAlive = true;
      RunAtLoad = true;
      StandardOutPath = "/var/log/kanata.log";
      StandardErrorPath = "/var/log/kanata.log";
      ProcessType = "Interactive";
    };
  };

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
