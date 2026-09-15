# No nixpkgs download: use the installed Nix executable and its registered closure.
# The inner evaluator is impure so the marker is hidden by the OS sandbox,
# not by Nix's pure-evaluation path restrictions.
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
      let marker = builtins.getEnv "DEVBOX_SANDBOX_MARKER";
      in assert marker != ""; assert !(builtins.pathExists marker); "marker-hidden\n"
    ''
  ];
  preferLocalBuild = true;
  allowSubstitutes = false;
}
