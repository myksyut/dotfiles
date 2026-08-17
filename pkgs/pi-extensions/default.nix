{ pkgs, agentPiSrc }:

{
  agentPi = pkgs.callPackage ./agent-pi.nix { src = agentPiSrc; };
  piHunk = pkgs.callPackage ./pi-hunk.nix { };
  plannotator = pkgs.callPackage ./plannotator.nix { };
}
