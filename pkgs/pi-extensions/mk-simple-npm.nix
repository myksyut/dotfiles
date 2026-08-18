{
  lib,
  stdenvNoCC,
  fetchurl,
}:

{
  pname,
  version,
  hash,
  description,
  homepage,
  license ? lib.licenses.mit,
  npmName ? pname,
}:

let
  tarballName = lib.last (lib.splitString "/" npmName);
in
stdenvNoCC.mkDerivation {
  inherit pname version;

  src = fetchurl {
    url = "https://registry.npmjs.org/${npmName}/-/${tarballName}-${version}.tgz";
    inherit hash;
  };

  sourceRoot = "package";
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp -R . $out/
    runHook postInstall
  '';

  meta = {
    inherit description homepage license;
    platforms = lib.platforms.unix;
  };
}
