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
    export PATH=${pkgs.coreutils}/bin:${pkgs.jq}/bin:$PATH
    export AGENT_PI='${extensions.agentPi}'
    export PI_HUNK='${extensions.piHunk}'
    export PLANNOTATOR='${extensions.plannotator}'
    export CONTEXT_VIEW='${extensions.contextView}'
    export WEB_ACCESS='${extensions.webAccess}'
    export SESSION_RECALL='${extensions.sessionRecall}'
    export PI_FFF='${extensions.piFff}'
    export PI_LENS='${extensions.piLens}'
    export RPIV_ASK_USER='${extensions.rpivAskUser}'
    export PI_BTW='${extensions.piBtw}'
    export CODEX_IMAGE_GEN='${extensions.codexImageGen}'
    export PI_VCC='${extensions.piVcc}'
    export PI_LINEAR='${extensions.piLinear}'
    export SKILL_CREATOR='${extensions.skillCreator}'
    export ISSUE_PR_WRITING='${extensions.issuePrWriting}'
    export REMOTE_CONTROL='${extensions.remoteControl}'
    export PI_GOAL='${extensions.piGoal}'
    export CODEX_FAST='${extensions.codexFast}'
    export DEFAULT_PROVIDER='openai-codex'
    export DEFAULT_MODEL='gpt-6-astra'
    export DEFAULT_THINKING_LEVEL='high'
    exec ${pkgs.bash}/bin/bash ${./merge-pi-settings.sh} "$1"
  '';
in
{
  home = {
    file = {
      ".pi/agent/skills/grill-with-docs".source = ../../pkgs/skills/grill-with-docs;

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

    # Disable the pi-web-access curator UI. Keep the file writable so /curator
    # and saveConfig can still update other keys (API keys, provider).
    activation.configureWebSearch = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      web_search_config="$HOME/.pi/web-search.json"
      mkdir -p "$HOME/.pi"
      if [ -L "$web_search_config" ]; then
        mv "$web_search_config" "$web_search_config.before-nix.backup"
      fi
      if [ ! -e "$web_search_config" ]; then
        printf '%s\n' '{"workflow":"none"}' > "$web_search_config"
        chmod 600 "$web_search_config"
      else
        tmp="$(${pkgs.coreutils}/bin/mktemp "$HOME/.pi/.web-search.json.XXXXXX")"
        ${lib.getExe pkgs.jq} '.workflow = "none"' "$web_search_config" > "$tmp"
        mode="$(${pkgs.coreutils}/bin/stat -c '%a' "$web_search_config")"
        ${pkgs.coreutils}/bin/chmod "$mode" "$tmp"
        ${pkgs.coreutils}/bin/mv "$tmp" "$web_search_config"
      fi
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
