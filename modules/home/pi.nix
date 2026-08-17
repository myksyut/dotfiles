{
  pkgs,
  lib,
  agent-pi,
  ...
}:

let
  extensions = import ../../pkgs/pi-extensions {
    inherit pkgs;
    agentPiSrc = agent-pi;
  };

  mergePiPackages = pkgs.writeShellScript "merge-pi-packages" ''
    set -euo pipefail

    settings_path="''${1:?settings path is required}"
    settings_dir="$(${pkgs.coreutils}/bin/dirname "$settings_path")"
    ${pkgs.coreutils}/bin/mkdir -p "$settings_dir"

    if [ ! -e "$settings_path" ]; then
      ${pkgs.coreutils}/bin/printf '%s\n' '{}' > "$settings_path"
      ${pkgs.coreutils}/bin/chmod 600 "$settings_path"
    fi

    mode="$(${pkgs.coreutils}/bin/stat -c '%a' "$settings_path")"
    tmp="$(${pkgs.coreutils}/bin/mktemp "$settings_dir/.settings.json.XXXXXX")"

    ${lib.getExe pkgs.jq} \
      --arg agentPi '${extensions.agentPi}' \
      --arg piHunk '${extensions.piHunk}' \
      --arg plannotator '${extensions.plannotator}' \
      --arg contextView '${extensions.contextView}' \
      --arg claudeAuth '${extensions.claudeAuth}' \
      '
        def source:
          if type == "string" then .
          elif type == "object" then (.source // "")
          else ""
          end;
        def managed:
          (source | test("^(git:github.com/(ruizrica|myksyut)/agent-pi|npm:pi-hunk|npm:@plannotator/pi-extension|npm:pi-context-view(@.*)?$|npm:pi-claude-auth(@.*)?$|npm:@pankajudhas81/pi-claude-auth(@.*)?$|/nix/store/[a-z0-9]+-(agent-pi|pi-hunk|plannotator-pi-extension|pi-context-view|pi-claude-auth)-)"));
        .packages = (
          ((.packages // []) | map(select(managed | not)))
          + [
            { source: $agentPi, extensions: ["!extensions/user-question.ts"] },
            $piHunk,
            $plannotator,
            $contextView,
            $claudeAuth
          ]
        )
      ' "$settings_path" > "$tmp"

    ${pkgs.coreutils}/bin/chmod "$mode" "$tmp"
    ${pkgs.coreutils}/bin/mv "$tmp" "$settings_path"
  '';
in
{
  home = {
    sessionVariables.AGENT_PI_PLAN_REVIEWER = "plannotator";

    file = {
      ".pi/agent/hunk.json".text = builtins.toJSON {
        review = "off";
        followEdits = true;
        hunk = {
          command = "hunk";
          args = [
            "diff"
            "--watch"
          ];
        };
        overlay.layout = "full";
        bindings = {
          prefix = "ctrl+space";
          toggle = "h";
          show = "s";
        };
      };

      ".pi/agent/plannotator.json".text = builtins.toJSON {
        executionMode = "external";
      };

      # Shift+Tabをagent-piのmode切替に譲るため、thinking切替は別キーに移す。
      ".pi/agent/keybindings.json".text = builtins.toJSON {
        "app.thinking.cycle" = "ctrl+shift+t";
      };

      # agent-pi model routing (roles + difficulty tiers). Distinct from
      # ~/.pi/agent/models.json which is Pi's provider catalog.
      ".pi/agents/models.json".text = builtins.toJSON {
        default = {
          provider = "xai";
          model = "grok-4.6";
        };
        tiers = {
          easy = {
            provider = "openai-codex";
            model = "gpt-5.6-luna";
          };
          mid = {
            provider = "xai";
            model = "grok-4.6";
          };
          hard = {
            provider = "anthropic";
            model = "claude-fable-5";
          };
        };
        kinds = {
          design = {
            provider = "anthropic";
            model = "claude-fable-5";
          };
          architecture = {
            provider = "anthropic";
            model = "claude-fable-5";
          };
          review = {
            provider = "openai-codex";
            model = "gpt-5.6-sol";
          };
        };
        agents = {
          scout = {
            provider = "x-ai";
            model = "grok-4.1-fast";
          };
          ranger = {
            provider = "openai-codex";
            model = "gpt-5.4";
          };
          builder = {
            provider = "anthropic";
            model = "claude-haiku-4-5";
          };
          paladin = {
            provider = "anthropic";
            model = "claude-opus-4-6";
          };
          reviewer = {
            provider = "openai-codex";
            model = "gpt-5.6-sol";
          };
          warden = {
            provider = "anthropic";
            model = "claude-opus-4-6";
          };
          planner = {
            provider = "openai-codex";
            model = "gpt-5.4";
          };
          tester = {
            provider = "openai-codex";
            model = "gpt-5.4";
          };
          herald = {
            provider = "openai-codex";
            model = "gpt-5.4";
          };
          "red-team" = {
            provider = "openai-codex";
            model = "gpt-5.4";
          };
          knight = {
            provider = "openai-codex";
            model = "gpt-5.4";
          };
          "rlm-subcall" = {
            provider = "anthropic";
            model = "claude-haiku-4-5";
          };
        };
      };
    };

    activation.configurePiPackages = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      run ${mergePiPackages} "$HOME/.pi/agent/settings.json"
    '';
  };
}
