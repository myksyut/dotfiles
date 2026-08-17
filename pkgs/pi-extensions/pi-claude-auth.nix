{
  lib,
  stdenvNoCC,
  fetchurl,
}:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "pi-claude-auth";
  version = "0.1.3";

  src = fetchurl {
    url = "https://registry.npmjs.org/pi-claude-auth/-/pi-claude-auth-${finalAttrs.version}.tgz";
    hash = "sha256-QBNkKnr3v2mCKCU1fMF5cQF4wXMyqqWQRZOBbnc6XWM=";
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
    description = "Use Claude Code credentials with Pi's Anthropic provider";
    homepage = "https://github.com/pankajudhas81/pi-claude-auth";
    license = lib.licenses.mit;
    platforms = lib.platforms.unix;
  };
})
