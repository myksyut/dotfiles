{ pkgs, agentPiSrc }:

{
  agentPi = pkgs.callPackage ./agent-pi.nix { src = agentPiSrc; };
  piHunk = pkgs.callPackage ./pi-hunk.nix { };
  plannotator = pkgs.callPackage ./plannotator.nix { };
  contextView = pkgs.callPackage ./pi-context-view.nix { };
  claudeAuth = pkgs.callPackage ./pi-claude-auth.nix { };
}
