{
  config,
  lib,
  pkgs,
  ...
}:
let
  isDarwin = pkgs.stdenv.isDarwin;
  # pywal's colorthief backend needs to run in this same Python environment.
  # No mutable ~/.local/share/yabai-config/venv or machine-specific interpreter.
  python = pkgs.python3.withPackages (ps: [
    ps.pywal
    ps.colorthief
    ps.pillow
  ]);
  runtime = pkgs.runCommand "yabai-config-runtime" { } ''
    mkdir -p "$out"
    cp -R ${./runtime}/. "$out/"
    chmod -R u+w "$out"
    ${pkgs.python3}/bin/python3 - "$out" <<'PY'
    from pathlib import Path
    import sys
    root = Path(sys.argv[1])
    substitutions = {
        '@python@': '${python}/bin/python3',
        '@wal@': '${python}/bin/wal',
        '@runtime@': str(root),
        '@paletteSeed@': '${./themes/colors.json}',
        '@zedSeed@': '${./themes/zed-pywal.json}',
    }
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        text = path.read_text()
        for key, value in substitutions.items():
            text = text.replace(key, value)
        path.write_text(text)
        if text.startswith('#!'):
            path.chmod(0o755)
    PY
  '';
  runtimeFile = relative: {
    source = "${runtime}/${relative}";
    force = true;
  };
in
{
  config = lib.mkIf isDarwin {
    home = {
      packages = [ pkgs.nerd-fonts.hack ];
      sessionPath = [
        "${config.home.homeDirectory}/.local/bin"
        "/opt/homebrew/bin"
        "/usr/local/bin"
      ];
      file = {
        ".yabairc" = runtimeFile "yabairc";
        ".skhdrc" = runtimeFile "skhd/skhdrc";
        ".config/skhd/skhdrc" = runtimeFile "skhd/skhdrc";
        ".config/skhd/scripts" = runtimeFile "skhd/scripts";
        ".config/sketchybar" = runtimeFile "sketchybar";
        ".config/borders/bordersrc" = runtimeFile "bordersrc";
        ".local/bin/reload-theme" = runtimeFile "reload-theme.py";
        ".local/bin/yabai-config-tool" = runtimeFile "brew-tool";
      };

      activation = {
        backupDesktopRuntime = lib.hm.dag.entryBetween [ "linkGeneration" ] [ "writeBoundary" ] ''
          run ${python}/bin/python3 ${runtime}/backup-runtime.py
        '';

        # Cache and generated theme stay writable for `reload-theme <image>`.
        # The exported assets under desktop-theme are the declarative source.
        # Existing palettes are retained; `reload-theme --reset-palette` restores Sky Copy.
        seedDesktopTheme = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
          run ${python}/bin/python3 ${runtime}/seed-theme.py
        '';
      };
    };
  };
}
