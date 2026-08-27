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
      --arg webAccess '${extensions.webAccess}' \
      --arg sessionRecall '${extensions.sessionRecall}' \
      --arg piFff '${extensions.piFff}' \
      --arg piLens '${extensions.piLens}' \
      --arg rpivAskUser '${extensions.rpivAskUser}' \
      --arg piBtw '${extensions.piBtw}' \
      --arg codexImageGen '${extensions.codexImageGen}' \
      --arg piVcc '${extensions.piVcc}' \
      --arg piLinear '${extensions.piLinear}' \
      --arg skillCreator '${extensions.skillCreator}' \
      --arg issuePrWriting '${extensions.issuePrWriting}' \
      --arg remoteControl '${extensions.remoteControl}' \
      --arg piGoal '${extensions.piGoal}' \
      --arg codexFast '${extensions.codexFast}' \
      '
        def source:
          if type == "string" then .
          elif type == "object" then (.source // "")
          else ""
          end;
        def managed:
          (source | test("^(git:github.com/(ruizrica|myksyut)/agent-pi|npm:(pi-hunk|@plannotator/pi-extension|pi-context-view|pi-ask-user|pi-web-access|@ogulcancelik/pi-session-recall|@ff-labs/pi-fff|pi-lens|@juicesharp/rpiv-ask-user-question|pi-btw|pi-codex-image-gen|@sting8k/pi-vcc|@alasano/pi-linear|@tmustier/pi-skill-creator|pi-remote-control|@narumitw/pi-goal|@calesennett/pi-codex-fast|pi-claude-auth|@pankajudhas81/pi-claude-auth)(@.*)?$|(.*/)?nix/store/[a-z0-9]+-(agent-pi|pi-hunk|plannotator-pi-extension|pi-context-view|pi-web-access|pi-session-recall|pi-fff|pi-lens|rpiv-ask-user-question|pi-btw|pi-codex-image-gen|pi-vcc|pi-linear|pi-skill-creator|aipr-writing|issue-pr-writing|pi-remote-control|pi-goal|pi-codex-fast|pi-claude-auth)-)"));
        .packages = (
          ((.packages // []) | map(select(managed | not)))
          + [
            { source: $agentPi, extensions: ["!extensions/user-question.ts"] },
            $piHunk,
            $plannotator,
            $contextView,
            $webAccess,
            $sessionRecall,
            $piFff,
            $piLens,
            $rpivAskUser,
            $piBtw,
            $codexImageGen,
            $piVcc,
            $piLinear,
            $skillCreator,
            $issuePrWriting,
            $remoteControl,
            $piGoal,
            { source: $codexFast, extensions: ["extensions/codex-fast.ts"] }
          ]
        )
      ' "$settings_path" > "$tmp"

    ${pkgs.coreutils}/bin/chmod "$mode" "$tmp"
    ${pkgs.coreutils}/bin/mv "$tmp" "$settings_path"
  '';
in
{
  home = {
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

      # Keep local environment files out of pi-lens diagnostics and project scans.
      ".pi-lens/config.json".text = builtins.toJSON {
        ignore = [ ".env" ];
      };

      # Shift+Tabをagent-piのmode切替に譲るため、thinking切替は別キーに移す。
      ".pi/agent/keybindings.json".text = builtins.toJSON {
        "app.thinking.cycle" = "ctrl+shift+t";
      };

      # Pi's provider catalog: override GPT-5.6 models to use 1.05M context window.
      # Built-in default is 272K (short-context pricing tier).
      ".pi/agent/models.json".text = builtins.toJSON {
        providers = {
          openai-codex = {
            modelOverrides = {
              "gpt-5.6-sol" = {
                contextWindow = 1050000;
              };
              "gpt-5.6-luna" = {
                contextWindow = 1050000;
              };
              "gpt-5.6-terra" = {
                contextWindow = 1050000;
              };
            };
          };
        };
      };

      # agent-pi model routing (roles + difficulty tiers). Distinct from
      # ~/.pi/agent/models.json which is Pi's provider catalog.
      ".pi/agents/models.json".text = builtins.toJSON {
        default = {
          provider = "openai-codex";
          model = "gpt-5.6-luna";
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
            provider = "openai-codex";
            model = "gpt-5.6-luna";
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

    # The daemon rewrites config.json on startup, so keep it as a writable file
    # rather than a Home Manager symlink into the Nix store.
    activation.configureRemoteControl = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
            remote_control_dir="$HOME/.pi/remote-control"
            remote_control_config="$remote_control_dir/config.json"
            mkdir -p "$remote_control_dir"
            if [ -L "$remote_control_config" ]; then
              mv "$remote_control_config" "$remote_control_config.before-nix.backup"
            fi
            if [ ! -e "$remote_control_config" ]; then
              cat > "$remote_control_config" <<'EOF'
      {
        "bindAddress": "100.82.209.42:17373",
        "advertisedBaseUrl": "http://100.82.209.42:17373"
      }
      EOF
              chmod 600 "$remote_control_config"
            fi
    '';
  };
}
