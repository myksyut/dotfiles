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
  ];

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
