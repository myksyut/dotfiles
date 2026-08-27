{
  lib,
  stdenvNoCC,
  src,
}:

stdenvNoCC.mkDerivation {
  pname = "issue-pr-writing";
  version = "0.2.0";
  inherit src;

  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp -R ./* $out/
    runHook postInstall
  '';

  meta = {
    description = "Linear Issue and GitHub pull request writing skill for Pi";
    homepage = "https://github.com/emuni-kyoto/ai_patent_rocket_web_mvp/tree/main/.claude/skills/aipr-writing";
    license = lib.licenses.mit;
    platforms = lib.platforms.unix;
  };
}
