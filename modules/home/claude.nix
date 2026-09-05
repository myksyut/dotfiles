{
  pkgs,
  lib,
  config,
  ...
}:

let
  skillsRoot = ../../pkgs/skills;
  issuePrWriting = ../../pkgs/pi-extensions/skills/issue-pr-writing;
  hook = ./claude/plan-grill-gate.sh;
  claudeMd = ./claude/CLAUDE.md;
  plannotatorCli = pkgs.callPackage ../../pkgs/plannotator-cli.nix { };
  plannotatorBin = lib.getExe plannotatorCli;

  settings = {
    language = "日本語";
    env = {
      CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = "1";
    };
    permissions = {
      defaultMode = "auto";
    };
    fileCheckpointingEnabled = true;
    skipDangerousModePermissionPrompt = true;
    enabledPlugins = {
      "plannotator@plannotator" = true;
      "linear@claude-plugins-official" = true;
      "skill-creator@claude-plugins-official" = true;
      "pyright-lsp@claude-plugins-official" = true;
      "figma@claude-plugins-official" = false;
      "frontend-design@claude-plugins-official" = false;
      "pev-harness@pev-harness" = false;
      "notion@claude-plugins-official" = false;
      "accuracy-iteration-loop@emuni-skills" = false;
    };
    extraKnownMarketplaces = {
      plannotator = {
        source = {
          source = "github";
          repo = "backnotprop/plannotator";
        };
      };
    };
    hooks = {
      PreToolUse = [
        {
          matcher = "EnterPlanMode";
          hooks = [
            {
              type = "command";
              command = "${plannotatorBin} improve-context";
              timeout = 5;
            }
          ];
        }
        {
          matcher = "Write|Edit|NotebookEdit";
          hooks = [
            {
              type = "command";
              command = "${config.home.homeDirectory}/.claude/hooks/plan-grill-gate.sh";
            }
          ];
        }
      ];
      PermissionRequest = [
        {
          matcher = "ExitPlanMode";
          hooks = [
            {
              type = "command";
              command = plannotatorBin;
              timeout = 345600;
            }
          ];
        }
      ];
    };
  };

  installPlugins = pkgs.writeShellScript "install-claude-plugins" ''
        set -euo pipefail
        claude_bin="${lib.getExe pkgs.claude-code}"
        if command -v claude >/dev/null 2>&1; then
          claude_bin="$(command -v claude)"
        fi
        if [ ! -x "$claude_bin" ]; then
          echo "claude-code is not executable; skip plugin install" >&2
          exit 0
        fi
        yes_flag=()
        if "$claude_bin" plugin install --help 2>&1 | ${pkgs.gnugrep}/bin/grep -q -- '-y'; then
          yes_flag=(-y)
        fi
        run_limited() {
          ${lib.getExe pkgs.python3} - "$claude_bin" "$@" <<'PY'
    import subprocess, sys
    cmd = sys.argv[1:]
    try:
        subprocess.run(cmd, timeout=45, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        print("timed out: " + " ".join(cmd), file=sys.stderr)
    PY
        }
        run_limited plugin marketplace add https://github.com/backnotprop/plannotator.git --scope user || true
        run_limited plugin install plannotator@plannotator "''${yes_flag[@]}" -s user || true
        run_limited plugin install linear@claude-plugins-official "''${yes_flag[@]}" -s user || true
        run_limited plugin install skill-creator@claude-plugins-official "''${yes_flag[@]}" -s user || true
        run_limited plugin install pyright-lsp@claude-plugins-official "''${yes_flag[@]}" -s user || true
  '';
in
{
  home.packages = [ plannotatorCli ];

  home.file = {
    ".claude/CLAUDE.md" = {
      force = true;
      source = claudeMd;
    };
    ".claude/hooks/plan-grill-gate.sh" = {
      force = true;
      executable = true;
      source = hook;
    };
    ".claude/skills/grill-with-docs" = {
      force = true;
      source = skillsRoot + "/grill-with-docs";
    };
    ".claude/skills/codex-image-gen" = {
      force = true;
      source = skillsRoot + "/codex-image-gen";
    };
    ".claude/skills/pi-goal" = {
      force = true;
      source = skillsRoot + "/pi-goal";
    };
    ".claude/skills/issue-pr-writing" = {
      force = true;
      source = issuePrWriting;
    };
    ".claude/skills/archify".source =
      config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.pi/agent/skills/archify";
  };

  home.activation.configureClaudeCode = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    settings_path="$HOME/.claude/settings.json"
    mkdir -p "$HOME/.claude"
    if [ -e "$settings_path" ] && [ ! -e "$settings_path.before-nix.backup" ]; then
      cp "$settings_path" "$settings_path.before-nix.backup"
    fi
    ${lib.getExe pkgs.jq} -n --argjson settings '${builtins.toJSON settings}' '$settings' > "$settings_path"
    chmod 600 "$settings_path"
    run ${installPlugins} || echo "claude plugin install failed (non-fatal)" >&2
  '';
}
