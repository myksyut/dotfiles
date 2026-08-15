{
  pkgs,
  config,
  lib,
  zeno-zsh,
  ...
}:

let
  isDarwin = pkgs.stdenv.isDarwin;
in
{
  home = {
    stateVersion = "24.11";

    sessionVariables = {
      # Playwright が npm パッケージ側で再ダウンロードしないよう、
      # Nix が用意したブラウザバンドルへパスを固定する。
      PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
      PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
    };

    packages =
      with pkgs;
      [
        ripgrep
        fd
        fzf

        bat
        eza

        jq

        gh
        lazygit
        delta
        himalaya
        (callPackage ../../pkgs/gwq { })

        deno
        pyenv
        claude-code
        codex
        herdr
        pi-coding-agent

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
        railway
        terraform
        terraform-ls
        tflint
        azure-cli
        awscli2

        nerd-fonts.jetbrains-mono
        # 日本語合成フォント (HackGen35ConsoleNF 等)。~/Library/Fonts への手動配置から移行
        hackgen-nf-font
      ]
      ++ lib.optionals isDarwin [
        # macOS のみ build 可能なパッケージ
        terminal-notifier
      ];

    # 放置 tmux セッションの掃除 (prefix+X で interactive / launchd で --auto 定期実行)。
    # ロジックは bash ファイルとして切り出し、ここからは source で配線する。
    file.".config/tmux/session-gc.sh" = {
      executable = true;
      source = ./scripts/tmux-session-gc.sh;
    };

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

    file.".config/tmux/fzf-url.sh" = {
      executable = true;
      text = ''
        #!/usr/bin/env bash
        set -euo pipefail
        pane="''${1:-''${TMUX_PANE:-}}"
        urls=$(tmux capture-pane -J -p -S - ''${pane:+-t "$pane"} \
          | grep -oE 'https?://[^[:space:]<>"'"'"'`]+' \
          | sed 's/[.,);:!?]*$//' \
          | awk '!seen[$0]++')
        [ -z "$urls" ] && exit 0
        selected=$(printf '%s\n' "$urls" | fzf --reverse --no-multi --prompt='URL> ')
        [ -z "$selected" ] && exit 0
        # macOS=open / WSL=wslview / その他Linux=xdg-open でブラウザに渡す
        if command -v open >/dev/null 2>&1; then
          open "$selected"
        elif command -v wslview >/dev/null 2>&1; then
          wslview "$selected"
        elif command -v xdg-open >/dev/null 2>&1; then
          xdg-open "$selected"
        else
          echo "no URL opener found (open / wslview / xdg-open)" >&2
          exit 1
        fi
      '';
    };

    # gwq のグローバル設定。`repository = "**"` の catch-all で全リポジトリに共通の
    # copy_files / setup_commands を適用する。findRepoSetting は先頭一致なので、
    # 特定 repo 用の override を入れる場合は `**` より上に並べること。
    file.".config/gwq/config.toml".text = ''
      [[repository_settings]]
      repository = "**"
      copy_files = [
        ".env",
        ".env.*",
        ".envrc",
        ".envrc.local",
        ".tool-versions",
        ".python-version",
        ".node-version",
        ".claude/settings.local.json",
      ]
      setup_commands = [
        "if [ -f .envrc ]; then direnv allow .; fi",
      ]
    '';

    # MCP サーバ定義 (Claude Code 等)。secret なし。
    # force: 同一内容だと link 生成が skip され手動ファイルのまま残るため
    file.".mcp.json" = {
      force = true;
      text = ''
        {
          "mcpServers": {
            "voicevox": {
              "command": "npx",
              "args": ["@t09tanaka/mcp-simple-voicevox"]
            }
          }
        }
      '';
    };

    # herdr (tmux 代替のターミナルマルチプレクサ) の設定
    file.".config/herdr/config.toml" = {
      force = true;
      text = ''
        [terminal]
        # デフォルトは $SHELL → /bin/sh fallback。server が launchd/systemd 等の
        # $SHELL 無し環境で起動されると pane が /bin/sh に落ちるため、Nix の zsh に固定する。
        default_shell = "${pkgs.zsh}/bin/zsh"
        # "auto" は macOS のみ login shell。WSL でも ~/.zprofile (pyenv PATH 等) を
        # 読ませたいので明示的に login にする。
        shell_mode = "login"

        [ui]
        agent_panel_sort = "priority"
      '';
    };

    # zeno.zsh の snippet 定義 (ZENO_HOME=~/.config/zeno)
    file.".config/zeno/config.yml" = {
      force = true;
      text = ''
        snippets:
          - name: open pm-agent-skills
            keyword: pma
            snippet: cd "$HOME/Library/CloudStorage/GoogleDrive-shota.miyaki@emuniinc.jp/マイドライブ/pm-agent-skills"

          - name: open pm-agent-skills and claude
            keyword: pmac
            snippet: cd "$HOME/Library/CloudStorage/GoogleDrive-shota.miyaki@emuniinc.jp/マイドライブ/pm-agent-skills" && claude

          - name: claude
            keyword: cl
            snippet: claude

          - name: tmux
            keyword: tm
            snippet: tmux

          - name: tmux attach
            keyword: tma
            snippet: tmux attach

          - name: tmux attach to session
            keyword: tmat
            snippet: "tmux attach -t "

          - name: tmux new session
            keyword: tmn
            snippet: "tmux new -s "

          - name: tmux list sessions
            keyword: tml
            snippet: tmux ls

          - name: tmux kill session
            keyword: tmk
            snippet: "tmux kill-session -t "

          - name: tmux kill server
            keyword: tmka
            snippet: tmux kill-server
      '';
    };

    # tmux popup から呼び出して、既存 worktree / ローカル / リモートブランチを fzf で選び、
    # 必要なら gwq add で worktree を作成し、tmux セッションを起動 or 切替する。
    file.".config/tmux/worktree-switcher.sh" = {
      executable = true;
      text = ''
        #!/usr/bin/env bash
        set -euo pipefail

        # popup の cwd は呼び出し元 pane の current_path だが、
        # その path が削除済みだと git rev-parse が失敗して global モードに落ち、
        # basedir 外の本体 worktree が一覧から消える。先に有効な cwd に逃がす。
        if ! pwd >/dev/null 2>&1 || [ ! -d "$(pwd 2>/dev/null)" ]; then
          cd "$HOME" || exit 1
        fi

        if ! command -v gwq >/dev/null 2>&1; then
          echo "gwq not found in PATH" >&2
          read -r -p "press enter to exit" _ || true
          exit 1
        fi

        in_repo=false
        if git rev-parse --git-dir >/dev/null 2>&1; then
          in_repo=true
        fi

        if $in_repo; then
          worktrees_json=$(gwq list --json 2>/dev/null || echo "[]")
        else
          worktrees_json=$(gwq list -g --json 2>/dev/null || echo "[]")
        fi

        worktrees=$(printf '%s\n' "$worktrees_json" \
          | jq -r '.[] | "[wt] " + .branch + "\t" + .path')
        existing_branches=$(printf '%s\n' "$worktrees_json" | jq -r '.[].branch')

        local_lines=""
        remote_lines=""
        if $in_repo; then
          # grep -vxFf は全行除外時に exit 1 を返すので、|| true で pipefail を無効化。
          local_lines=$(git branch --format='%(refname:short)' \
            | { grep -vxFf <(printf '%s\n' "$existing_branches") || true; } \
            | awk 'NF{print "[local] " $0 "\t"}')
          remote_lines=$(git branch -r --format='%(refname:short)' \
            | grep -v 'HEAD' \
            | sed 's|^[^/]*/||' \
            | sort -u \
            | { grep -vxFf <(printf '%s\n' "$existing_branches") || true; } \
            | awk 'NF{print "[remote] " $0 "\t"}')
        fi

        candidates=$(
          {
            printf '%s\n' "$worktrees"
            [ -n "$local_lines" ] && printf '%s\n' "$local_lines"
            [ -n "$remote_lines" ] && printf '%s\n' "$remote_lines"
            true
          } | awk 'NF'
        )

        # 候補ゼロでも fzf は起動する: query をそのまま新規ブランチ名として扱うため。
        set +e
        fzf_out=$(printf '%s\n' "$candidates" | fzf \
          --reverse --no-multi --prompt='gwq> ' \
          --delimiter=$'\t' --with-nth=1 \
          --print-query --expect=ctrl-d \
          --header='enter: switch / new  •  ctrl-d: remove worktree' \
          --preview='echo {2}' --preview-window='down:1:wrap')
        fzf_status=$?
        set -e

        # Esc/Ctrl-C は 130。何もせず終了。
        if [ "$fzf_status" -eq 130 ]; then
          exit 0
        fi

        # --print-query --expect の出力: 1行目=query, 2行目=押されたキー(空ならEnter), 3行目=選択
        query=$(printf '%s' "$fzf_out" | sed -n '1p')
        pressed_key=$(printf '%s' "$fzf_out" | sed -n '2p')
        selected=$(printf '%s' "$fzf_out" | sed -n '3p')

        # Ctrl-D: worktree 削除モード
        if [ "$pressed_key" = "ctrl-d" ]; then
          if [ -z "$selected" ]; then
            echo "No worktree selected to remove" >&2
            read -r -p "press enter to exit" _ || true
            exit 1
          fi
          label=$(printf '%s' "$selected" | awk -F'\t' '{print $1}')
          del_path=$(printf '%s' "$selected" | awk -F'\t' '{print $2}')
          case "$label" in
            "[wt] "*)
              del_branch="''${label#'[wt] '}"
              ;;
            *)
              echo "Can only remove [wt] entries (got: $label)" >&2
              read -r -p "press enter to exit" _ || true
              exit 1
              ;;
          esac

          current_session=$(tmux display-message -p '#S' 2>/dev/null || echo "")
          del_repo=$(git -C "$del_path" remote get-url origin 2>/dev/null \
            | sed 's|.*/||; s|\.git$||' || true)
          [ -z "$del_repo" ] && del_repo=$(basename "$del_path")
          del_session=$(printf '%s__%s' "$del_repo" "$del_branch" | tr ':./' '___')

          if [ "$current_session" = "$del_session" ]; then
            printf 'Currently attached to %s. Remove worktree & drop to shell? [y/N] ' "$del_session"
          else
            printf 'Remove worktree %s? [y/N] ' "$del_branch"
          fi
          read -r confirm || confirm=""
          case "$confirm" in
            y|Y|yes|YES) ;;
            *)
              echo "Cancelled."
              exit 0
              ;;
          esac

          # cd 前に main repo path を抑える ($HOME に逃げると -C が必要)。
          main_repo=$(printf '%s' "$worktrees_json" \
            | jq -r '.[] | select(.is_main==true) | .path')
          [ -z "$main_repo" ] && main_repo=$(git -C "$del_path" rev-parse --show-toplevel 2>/dev/null || echo "")

          # popup の cwd が del_path だと remove 後に困るので退避。
          cd "$HOME"

          # gwq remove は pattern 部分一致 (test→test/test2 両方ヒット) で
          # popup 内 fuzzy finder が起動できず cancel になる。git worktree
          # remove に path を直接渡せば曖昧マッチが起きない。
          if [ -z "$main_repo" ] || ! git -C "$main_repo" worktree remove "$del_path"; then
            echo "git worktree remove failed (try -f if dirty)."
            read -r -p "press enter to exit" _ || true
            exit 1
          fi

          # 残った tmux セッションを kill。current session を kill すると
          # クライアントが detach されて素のターミナルに戻る。
          if tmux has-session -t "=$del_session" 2>/dev/null; then
            tmux kill-session -t "=$del_session"
          fi
          exit 0
        fi

        if [ -z "$selected" ]; then
          # マッチなし or 候補ゼロ + Enter → query を新規ブランチ名として作成。
          if [ -z "$query" ]; then
            exit 0
          fi
          if ! $in_repo; then
            echo "Not in a git repo; cannot create new branch '$query'" >&2
            read -r -p "press enter to exit" _ || true
            exit 1
          fi
          base_branch=$( { git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
            | sed 's|^refs/remotes/origin/||'; } || true)
          [ -n "$base_branch" ] || base_branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo main)
          branch="$query"
          # gwq add は [branch] [path] 受けで base ブランチを指定できないため、
          # 先に git branch で base から作成してから gwq add で worktree 化する。
          if ! git branch "$branch" "$base_branch" 2>/dev/null \
              && ! git branch "$branch" "origin/$base_branch" 2>/dev/null; then
            echo "failed to create branch $branch from $base_branch" >&2
            read -r -p "press enter to exit" _ || true
            exit 1
          fi
          if ! gwq add "$branch"; then
            echo "gwq add $branch failed" >&2
            read -r -p "press enter to exit" _ || true
            exit 1
          fi
          target_path=$(gwq get "$branch" 2>/dev/null || true)
          if [ -z "$target_path" ]; then
            echo "Could not resolve worktree path for $branch" >&2
            read -r -p "press enter to exit" _ || true
            exit 1
          fi
        else
          label=$(printf '%s' "$selected" | awk -F'\t' '{print $1}')
          target_path=$(printf '%s' "$selected" | awk -F'\t' '{print $2}')

          case "$label" in
            "[wt] "*)
              branch="''${label#'[wt] '}"
              ;;
            "[local] "*|"[remote] "*)
              branch="''${label#*'] '}"
              if ! gwq add "$branch"; then
                echo "gwq add $branch failed" >&2
                read -r -p "press enter to exit" _ || true
                exit 1
              fi
              target_path=$(gwq get "$branch" 2>/dev/null || true)
              if [ -z "$target_path" ]; then
                echo "Could not resolve worktree path for $branch" >&2
                read -r -p "press enter to exit" _ || true
                exit 1
              fi
              ;;
            *)
              echo "Unknown selection: $label" >&2
              exit 1
              ;;
          esac
        fi

        repo_name=$(git -C "$target_path" remote get-url origin 2>/dev/null \
          | sed 's|.*/||; s|\.git$||')
        [ -z "$repo_name" ] && repo_name=$(basename "$(git -C "$target_path" rev-parse --show-toplevel 2>/dev/null || echo "$target_path")")
        session_name=$(printf '%s__%s' "$repo_name" "$branch" | tr ':./' '___')

        if ! tmux has-session -t "=$session_name" 2>/dev/null; then
          tmux new-session -d -s "$session_name" -c "$target_path"
        fi

        if [ -n "''${TMUX:-}" ]; then
          tmux switch-client -t "=$session_name"
        else
          tmux attach-session -t "$session_name"
        fi
      '';
    };

    # zeno.zsh: 実行時に deno が node_modules を生成する (deno cache --node-modules-dir=auto)
    # ため writable パスが要る。flake input は store の read-only なので、
    # ~/.local/share へコピーしてから source する。
    activation.copyZenoZsh = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      run rm -rf "$HOME/.local/share/zeno-zsh"
      run cp -R ${zeno-zsh} "$HOME/.local/share/zeno-zsh"
      run chmod -R u+w "$HOME/.local/share/zeno-zsh"
    '';
  };

  programs = {
    # zsh を home-manager 配下に置く。これを有効化しないと zoxide/atuin/direnv 等の
    # zsh integration が ~/.zshrc に書き出されず、シェルが素のままになる
    # (Linux/WSL では `zsh-newuser-install` のプロンプトに毎回当たる)。
    zoxide.enable = true;
    atuin = {
      enable = true;
      flags = [ "--disable-up-arrow" ];
      # 手書き ~/.config/atuin/config.toml の非デフォルト項目のみ移行
      settings = {
        enter_accept = true;
        sync.records = true;
      };
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
        set -g status-right-length 60
        set -g status-right '#{?client_prefix,#[bg=#ebcb8b]#[fg=#2e3440]#[bold] ● PREFIX #[default] ,}%H:%M '
        set-hook -g session-created 'run-shell -b "~/.config/tmux/session-color.sh #{session_name}"'
        set-hook -g client-attached 'run-shell -b "~/.config/tmux/session-color.sh #{session_name}"'
        set-hook -g session-renamed 'run-shell -b "~/.config/tmux/session-color.sh #{session_name}"'
        bind-key u display-popup -E -w 80% -h 60% "~/.config/tmux/fzf-url.sh #{pane_id}"
        bind-key w display-popup -E -d '#{pane_current_path}' -w 80% -h 60% "~/.config/tmux/worktree-switcher.sh"
        # prefix+k: 放置セッションを fzf で選んで掃除 (⚠=開発プロセス動作中は消すと失う)
        # Shift を使う大文字キーが効かない環境のため、小文字 k (Kill 連想) を採用。
        # 標準の prefix+x(kill-pane) とは別の物理キーで誤爆しにくい。
        bind-key k display-popup -E -w 85% -h 70% "~/.config/tmux/session-gc.sh"
      '';
    };
    direnv = {
      enable = true;
      nix-direnv.enable = true;
    };

    # 手書き ~/.gitconfig から移行。credential helper は gh auth (nix profile 側の gh を PATH 解決)。
    git = {
      enable = true;
      lfs.enable = true;
      ignores = [ "**/.claude/settings.local.json" ];
      settings = {
        user = {
          name = "myksyut";
          email = "wizard1026miya@gmail.com";
        };
        credential = {
          # 空文字 helper で既存 helper リスト (osxkeychain 等) をクリアしてから gh を登録
          "https://github.com".helper = [
            ""
            "!gh auth git-credential"
          ];
          "https://gist.github.com".helper = [
            ""
            "!gh auth git-credential"
          ];
        };
      };
    };

    # シェル設定。従来は ~/.zshrc / ~/.zshenv / ~/.zprofile を手書きしていたものを移行。
    # atuin / zoxide / direnv / nix-index の init は各モジュール (enableZshIntegration) が
    # 自動注入するため、initExtra には書かない (二重起動防止)。
    zsh = {
      enable = true;
      enableCompletion = true;
      autosuggestion.enable = true;
      syntaxHighlighting.enable = true;
      history = {
        size = 100000;
        save = 100000;
        path = "$HOME/.zsh_history";
        ignoreDups = true;
        share = true;
      };
      initContent = ''
        [ -f /etc/nix/custom-bundle.pem ] && export NODE_EXTRA_CA_CERTS=/etc/nix/custom-bundle.pem
      '';
      envExtra = ''
        [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
      '';
      profileExtra = ''
        command -v pyenv >/dev/null 2>&1 && eval "$(pyenv init --path)"

        # Added by OrbStack: command-line tools and integration
        source ~/.orbstack/shell/init.zsh 2>/dev/null || :
      '';
      sessionVariables = {
        ZENO_HOME = "$HOME/.config/zeno";
        ZENO_ENABLE_SOCK = "1";
      };
      oh-my-zsh = {
        enable = true;
        theme = "robbyrussell";
        plugins = [ "git" ];
      };
      initExtraBeforeCompInit = ''
        # herdr zsh 補完 (compinit 前に fpath へ追加)
        fpath+=("${pkgs.herdr}/share/zsh/site-functions")
      '';
      initExtra = ''
        # pyenv (legacy: 新規は uv 推奨だが既存互換のため維持)
        export PYENV_ROOT="$HOME/.pyenv"
        [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
        command -v pyenv >/dev/null 2>&1 && eval "$(pyenv init - zsh)"
        export PATH="$HOME/.local/bin:$PATH"

        # mise (asdf 後継のランタイムマネージャ)
        command -v mise >/dev/null 2>&1 && eval "$(mise activate zsh)"

        # Nix版 zed-editor の CLI バイナリは zeditor
        command -v zeditor >/dev/null 2>&1 && alias zed=zeditor

        # zeno.zsh (flake input を ~/.local/share へコピー済み。activation.copyZenoZsh 参照)
        # upstream に zeno.plugin.zsh は無い (旧環境では手動 symlink で対応していた) ので
        # 本体の zeno.zsh を直接 source し、ZENO_ROOT も明示する ($0 解決に頼らない)。
        if [ -f "$HOME/.local/share/zeno-zsh/zeno.zsh" ]; then
          export ZENO_ROOT="$HOME/.local/share/zeno-zsh"
          source "$HOME/.local/share/zeno-zsh/zeno.zsh"
          bindkey ' '  zeno-auto-snippet
          bindkey '^m' zeno-auto-snippet-and-accept-line
          bindkey '^i' zeno-completion
        fi
      '';
    };

    # Ghostty / Zed は GUI アプリで WSL (NixOS) では実用上意味がないため Darwin のみ enable。
    # WSL では Windows 側 (Windows Terminal / Zed Windows build) を使う前提。
    ghostty = lib.mkIf isDarwin {
      enable = true;
      package = null;
      settings = {
        # --- Zed (Nstlgy Glass Dark) に寄せた appearance ---
        # シンタックスパレットは nord 維持。背景だけ Zed の水色ガラス
        # (background = #1f4a6a @ alpha 80% + blur) に合わせる。
        theme = "nord";
        background = "1f4a6a";
        background-opacity = 0.80;
        background-blur-radius = 20;
        selection-background = "2a6885"; # Zed の surface.background 色
        # Zed の buffer font (JetBrainsMono Nerd Font 15, calt/liga 有効) に統一
        font-family = "JetBrainsMono Nerd Font";
        font-size = 15;
        font-feature = [
          "calt"
          "liga"
          "-dlig"
        ];
        adjust-cell-height = "15%"; # Zed line_height "comfortable" 寄りの行間
        cursor-style = "bar"; # Zed の cursor_shape = bar
        cursor-style-blink = false; # Zed の cursor_blink = false
        macos-titlebar-style = "tabs"; # タブをタイトルバー同居させてエディタ風に

        window-padding-x = 20;
        window-padding-y = 5;
        window-padding-balance = true;
        fullscreen = true;
        macos-non-native-fullscreen = true;
        keybind = [ "ctrl+j=ignore" ];
      };
    };

    zed-editor = lib.mkIf isDarwin {
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
        # 水色(アクア寄りのライトブルー)ベース。エディタ部は alpha=cc (≒80%)、パネル/バーは e6 (≒90%)。
        # editor/panel/terminal などは元から #00000000 (完全透過) で background に重なる構造のため、background を下げれば全体に反映される。
        theme_overrides = {
          "Nstlgy Glass Dark" = {
            "background.appearance" = "blurred";
            background = "#1f4a6acc";
            "surface.background" = "#2a6885e6";
            "status_bar.background" = "#2a6885e6";
            "title_bar.background" = "#2a6885e6";
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
        vim_mode = true;
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
      # 各 binding は Cursor base keymap が Editor / Terminal context で
      # 同キーを別アクションに bind しているのを上書きするため、複数 context に登録する。
      userKeymaps = [
        {
          context = "Workspace";
          bindings = {
            "cmd-shift-enter" = "workspace::NewCenterTerminal";
            "cmd-shift-d" = "pane::SplitDown";
            "cmd-d" = "pane::SplitRight";
          };
        }
        {
          context = "Editor";
          bindings = {
            "cmd-shift-enter" = "workspace::NewCenterTerminal";
            "cmd-shift-d" = "pane::SplitDown";
            "cmd-d" = "pane::SplitRight";
            "cmd-alt-d" = "editor::SelectNext";
          };
        }
        {
          context = "Terminal";
          bindings = {
            "cmd-shift-enter" = "workspace::NewCenterTerminal";
            "cmd-shift-d" = "pane::SplitDown";
            "cmd-d" = "pane::SplitRight";
          };
        }
      ];
    };
  };

  # 放置 tmux セッションの定期掃除 (darwin のみ)。prefix+X の手動掃除に加え、
  # idle が閾値 (12h) を超え かつ 開発プロセス (claude/node 等) が動いていない
  # セッションを 6h ごとに無確認 kill する保険。判定ロジックは session-gc.sh と共通。
  launchd.agents.tmux-session-gc = lib.mkIf isDarwin {
    enable = true;
    config = {
      ProgramArguments = [
        "${config.home.homeDirectory}/.config/tmux/session-gc.sh"
        "--auto"
      ];
      EnvironmentVariables = {
        # launchd は PATH 空で起動するため tmux/pgrep/ps/grep を解決できるよう補う。
        PATH = "${config.home.profileDirectory}/bin:/run/current-system/sw/bin:/usr/bin:/bin";
        TMUX_GC_IDLE_HOURS = "12";
      };
      StartInterval = 21600; # 6h ごと
      ProcessType = "Background";
      StandardOutPath = "${config.home.homeDirectory}/Library/Logs/tmux-session-gc.log";
      StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/tmux-session-gc.log";
    };
  };
}
