{
  config,
  lib,
  pkgs,
  ...
}:
let
  home = config.home.homeDirectory;
  labels = {
    yabai = "com.asmvik.yabai";
    skhd = "com.koekeishiya.skhd";
    borders = "sh.brew.borders";
    sketchybar = "sh.brew.sketchybar";
  };
  logDir = "${home}/Library/Logs/yabai-config";
  mkAgent = name: label: {
    enable = true;
    domain = "gui";
    config = {
      Label = label;
      ProgramArguments = [
        "${home}/.local/bin/yabai-config-tool"
        name
      ]
      ++ lib.optionals (name == "yabai" || name == "skhd") [
        "--config"
        (if name == "yabai" then "${home}/.yabairc" else "${home}/.skhdrc")
      ];
      EnvironmentVariables = {
        HOME = home;
        SHELL = "/bin/sh";
        PATH = "${home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${home}/.nix-profile/bin:/etc/profiles/per-user/${config.home.username}/bin:/run/current-system/sw/bin:/usr/bin:/bin:/usr/sbin:/sbin";
        LANG = "en_US.UTF-8";
      };
      RunAtLoad = true;
      KeepAlive = {
        SuccessfulExit = false;
        Crashed = true;
      };
      ThrottleInterval = 10;
      ProcessType = "Interactive";
      StandardOutPath = "${logDir}/${name}.log";
      StandardErrorPath = "${logDir}/${name}.err.log";
    };
  };
in
{
  config = lib.mkIf pkgs.stdenv.isDarwin {
    # Keep existing labels: Home Manager unloads and replaces each matching
    # LaunchAgent instead of starting a second Homebrew-managed instance.
    launchd.agents = lib.mapAttrs mkAgent labels;
    home.activation.prepareDesktopServices =
      lib.hm.dag.entryBetween [ "setupLaunchAgents" ] [ "linkGeneration" "seedDesktopTheme" ]
        ''
          run mkdir -p ${lib.escapeShellArg logDir}
          desktop_backup="${home}/.local/state/yabai-config/launchagents-before-nix"
          for desktop_label in ${lib.concatStringsSep " " (lib.attrValues labels)}; do
            desktop_old="${home}/Library/LaunchAgents/$desktop_label.plist"
            # Save the pre-Nix service definition once before HM replaces it.
            if [[ -f "$desktop_old" && ! -e "$desktop_backup/$desktop_label.plist" ]]; then
              run mkdir -p -m 700 "$desktop_backup"
              run cp -p "$desktop_old" "$desktop_backup/$desktop_label.plist"
            fi
          done
        '';
  };
}
