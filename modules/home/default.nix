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

    mise
    terraform
    azure-cli
    awscli2
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

    ghostty = {
      enable = true;
      package = null;
      settings = {
        theme = "nord";
        window-padding-x = 20;
        window-padding-y = 5;
        window-padding-balance = true;
        background-opacity = 0.80;
        background-blur-radius = 20;
        font-feature = "-dlig";
        fullscreen = true;
        macos-non-native-fullscreen = true;
        keybind = [ "ctrl+j=ignore" ];
      };
    };

    zed-editor = {
      enable = true;
      package = null; # GUI app は darwin 側 environment.systemPackages で install (/Applications/Nix Apps/ へ自動link)
      userSettings = {
        cli_default_open_behavior = "existing_window";
        project_panel.dock = "left";
        outline_panel.dock = "left";
        collaboration_panel.dock = "left";
        git_panel.dock = "left";
        agent = {
          dock = "right";
          default_model = {
            provider = "ollama";
            model = "gpt-oss:latest";
          };
          inline_assistant_model = {
            provider = "ollama";
            model = "gpt-oss:latest";
          };
        };
        icon_theme = "VSCode Icons for Zed (Dark)";
        vim_mode = false;
        base_keymap = "Cursor";
        ui_font_size = 16;
        buffer_font_size = 15;
        theme = {
          mode = "dark";
          light = "Nstlgy Glass Dark";
          dark = "Nstlgy Glass Dark";
        };
        languages.Python.language_servers = [ "pyright" ];
        lsp.solargraph.initialization_options = {
          diagnostics = true;
          formatting = true;
        };
      };
    };
  };
}
