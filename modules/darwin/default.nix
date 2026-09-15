{ pkgs, username, ... }:

{
  imports = [ ./desktop.nix ];

  nix.enable = false;

  nixpkgs.config.allowUnfree = true;

  # nixpkgs のバージョンに依存せず公式 v2 を固定する (macOS 26 以降)。
  nixpkgs.overlays = [
    (_final: prev: {
      raycast = prev.raycast.overrideAttrs (_old: rec {
        version = "2.4.1.0";
        src = prev.fetchurl {
          name = "Raycast.dmg";
          url = "https://x-r2.raycast-releases.com/Raycast_2.4.1.0_df416282fa_arm64.dmg";
          hash = "sha256-W7Ca2vz4BwYFJkuyn89Jbk1hXaOmoM6I6rcGU9GGp5U=";
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
