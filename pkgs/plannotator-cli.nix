{
  lib,
  stdenv,
  fetchurl,
}:

let
  version = "0.27.8";
  assets = {
    aarch64-darwin = {
      name = "plannotator-darwin-arm64";
      hash = "sha256-E71OrlkWwRksP3H9TIcigp1wdueBhQ/WoO8v/G8WzGs=";
    };
    x86_64-linux = {
      name = "plannotator-linux-x64";
      hash = "sha256-owcUKEOYRvwqtoBGfrYZwsipAidcKKepZxk69XU7F9Y=";
    };
  };
  asset =
    assets.${stdenv.hostPlatform.system}
      or (throw "plannotator-cli: unsupported system ${stdenv.hostPlatform.system}");
in
stdenv.mkDerivation {
  pname = "plannotator";
  inherit version;

  src = fetchurl {
    url = "https://github.com/backnotprop/plannotator/releases/download/v${version}/${asset.name}";
    inherit (asset) hash;
  };

  dontUnpack = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out/bin
    cp $src $out/bin/plannotator
    chmod +x $out/bin/plannotator
    runHook postInstall
  '';

  meta = {
    description = "Visual plan review CLI for Claude Code hooks";
    homepage = "https://github.com/backnotprop/plannotator";
    license = lib.licenses.mit;
    mainProgram = "plannotator";
    platforms = builtins.attrNames assets;
  };
}
