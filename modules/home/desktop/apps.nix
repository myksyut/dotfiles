{
  pkgs,
  lib,
  config,
  ...
}:

let
  python = pkgs.python3.withPackages (ps: [ ps.lz4 ]);
  applyAppThemes = pkgs.writeShellApplication {
    name = "desktop-app-themes";
    text = ''
      exec ${python}/bin/python ${./apply-app-themes.py} \
        --spec ${./themes/zen-workspaces.json} \
        --orca-spec ${./themes/orca-theme.json} "$@"
    '';
  };
  importRaycastTheme = pkgs.writeShellApplication {
    name = "desktop-raycast-theme";
    text = ''
      printf '%s\n' 'Raycast: Install Theme → Sky Copyを右クリック → Set as Current (forced)'
      exec /usr/bin/open ${lib.escapeShellArg (lib.strings.trim (builtins.readFile ./themes/Raycast-Sky-Copy.url))}
    '';
  };
in
{
  config = lib.mkIf pkgs.stdenv.isDarwin {
    # Importable assets are immutable; app-owned profiles remain writable.
    xdg.configFile."desktop-theme/assets".source = ./themes;
    home = {
      packages = [
        applyAppThemes
        importRaycastTheme
      ];
      file = {
        ".local/share/desktop-theme/wallpapers".source = ./themes/wallpapers;
        "Library/Application Support/com.mitchellh.ghostty/config.ghostty" = {
          force = true;
          source = ./themes/ghostty.conf;
        };
      };
      activation.applyDesktopAppThemes = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
        run ${applyAppThemes}/bin/desktop-app-themes --app all --apply --defer-running --quiet
      '';
    };

    # App-owned files are merged after normal app exit, including newly initialized profiles.
    launchd.agents.desktop-app-themes = {
      enable = true;
      domain = "gui";
      config = {
        Label = "local.desktop-app-themes";
        ProgramArguments = [
          "${applyAppThemes}/bin/desktop-app-themes"
          "--app"
          "all"
          "--apply"
          "--defer-running"
          "--quiet"
        ];
        RunAtLoad = true;
        StartInterval = 60;
        ProcessType = "Background";
        EnvironmentVariables.HOME = config.home.homeDirectory;
      };
    };

    # runtime.nix seeds the writable generated theme; reload-theme may update it.
    programs.zed-editor.userSettings = {
      theme = {
        mode = "dark";
        light = "Pywal";
        dark = "Pywal";
      };
      theme_overrides.Pywal = builtins.fromJSON (builtins.readFile ./themes/zed-overrides.json);
    };
  };
}
