{
  lib,
  buildNpmPackage,
  fetchurl,
  jq,
  makeWrapper,
  nodejs_22,
}:

buildNpmPackage {
  pname = "pi-acp";
  version = "0.0.33";
  nodejs = nodejs_22;

  src = fetchurl {
    url = "https://registry.npmjs.org/pi-acp/-/pi-acp-0.0.33.tgz";
    hash = "sha256-n964pngMBWsywHJC81kIRHIAcwjhq1d1fzM53ZYw3ks=";
  };

  npmDepsHash = "sha256-fUJ/ZsvvN5J8XjqY+zBlWNK6e8DoJo7PFsJsqC6cIj0=";

  postPatch = ''
    ${lib.getExe jq} 'del(.devDependencies, .peerDependencies, .peerDependenciesMeta, .scripts)' \
      package.json > package.json.min
    mv package.json.min package.json
    cp ${./locks/pi-acp/package-lock.json} package-lock.json
  '';

  npmFlags = [ "--omit=dev" ];
  dontNpmBuild = true;
  nativeBuildInputs = [ makeWrapper ];

  installPhase = ''
    runHook preInstall
    mkdir -p $out/lib/pi-acp $out/bin
    cp -R . $out/lib/pi-acp/
    makeWrapper ${nodejs_22}/bin/node $out/bin/pi-acp \
      --run 'if [ "''${1:-}" = "--version" ]; then echo "0.0.33"; exit 0; fi' \
      --add-flags "$out/lib/pi-acp/dist/index.js"
    runHook postInstall
  '';

  meta = {
    description = "ACP adapter for the pi coding agent";
    homepage = "https://github.com/svkozak/pi-acp";
    license = lib.licenses.mit;
    mainProgram = "pi-acp";
    platforms = lib.platforms.unix;
  };
}
