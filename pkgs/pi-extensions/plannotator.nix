{
  lib,
  buildNpmPackage,
  fetchurl,
  jq,
}:

buildNpmPackage rec {
  pname = "plannotator-pi-extension";
  version = "0.27.3";

  src = fetchurl {
    url = "https://registry.npmjs.org/@plannotator/pi-extension/-/pi-extension-${version}.tgz";
    hash = "sha256-FPvuuWtePwE1Krdz8djVe/4O9bTd+ab7nlj0JKEv6yQ=";
  };

  postPatch = ''
    ${lib.getExe jq} 'del(.devDependencies, .peerDependencies, .peerDependenciesMeta, .scripts)' \
      package.json > package.json.min
    mv package.json.min package.json
    cp ${./locks/plannotator/package-lock.json} package-lock.json
  '';

  npmDepsHash = "sha256-80ArstQ0mdzXcjfXRFDKKTHNVGiT9YXirWDCKdkTifA=";
  npmFlags = [
    "--omit=dev"
    "--legacy-peer-deps"
  ];
  dontNpmBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp -R . $out/
    runHook postInstall
  '';

  meta = {
    description = "Visual plan and document review extension for Pi";
    homepage = "https://github.com/backnotprop/plannotator";
    license = with lib.licenses; [
      mit
      asl20
    ];
    platforms = lib.platforms.unix;
  };
}
