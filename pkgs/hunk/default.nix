{
  lib,
  stdenvNoCC,
  fetchurl,
}:

let
  version = "0.18.2";

  # Official standalone binaries from https://github.com/modem-dev/hunk/releases
  # nixpkgs.hunk rebuilds from source via bun and pulls ~1.8GiB of node_modules.
  sources = {
    aarch64-darwin = {
      url = "https://github.com/modem-dev/hunk/releases/download/v${version}/hunkdiff-darwin-arm64.tar.gz";
      hash = "sha256-6CX008IQFt5cdWoTK2ttZrAqFt3xP1PhX8dY+9zToFI=";
    };
  };

  srcInfo =
    sources.${stdenvNoCC.hostPlatform.system}
      or (throw "hunk: no official binary for ${stdenvNoCC.hostPlatform.system} yet");
in
stdenvNoCC.mkDerivation {
  pname = "hunk";
  inherit version;

  src = fetchurl {
    inherit (srcInfo) url hash;
  };

  sourceRoot = ".";

  installPhase = ''
    runHook preInstall
    mkdir -p $out/bin
    bin=$(find . -type f -name hunk | head -n1)
    if [ -z "$bin" ]; then
      echo "hunk binary not found in release archive:" >&2
      find . -maxdepth 3 -type f >&2
      exit 1
    fi
    install -m755 "$bin" $out/bin/hunk
    skilldir=$(find . -type d -name skills | head -n1)
    if [ -n "$skilldir" ]; then
      cp -R "$skilldir" $out/skills
    fi
    runHook postInstall
  '';

  dontFixup = true;
  dontStrip = true;

  meta = with lib; {
    description = "Review-first terminal diff viewer for agent-authored changesets";
    homepage = "https://hunk.dev/";
    license = licenses.mit;
    mainProgram = "hunk";
    platforms = builtins.attrNames sources;
    sourceProvenance = [ sourceTypes.binaryNativeCode ];
  };
}
