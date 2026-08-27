{
  lib,
  buildNpmPackage,
  fetchurl,
  jq,
}:

{
  pname,
  version,
  hash,
  npmDepsHash,
  lockDir,
  description,
  homepage,
  license ? lib.licenses.mit,
  npmName ? pname,
  npmDepsFetcherVersion ? 1,
  additionalDependencies ? { },
  postPatchExtra ? "",
}:

let
  tarballName = lib.last (lib.splitString "/" npmName);
in
buildNpmPackage {
  inherit
    pname
    version
    npmDepsHash
    npmDepsFetcherVersion
    ;

  src = fetchurl {
    url = "https://registry.npmjs.org/${npmName}/-/${tarballName}-${version}.tgz";
    inherit hash;
  };

  postPatch = ''
    ${lib.getExe jq} --argjson additionalDependencies '${builtins.toJSON additionalDependencies}' \
      'del(.devDependencies, .peerDependencies, .peerDependenciesMeta, .scripts) | .dependencies = ((.dependencies // {}) + $additionalDependencies)' \
      package.json > package.json.min
    mv package.json.min package.json
    cp ${lockDir}/package-lock.json package-lock.json
    ${postPatchExtra}
  '';

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
    inherit description homepage license;
    platforms = lib.platforms.unix;
  };
}
