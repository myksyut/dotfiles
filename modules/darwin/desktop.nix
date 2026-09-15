{
  # Signed Homebrew distributions preserve the GUI apps' and window managers'
  # macOS identities. Homebrew owns installation; Home Manager owns services.
  homebrew = {
    taps = [
      {
        name = "asmvik/formulae";
        trusted = true;
      }
      {
        name = "FelixKratz/formulae";
        trusted = true;
      }
      {
        name = "stablyai/orca";
        trusted = true;
      }
    ];
    brews = [
      "asmvik/formulae/yabai"
      "asmvik/formulae/skhd"
      "FelixKratz/formulae/borders"
      "FelixKratz/formulae/sketchybar"
      "blueutil"
    ];
    casks = [
      "font-hack-nerd-font"
      "zen"
      "stablyai/orca/orca"
    ];
  };

  # Match the choices already made on this Mac.
  system.defaults.WindowManager = {
    EnableTilingByEdgeDrag = false;
    EnableTopTilingByEdgeDrag = false;
    EnableTiledWindowMargins = false;
  };
  system.defaults.CustomUserPreferences."com.floatytool.floaty" = {
    launchAtLogin = false;
    shakeToPinEnabled = false;
  };
}
