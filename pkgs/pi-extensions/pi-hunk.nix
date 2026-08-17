{
  lib,
  buildNpmPackage,
  fetchurl,
  jq,
}:

buildNpmPackage rec {
  pname = "pi-hunk";
  version = "0.2.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/pi-hunk/-/pi-hunk-${version}.tgz";
    hash = "sha256-GbZ660zfj1n/6sjcYI8PZiiMrAV/hwn47zgl4CqJqPs=";
  };

  postPatch = ''
    ${lib.getExe jq} 'del(.devDependencies, .peerDependencies, .peerDependenciesMeta, .scripts)' \
      package.json > package.json.min
    mv package.json.min package.json
    cp ${./locks/pi-hunk/package-lock.json} package-lock.json
  '';

  npmDepsHash = "sha256-FliI0vMRcfWAAl4cO7feP8p537ORrgp0a4Wm4Q5EpRA=";
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
    description = "Native persistent Hunk overlay for Pi";
    homepage = "https://github.com/igshehata/pi-hunk";
    license = lib.licenses.mit;
    platforms = lib.platforms.unix;
  };
}
