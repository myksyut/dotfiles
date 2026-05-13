{
  pkgs,
  username,
  ...
}:

{
  # NixOS-WSL モジュールが provide する `wsl.*` を有効化。
  # `defaultUser` を設定すると wsl 初回起動時にそのユーザーで login する。
  wsl = {
    enable = true;
    defaultUser = username;
    # Windows 側の `wsl.exe` から見える distro 名。`wsl -d <name>` で起動する。
    # NixOS-WSL の default は "NixOS"。複数 distro 並走する場合のみ変える。
    # nativeSystemd = true; # 既定で true。systemd ユーザーサービスを使う場合は触らない
    startMenuLaunchers = true; # Windows のスタートメニューから NixOS を起動できるようにする
    useWindowsDriver = true; # GPU を Windows 側ドライバ経由で使う (WSLg / CUDA など)
  };

  nixpkgs.config.allowUnfree = true;
  nixpkgs.hostPlatform = "x86_64-linux";

  # nix-darwin の `nix.enable = false;` に相当する宣言は WSL では不要。
  # NixOS では nix daemon が system レベルで常時動く前提。
  nix.settings = {
    experimental-features = [
      "nix-command"
      "flakes"
    ];
    # wheel グループに NOPASSWD で nix builds を許可する trusted-users 設定
    trusted-users = [
      "root"
      username
    ];
  };

  # CLI / GUI app の system レベル install。home-manager 側で入れにくいものだけ。
  # WSL から Windows 側ブラウザを開くには `cmd.exe /c start <url>` 等で十分なので
  # 廃止された wslu には依存しない。fzf-url.sh は xdg-open / cmd.exe にフォールバックする。
  environment.systemPackages = with pkgs; [
    git
    wget
    curl
  ];

  # WSL の system locale。日本語 input が必要なら ja_JP.UTF-8 に変える。
  i18n.defaultLocale = "en_US.UTF-8";
  time.timeZone = "Asia/Tokyo";

  # `sudo nixos-rebuild switch` を passwordless で許可。
  # `flake.nix` 側で固定パスの nixos-rebuild を sudo するため、ここのパスと一致させる。
  security.sudo.extraRules = [
    {
      users = [ username ];
      commands = [
        {
          command = "/run/current-system/sw/bin/nixos-rebuild";
          options = [ "NOPASSWD" ];
        }
      ];
    }
  ];

  users.users.${username} = {
    isNormalUser = true;
    home = "/home/${username}";
    extraGroups = [
      "wheel"
      "users"
    ];
    shell = pkgs.zsh;
  };

  # zsh を user shell として使うために system 側で program を有効化。
  programs.zsh.enable = true;

  system.stateVersion = "24.11";
}
