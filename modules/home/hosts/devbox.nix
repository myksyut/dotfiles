{
  pkgs,
  lib,
  username,
  ...
}:
{
  home.username = username;
  home.homeDirectory = "/home/${username}";
  targets.genericLinux = {
    enable = true;
    gpu.enable = false; # Headless Fly guest has no host GPU integration.
  };
  dotfiles.pi.remoteControl.enable = false;

  # Keep autonomous development local to this isolated host.
  home.file.".pi/agent/AGENTS.md".source = ../devbox-agents.md;
  home.file.".pi/agent/extensions/devbox-autonomy.ts".source = ../devbox-autonomy.ts;
  home.activation.configurePiAutonomy = lib.hm.dag.entryAfter [ "configurePiPackages" ] ''
    run ${pkgs.python3}/bin/python3 ${../configure-devbox-pi.py} "$HOME/.pi/agent/settings.json"
  '';

  # zeno's downloaded SQLite library crashes under this Nix runtime. Use the
  # matching Nix library in both launchers, including already-open shells.
  home.activation.zenoNixSqlite = lib.hm.dag.entryAfter [ "copyZenoZsh" ] ''
    for launcher in "$HOME/.local/share/zeno-zsh/bin/zeno" "$HOME/.local/share/zeno-zsh/bin/zeno-server"; do
      run ${pkgs.gnused}/bin/sed -i '2i export DENO_SQLITE_PATH="${pkgs.sqlite.out}/lib/libsqlite3.so"' "$launcher"
    done
  '';

  home.packages = [
    pkgs.nix
    pkgs.python3
    pkgs.restic
    pkgs.shellcheck
  ];
  home.sessionVariables = {
    DEVBOX_HOST = "1";
    NIX_REMOTE = "daemon";
    NIX_BECOME = "/usr/bin/false";
    SHELL = "${pkgs.zsh}/bin/zsh";
  };
  home.file.".local/bin/devbox" = {
    source = ../../../tools/devbox/devbox;
    executable = true;
  };

  # Orca owns normal worktrees. Keep gwq for inventory, not automatic setup.
  home.file.".config/gwq/config.toml".text = lib.mkForce ''
    # No automatic copying or direnv approval on the devbox.
  '';
  home.file.".config/tmux/worktree-switcher.sh".text = lib.mkForce ''
    #!/usr/bin/env bash
    printf '%s\n' 'Use Orca to create, switch, review and remove worktrees.'
  '';
  # No local VOICEVOX service on a headless host. Pi extensions remain installed.
  home.file.".mcp.json".text = lib.mkForce "{}";
}
