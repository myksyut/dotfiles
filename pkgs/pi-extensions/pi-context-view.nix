{
  lib,
  stdenvNoCC,
  fetchurl,
}:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "pi-context-view";
  version = "0.4.2";

  src = fetchurl {
    url = "https://registry.npmjs.org/pi-context-view/-/pi-context-view-${finalAttrs.version}.tgz";
    hash = "sha256-zCTfdDaxfWc1LGukMGBuwvWPkZB8IO9i2pKHNJUvlu8=";
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
    description = "Context usage and injection viewer for Pi";
    homepage = "https://github.com/dimk90/pi-context-view";
    license = lib.licenses.mit;
    platforms = lib.platforms.unix;
  };
})
