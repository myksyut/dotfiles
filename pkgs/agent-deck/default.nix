{
  lib,
  buildGoModule,
  fetchFromGitHub,
  git,
}:

buildGoModule rec {
  pname = "agent-deck";
  version = "1.8.3";

  src = fetchFromGitHub {
    owner = "asheshgoplani";
    repo = "agent-deck";
    rev = "v${version}";
    hash = "sha256-XJJmZuGhCenMt5WJsf8zz7P1fPV0sHUAOr2bao4niYI=";
  };

  vendorHash = "sha256-aH32Up3redCpeyjZkjcjiVN0tfYpF+GFB2WVAGm3J2I=";

  subPackages = [ "cmd/agent-deck" ];

  # checkPhase の worktree テストが git を要求する
  nativeCheckInputs = [ git ];

  # テストが $HOME 配下に storage を作るため、サンドボックスの /homeless-shelter (RO) を回避
  preCheck = ''
    export HOME=$(mktemp -d)
  '';

  # TUI起動を伴うテストは sandbox の non-TTY 環境で debug.log を出さず失敗するためスキップ
  checkFlags = [ "-skip=TestLogCgroupIsolationDecision_WiredIntoBootstrap" ];

  meta = with lib; {
    description = "Terminal session manager for AI coding agents (Claude / Gemini / Codex / OpenCode 等)";
    homepage = "https://github.com/asheshgoplani/agent-deck";
    license = licenses.mit;
    mainProgram = "agent-deck";
    platforms = platforms.unix;
  };
}
