{
  config,
  lib,
  pkgs,
  ...
}:
let
  wallpaper = pkgs.writeShellApplication {
    name = "desktop-wallpaper";
    text = ''
      exec ${pkgs.python3}/bin/python3 ${./apply-wallpaper.py} \
        --desktoppr ${pkgs.desktoppr}/bin/desktoppr \
        --image ${lib.escapeShellArg "${config.home.homeDirectory}/.local/share/desktop-theme/wallpapers/loupe-mono-dark.heic"} "$@"
    '';
  };
in
{
  config = lib.mkIf pkgs.stdenv.isDarwin {
    home = {
      packages = [ wallpaper ];
      # The helper preserves manual changes until the declared image hash changes.
      # run keeps all wallpaper and marker writes out of Home Manager dry-runs.
      activation.applyDesktopWallpaper = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
        run ${wallpaper}/bin/desktop-wallpaper
      '';
    };
  };
}
