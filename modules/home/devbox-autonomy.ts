import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

// Keep optional agent-pi team tools from treating an absent mode as TEAM.
// Pi's own system prompt and the user's AGENTS.md remain authoritative.
export default function devboxAutonomy(pi: ExtensionAPI) {
  const useNormalMode = () => {
    (globalThis as any).__piCurrentMode = "NORMAL";
  };
  useNormalMode();
  pi.on("session_start", useNormalMode);
}
