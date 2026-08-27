{ pkgs, agentPiSrc }:

let
  mkSimple = pkgs.callPackage ./mk-simple-npm.nix { };
  mkNpm = pkgs.callPackage ./mk-npm-extension.nix { };
in
{
  agentPi = pkgs.callPackage ./agent-pi.nix { src = agentPiSrc; };
  piHunk = pkgs.callPackage ./pi-hunk.nix { };
  plannotator = pkgs.callPackage ./plannotator.nix { };
  contextView = pkgs.callPackage ./pi-context-view.nix { };
  issuePrWriting = pkgs.callPackage ./issue-pr-writing.nix {
    src = ./skills/issue-pr-writing;
  };

  piLinear = mkSimple {
    pname = "pi-linear";
    version = "0.5.0";
    npmName = "@alasano/pi-linear";
    hash = "sha256-ytdWNzRXBr4Y6iPfXLmT0Nk90QVrKiT6SXm9A9rwmyw=";
    description = "Linear integration for Pi with 64+ tools, multi-workspace auth, and per-tool settings";
    homepage = "https://github.com/alasano/house-of-pi/tree/main/packages/pi-linear";
  };

  skillCreator = mkSimple {
    pname = "pi-skill-creator";
    version = "0.3.4";
    npmName = "@tmustier/pi-skill-creator";
    hash = "sha256-hGseZJGyNc9JHA4NfjoUUsGqvrDH5FnpYLsPEXhgJe0=";
    postPatchExtra = ''
      substituteInPlace scripts/validate_skill.py \
        --replace-fail '#!/usr/bin/env -S uv run --script' '#!${pkgs.uv}/bin/uv run --script'
    '';
    description = "Guidance for creating Pi-compatible Agent Skills";
    homepage = "https://github.com/tmustier/pi-extensions/tree/main/extending-pi/skill-creator";
  };

  codexFast = mkSimple {
    pname = "pi-codex-fast";
    version = "0.1.6";
    npmName = "@calesennett/pi-codex-fast";
    hash = "sha256-7FbKbDr5kLRsbPRDbt0BWllK5LKhnWmKdUkJN7R9PyQ=";
    postPatchExtra = ''
      patch -p1 < ${./patches/pi-codex-fast-ui.patch}
    '';
    description = "Pi extension for OpenAI Codex Fast and Ultrafast service tiers";
    homepage = "https://github.com/calesennett/pi-codex-fast";
  };

  webAccess = mkNpm {
    pname = "pi-web-access";
    version = "0.23.0";
    hash = "sha256-7ruCilNzGO+8t8hqQ5M5WvOUyfKm5Wjnns/jCTeb50A=";
    npmDepsHash = "sha256-zqkdW04a2esCUueRu7uSxVPlJ0MVpisNmjUNd1qsXK8=";
    lockDir = ./locks/pi-web-access;
    description = "Web search, URL fetch, GitHub clone, PDF extraction, and YouTube understanding for Pi";
    homepage = "https://github.com/nicobailon/pi-web-access";
  };

  sessionRecall = mkSimple {
    pname = "pi-session-recall";
    version = "1.0.6";
    npmName = "@ogulcancelik/pi-session-recall";
    hash = "sha256-NmDvg87Kj/97Y1Oqe5cNqdtvG+h28GDVOcMua21UdIE=";
    description = "Search and query past Pi sessions";
    homepage = "https://github.com/ogulcancelik/pi-extensions/tree/main/packages/pi-session-recall";
  };

  piFff = mkNpm {
    pname = "pi-fff";
    version = "0.10.5";
    npmName = "@ff-labs/pi-fff";
    hash = "sha256-vjZt5SCM4shMsn9wu2LxtH5rRx3a2cZMpZsNw770a2k=";
    npmDepsHash = "sha256-A5yCx5t8+OBDEMe/DUJesY0K8cN7fxfZ2m+bliCtb/I=";
    lockDir = ./locks/pi-fff;
    description = "FFF-powered fuzzy file and content search for Pi";
    homepage = "https://github.com/dmtrKovalenko/fff/tree/main/packages/pi-fff";
  };

  piLens = mkNpm {
    pname = "pi-lens";
    version = "4.0.1";
    hash = "sha256-k76SQZrFSTqgZNC7x5aMi2sFjU2q0dqrjK3DxJYi/Tk=";
    npmDepsHash = "sha256-QqBvDnptmDomoXqvI2jPxF90e4ggSpcDYsdDUZ8azsg=";
    lockDir = ./locks/pi-lens;
    postPatchExtra = ''
      ${pkgs.jq}/bin/jq '.pi.skills = ["./skills"]' package.json > package.json.min
      mv package.json.min package.json
    '';
    description = "Real-time LSP, linter, formatter, and type-check feedback for Pi";
    homepage = "https://github.com/apmantza/pi-lens";
  };

  rpivAskUser = mkNpm {
    pname = "rpiv-ask-user-question";
    version = "2.6.1";
    npmName = "@juicesharp/rpiv-ask-user-question";
    hash = "sha256-JhGQgiLBHUl5frkoIE59rjFpGtYl1oZvogW/xpVz2Mc=";
    npmDepsHash = "sha256-X2KINuhk5+3DGAB5CmdwDp3CG9lDxIW7hippyaIBcCQ=";
    lockDir = ./locks/rpiv-ask-user-question;
    description = "Structured questionnaire the model can put to you instead of guessing";
    homepage = "https://github.com/juicesharp/rpiv-mono/tree/main/packages/rpiv-ask-user-question";
  };

  piBtw = mkSimple {
    pname = "pi-btw";
    version = "0.4.1";
    hash = "sha256-CHzdNUd6Jo+ZMF0YvVoOw6piB+VQl4FHTKImwPwU/GI=";
    postPatchExtra = ''
      ${pkgs.jq}/bin/jq 'del(.pi.skills)' package.json > package.json.min
      mv package.json.min package.json
    '';
    description = "Parallel side conversations with /btw";
    homepage = "https://github.com/dbachelder/pi-btw";
  };

  codexImageGen = mkSimple {
    pname = "pi-codex-image-gen";
    version = "0.1.12";
    hash = "sha256-qL6ie/vFl/Ee18kETuVEBqa9yqnPW0lmnZZi/Q7k13c=";
    description = "Image generation for Pi using ChatGPT Images 2.0";
    homepage = "https://github.com/jvm/pi-mono/tree/main/packages/pi-codex-image-gen";
  };

  piVcc = mkSimple {
    pname = "pi-vcc";
    version = "0.6.0";
    npmName = "@sting8k/pi-vcc";
    hash = "sha256-ucYpUloe2trmI5oRs1hfaoilACkAgjZgR3Cyd2vSWHc=";
    description = "LLM-free structured conversation compaction for Pi";
    homepage = "https://github.com/sting8k/pi-vcc";
  };

  remoteControl = mkNpm {
    pname = "pi-remote-control";
    version = "1.0.5";
    hash = "sha256-ORVFQPswcxGAN/Kzm4yCKsqEOyugDFNkipm7peBksoQ=";
    npmDepsHash = "sha256-JifIqRr459bRRb4KXQXDrtw1MlkRzrNRXZ4rOhZcAoc=";
    npmDepsFetcherVersion = 2;
    additionalDependencies = {
      "@earendil-works/pi-ai" = "^0.84.3";
    };
    postPatchExtra = ''
      cat > src/session-name-generator.ts <<'EOF'
      import type { ActiveSessionNameGenerator } from "./active-session-registry.js";

      // Keep the daemon independent from Pi's changing model-registry API.
      export function createLlmSessionNameGenerator(): ActiveSessionNameGenerator {
        return async () => null;
      }
      EOF
    '';
    lockDir = ./locks/pi-remote-control;
    description = "Authenticated remote control for Pi sessions";
    homepage = "https://github.com/zerray/pi-remote-control";
  };

  piGoal = mkSimple {
    pname = "pi-goal";
    version = "0.53.3";
    npmName = "@narumitw/pi-goal";
    hash = "sha256-/IdkUvfcY236pvtzPwZapqTByIohGZI9IR1+DbzTslg=";
    description = "Pi extension for autonomous single-objective goal completion";
    homepage = "https://github.com/narumiruna/pi-extensions/tree/main/packages/pi-goal";
  };
}
