{ pkgs }:
let
  cli = pkgs.replaceVars ../../tools/devbox/devbox {
    flyctl = "${pkgs.flyctl}/bin/flyctl";
  };
in
pkgs.writeShellScriptBin "devbox" ''
  exec ${pkgs.python3}/bin/python3 ${cli} "$@"
''
