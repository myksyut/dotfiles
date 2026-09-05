{
  lib,
  buildNpmPackage,
  rsync,
  src,
}:

buildNpmPackage {
  pname = "agent-pi";
  version = "2.2.0";
  inherit src;

  npmDepsHash = "sha256-MnZhcEg0xyetjamtN9Vatdg8SRy61SMvF2zBPkc+yYQ=";
  dontNpmBuild = true;

  postPatch = ''
    patch -p1 < ${./patches/agent-pi-tool-caller-security.patch}
    patch -p1 < ${./patches/agent-pi-shortcuts.patch}
    patch -p1 < ${./patches/agent-pi-runtime-paths.patch}
    patch -p1 < ${./patches/agent-pi-plan-grill-gate.patch}
    patch -p1 < ${./patches/agent-pi-security-notifications.patch}
  '';

  nativeBuildInputs = [ rsync ];

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    # These upstream symlinks point at the maintainer's private checkout and
    # are already unusable outside that machine. Keep them out of the package.
    rsync -a \
      --exclude=/commands/toolkit \
      --exclude=/prompts/toolkit \
      ./ $out/
    runHook postInstall
  '';

  meta = {
    description = "Multi-agent orchestration suite for Pi";
    homepage = "https://github.com/myksyut/agent-pi";
    license = lib.licenses.mit;
    platforms = lib.platforms.unix;
  };
}
