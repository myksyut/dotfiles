{
  lib,
  rustPlatform,
  fetchFromGitHub,
}:

rustPlatform.buildRustPackage rec {
  pname = "quotas";
  version = "0.11.0";

  src = fetchFromGitHub {
    owner = "clankercode";
    repo = "quotas";
    rev = "v${version}";
    hash = "sha256-H/cPnlM37ZU/RWYg5d0G7IHoRffntDcRPPlXCxD7OlY=";
  };

  cargoHash = "sha256-j8N+QZ103uzQkVjX1G/uuc1GM+JVWCNPszOYpDzOQDE=";

  doCheck = false;

  meta = with lib; {
    description = "TUI/CLI that auto-detects AI provider credentials and shows usage quotas";
    homepage = "https://github.com/clankercode/quotas";
    license = with licenses; [
      unlicense
      cc0
    ];
    mainProgram = "quotas";
    platforms = platforms.unix;
  };
}
