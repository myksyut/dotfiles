{
  lib,
  stdenvNoCC,
  fetchurl,
}:

let
  version = "0.24.4";

  # Official binaries from https://github.com/janekbaraniewski/openusage/releases
  # nixpkgs.openusage is a different macOS GUI (robinebers/openusage).
  sources = {
    aarch64-darwin = {
      url = "https://github.com/janekbaraniewski/openusage/releases/download/v${version}/openusage_${version}_darwin_arm64.tar.gz";
      hash = "sha256-5WssIjwTF3ixmICKtCs+Xzn/LQGVBmxIkPAM/xh+h6o=";
    };
    x86_64-linux = {
      url = "https://github.com/janekbaraniewski/openusage/releases/download/v${version}/openusage_${version}_linux_amd64.tar.gz";
      hash = "sha256-/lhzkVVlHr2aqtAzTOuGRSBpRKd7yKfQpPazTshsmzA=";
    };
    aarch64-linux = {
      url = "https://github.com/janekbaraniewski/openusage/releases/download/v${version}/openusage_${version}_linux_arm64.tar.gz";
      hash = "sha256-XAenoNkNmqxmvT2Ozy2joQ/EhecEFSwPa7EcAfQ/4ug=";
    };
  };

  srcInfo =
    sources.${stdenvNoCC.hostPlatform.system}
      or (throw "openusage: no official binary for ${stdenvNoCC.hostPlatform.system} yet");
in
stdenvNoCC.mkDerivation {
  pname = "openusage";
  inherit version;

  src = fetchurl {
    inherit (srcInfo) url hash;
  };

  sourceRoot = ".";

  installPhase = ''
    runHook preInstall
    mkdir -p $out/bin
    bin=$(find . -type f -name openusage | head -n1)
    if [ -z "$bin" ]; then
      echo "openusage binary not found in release archive:" >&2
      find . -maxdepth 3 -type f >&2
      exit 1
    fi
    install -m755 "$bin" $out/bin/openusage
    runHook postInstall
  '';

  dontFixup = true;
  dontStrip = true;

  meta = with lib; {
    description = "Terminal dashboard for AI tool spend, quotas, and rate limits";
    homepage = "https://openusage.sh/";
    license = licenses.mit;
    mainProgram = "openusage";
    platforms = builtins.attrNames sources;
    sourceProvenance = [ sourceTypes.binaryNativeCode ];
  };
}
