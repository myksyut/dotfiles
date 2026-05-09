{ pkgs, ... }:

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

  programs = {
    zoxide.enable = true;
    atuin = {
      enable = true;
      flags = [ "--disable-up-arrow" ];
    };
    tealdeer.enable = true;
    nix-index = {
      enable = true;
      enableZshIntegration = true;
    };
    nix-index-database.comma.enable = true;
    tmux = {
      enable = true;
      mouse = true;
      terminal = "screen-256color";
    };
    direnv = {
      enable = true;
      nix-direnv.enable = true;
    };
  };
}
