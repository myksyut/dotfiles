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
        .packages = (
          ((.packages // []) | map(select(
            (type != "string") or (
              . != "git:github.com/ruizrica/agent-pi" and
              . != "git:github.com/myksyut/agent-pi" and
              . != "npm:pi-hunk" and
              . != "npm:@plannotator/pi-extension" and
              (test("^npm:pi-context-view(@.*)?$") | not) and
              (test("^npm:pi-claude-auth(@.*)?$") | not) and
              (test("^npm:@pankajudhas81/pi-claude-auth(@.*)?$") | not) and
              (test("^/nix/store/[a-z0-9]+-(agent-pi|pi-hunk|plannotator-pi-extension|pi-context-view|pi-claude-auth)-") | not)
            )
          ))) + [$agentPi, $piHunk, $plannotator, $contextView, $claudeAuth]
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
    };

    activation.configurePiPackages = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      run ${mergePiPackages} "$HOME/.pi/agent/settings.json"
    '';
  };
}
