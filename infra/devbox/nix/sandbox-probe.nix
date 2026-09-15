# Trusted seed-only fixture. Evidence of host build UID is collected outside.
{ nixPackage, marker }:
derivation {
  name = "devbox-sandbox-probe";
  system = "x86_64-linux";
  builder = "${builtins.storePath nixPackage}/bin/nix";
  DEVBOX_SANDBOX_MARKER = marker;
  args = [
    "--extra-experimental-features"
    "nix-command"
    "--offline"
    "--store"
    "dummy://"
    "eval"
    "--impure"
    "--write-to"
    (builtins.placeholder "out")
    "--expr"
    ''
      let
        marker = builtins.getEnv "DEVBOX_SANDBOX_MARKER";
        # Bounded work makes the short-lived builder observable from outside.
        payload = builtins.concatStringsSep "" (builtins.genList (_: "0123456789abcdef") 65536);
        work = builtins.foldl' (acc: _: builtins.hashString "sha256" (acc + payload)) "" (builtins.genList (i: i) 64);
      in
        assert marker != "";
        assert !(builtins.pathExists marker);
        assert builtins.stringLength work == 64;
        "marker-hidden\n"
    ''
  ];
  preferLocalBuild = true;
  allowSubstitutes = false;
}
