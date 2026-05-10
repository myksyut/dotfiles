{ pkgs, ... }:

{
  home = {
    stateVersion = "24.11";

    sessionVariables = {
      # Playwright が npm パッケージ側で再ダウンロードしないよう、
      # Nix が用意したブラウザバンドルへパスを固定する。
      PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
      PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
    };

    packages = with pkgs; [
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

      nodejs_22
      pnpm
      biome
      playwright-driver
      playwright-test

      mise
      terraform
      terraform-ls
      tflint
      azure-cli
      awscli2

      nerd-fonts.jetbrains-mono
    ];

    file.".config/tmux/session-color.sh" = {
      executable = true;
      text = ''
        #!/usr/bin/env bash
        session="$1"
        [ -z "$session" ] && exit 0
        # Nord-ish palette (foreground stays #2e3440 for contrast on light hues)
        colors=(
          "#5e81ac" "#a3be8c" "#bf616a" "#b48ead"
          "#d08770" "#88c0d0" "#ebcb8b" "#8fbcbb"
        )
        hash=$(printf "%s" "$session" | cksum | awk '{print $1}')
        index=$((hash % ''${#colors[@]}))
        bg="''${colors[$index]}"
        tmux set -t "$session" status-style "bg=$bg,fg=#2e3440"
      '';
    };
  };

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
      extraConfig = ''
        set -g status-style "bg=#3b4252,fg=#eceff4"
        set-hook -g session-created 'run-shell -b "~/.config/tmux/session-color.sh #{session_name}"'
        set-hook -g client-attached 'run-shell -b "~/.config/tmux/session-color.sh #{session_name}"'
        set-hook -g session-renamed 'run-shell -b "~/.config/tmux/session-color.sh #{session_name}"'
      '';
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
        # general
        cli_default_open_behavior = "existing_window";
        auto_update = false; # Nix で管理
        confirm_quit = false;
        restore_on_startup = "last_workspace";
        telemetry = {
          diagnostics = false;
          metrics = false;
        };

        # Zed extensions (起動時に未インストールなら自動取得)
        auto_install_extensions = {
          biome = true;
          terraform = true;
          nix = true;
        };

        # docks / panels
        project_panel = {
          dock = "left";
          default_width = 260;
          file_icons = true;
          folder_icons = true;
          git_status = true;
          indent_size = 16;
        };
        outline_panel.dock = "left";
        collaboration_panel.dock = "left";
        git_panel.dock = "left";
        notification_panel.dock = "right";
        terminal = {
          dock = "hidden"; # bottom dock を使わず、エディタタブで運用 (cmd-shift-enter で新規)
          copy_on_select = true;
          blinking = "on";
          shell = "system";
        };

        # agent
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
        # Claude Code (ACP) — agent panel から起動するとファイル編集 diff を Zed の multibuffer diff UI で確認できる。
        # 初回スレッド作成時に @zed-industries/claude-agent-acp を Zed が自動 install する。
        agent_servers = {
          "claude-acp" = {
            type = "registry";
          };
        };

        # appearance
        icon_theme = "VSCode Icons for Zed (Dark)";
        theme = {
          mode = "dark";
          light = "Nstlgy Glass Dark";
          dark = "Nstlgy Glass Dark";
        };
        # 元 alpha が D7/D0 (≒82-84%) の主要背景を 99 (60%) に下げて、よりガラスっぽく透過させる。
        # editor/panel/terminal などは元から #00000000 (完全透過) で background に重なる構造のため、background を下げれば全体に反映される。
        theme_overrides = {
          "Nstlgy Glass Dark" = {
            "background.appearance" = "blurred";
            background = "#1919264d";
            "surface.background" = "#1e1e2e4d";
            "status_bar.background" = "#1e1e2e4d";
            "title_bar.background" = "#1e1e2e4d";
          };
        };
        ui_font_size = 16;
        buffer_font_size = 15;
        buffer_font_family = "JetBrainsMono Nerd Font";
        buffer_font_features = {
          calt = true;
          liga = true;
        };
        buffer_line_height = "comfortable";

        # editor behavior
        vim_mode = false;
        base_keymap = "Cursor";
        cursor_blink = false;
        cursor_shape = "bar";
        vertical_scroll_margin = 8;
        relative_line_numbers = true;
        current_line_highlight = "all";
        selection_highlight = true;
        show_whitespaces = "selection";
        show_wrap_guides = true;
        wrap_guides = [
          80
          100
        ];
        preferred_line_length = 100;
        soft_wrap = "none";
        tab_size = 2;
        hard_tabs = false;
        remove_trailing_whitespace_on_save = true;
        ensure_final_newline_on_save = true;
        format_on_save = "on";
        autosave = "on_focus_change";
        use_autoclose = true;
        use_auto_surround = true;
        show_completions_on_input = true;
        show_edit_predictions = true;

        # gutter / scrollbar / minimap / tabs / toolbar
        gutter = {
          line_numbers = true;
          runnables = true;
          breakpoints = true;
          folds = true;
        };
        scrollbar = {
          show = "auto";
          cursors = true;
          git_diff = true;
          search_results = true;
          selected_symbol = true;
          diagnostics = "all";
        };
        minimap = {
          show = "auto";
          thumb = "always";
          current_line_highlight = "line";
        };
        tab_bar = {
          show = true;
          show_nav_history_buttons = false;
        };
        tabs = {
          close_position = "right";
          file_icons = true;
          git_status = true;
          activate_on_close = "history";
        };
        toolbar = {
          breadcrumbs = true;
          quick_actions = true;
          selections_menu = true;
        };
        title_bar = {
          show_branch_icon = false;
          show_branch_name = true;
          show_project_items = true;
          show_onboarding_banner = false;
          show_user_picture = false;
          show_sign_in = false;
          show_menus = false;
        };
        centered_layout = {
          left_padding = 0.15;
          right_padding = 0.15;
        };

        # git
        git = {
          git_gutter = "tracked_files";
          inline_blame = {
            enabled = true;
            delay_ms = 500;
            show_commit_summary = true;
          };
          hunk_style = "staged_hollow";
        };

        # diagnostics / inlay hints
        diagnostics = {
          include_warnings = true;
          inline = {
            enabled = true;
            update_debounce_ms = 150;
            padding = 4;
            min_column = 0;
            max_severity = "warning";
          };
        };
        inlay_hints = {
          enabled = true;
          show_type_hints = true;
          show_parameter_hints = true;
          show_other_hints = true;
          show_background = false;
          edit_debounce_ms = 700;
          scroll_debounce_ms = 50;
        };

        # search / file finder / scan exclusions
        file_finder = {
          modal_max_width = "medium";
          file_icons = true;
          git_status = true;
        };
        search = {
          whole_word = false;
          case_sensitive = false;
          include_ignored = false;
          regex = false;
        };
        file_scan_exclusions = [
          "**/.git"
          "**/.direnv"
          "**/.venv"
          "**/__pycache__"
          "**/.mypy_cache"
          "**/.pytest_cache"
          "**/.ruff_cache"
          "**/node_modules"
          "**/dist"
          "**/build"
          "**/result"
          "**/.terraform"
          "**/.DS_Store"
        ];

        # languages
        languages = {
          Python = {
            language_servers = [
              "pyright"
              "ruff"
            ];
            tab_size = 4;
            format_on_save = "on";
            formatter = [
              {
                code_actions = {
                  "source.organizeImports.ruff" = true;
                  "source.fixAll.ruff" = true;
                };
              }
              { language_server.name = "ruff"; }
            ];
          };
          Nix = {
            language_servers = [ "nil" ];
            tab_size = 2;
            format_on_save = "on";
            formatter.external = {
              command = "nixfmt";
              arguments = [ ];
            };
          };
          JSON = {
            tab_size = 2;
            format_on_save = "on";
            formatter = "auto";
          };
          JSONC = {
            tab_size = 2;
            format_on_save = "on";
          };
          YAML = {
            tab_size = 2;
            format_on_save = "on";
          };
          TOML.tab_size = 2;
          Markdown = {
            soft_wrap = "editor_width";
            format_on_save = "off";
            remove_trailing_whitespace_on_save = false;
          };
          Shell = {
            tab_size = 2;
            format_on_save = "on";
          };
          TypeScript = {
            language_servers = [
              "vtsls"
              "!typescript-language-server"
            ];
            tab_size = 2;
            format_on_save = "on";
            formatter = [
              {
                code_actions = {
                  "source.organizeImports.biome" = true;
                  "source.fixAll.biome" = true;
                };
              }
              { language_server.name = "biome"; }
            ];
          };
          TSX = {
            language_servers = [
              "vtsls"
              "!typescript-language-server"
            ];
            tab_size = 2;
            format_on_save = "on";
            formatter = [
              {
                code_actions = {
                  "source.organizeImports.biome" = true;
                  "source.fixAll.biome" = true;
                };
              }
              { language_server.name = "biome"; }
            ];
          };
          JavaScript = {
            language_servers = [
              "vtsls"
              "!typescript-language-server"
            ];
            tab_size = 2;
            format_on_save = "on";
            formatter = [
              {
                code_actions = {
                  "source.organizeImports.biome" = true;
                  "source.fixAll.biome" = true;
                };
              }
              { language_server.name = "biome"; }
            ];
          };
          JSX = {
            language_servers = [
              "vtsls"
              "!typescript-language-server"
            ];
            tab_size = 2;
            format_on_save = "on";
            formatter = [
              {
                code_actions = {
                  "source.organizeImports.biome" = true;
                  "source.fixAll.biome" = true;
                };
              }
              { language_server.name = "biome"; }
            ];
          };
          Terraform = {
            language_servers = [ "terraform-ls" ];
            tab_size = 2;
            format_on_save = "on";
          };
          HCL = {
            language_servers = [ "terraform-ls" ];
            tab_size = 2;
            format_on_save = "on";
          };
        };

        # LSP
        lsp = {
          pyright.settings.python.analysis = {
            typeCheckingMode = "basic";
            autoImportCompletions = true;
            diagnosticMode = "openFilesOnly";
            useLibraryCodeForTypes = true;
          };
          ruff.initialization_options.settings = {
            lineLength = 100;
            lint.preview = true;
            format.preview = true;
          };
          nil.initialization_options = {
            formatting.command = [ "nixfmt" ];
            nix.flake.autoArchive = true;
          };
          solargraph.initialization_options = {
            diagnostics = true;
            formatting = true;
          };
          vtsls.initialization_options = {
            typescript = {
              preferences.importModuleSpecifier = "shortest";
              inlayHints = {
                parameterNames.enabled = "all";
                parameterTypes.enabled = true;
                variableTypes.enabled = true;
                propertyDeclarationTypes.enabled = true;
                functionLikeReturnTypes.enabled = true;
                enumMemberValues.enabled = true;
              };
              updateImportsOnFileMove.enabled = "always";
              suggest.completeFunctionCalls = true;
            };
            javascript = {
              inlayHints = {
                parameterNames.enabled = "all";
                parameterTypes.enabled = true;
                variableTypes.enabled = true;
              };
              updateImportsOnFileMove.enabled = "always";
            };
          };
          "terraform-ls".initialization_options = {
            experimentalFeatures = {
              prefillRequiredFields = true;
              validateOnSave = true;
            };
          };
        };
      };
      userKeymaps = [
        {
          context = "Workspace";
          bindings = {
            # エディタ領域に新規ターミナルタブを開く (bottom dock は非表示)
            "cmd-shift-enter" = "workspace::NewCenterTerminal";
            # ペインを左右に縦分割
            "cmd-shift-d" = "pane::SplitRight";
          };
        }
      ];
    };
  };
}
