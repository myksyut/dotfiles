{ pkgs, username, ... }:

{
  home.stateVersion = "24.11";

  home.packages = with pkgs; [
    ripgrep
    fd
    fzf

    bat
    eza

    jq

    gh
    lazygit
    delta

    deno
    pyenv
    claude-code

    nil
    nixfmt
    statix
    nix-output-monitor

    tealdeer

    just
    watchexec
    hyperfine
    xh

    dust
    duf
    procs

    uv
    ruff
    pyright
    mypy
  ];

  programs.zoxide.enable = true;
  programs.atuin = {
    enable = true;
    flags = [ "--disable-up-arrow" ];
  };
  programs.tealdeer.enable = true;

  programs.tmux = {
    enable   = true;
    mouse    = true;
    terminal = "screen-256color";
  };

  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };
}
