import type { AgentName } from "../types.js";

export const MODEL_PRESETS: Record<
  AgentName,
  readonly { id: string; label: string }[]
> = {
  codex: [
    { id: "gpt-6.1-sol", label: "GPT-6.1 Sol High" },
    { id: "gpt-6-astra", label: "GPT-6 Astra High" },
    { id: "gpt-6-sol", label: "GPT-6 Sol High" },
    { id: "gpt-5.6-sol", label: "GPT-5.6 Sol High" },
  ],
  cursor: [
    { id: "grok-4.7-xhigh-fast", label: "Grok 4.7 Extra High Fast" },
    { id: "claude-opus-5-5-high-fast", label: "Claude Opus 5.5 High Fast" },
    { id: "gpt-5.6-sol-high-fast", label: "GPT-5.6 Sol High Fast" },
    { id: "composer-2.5-fast", label: "Composer 2.5 Fast" },
  ],
};

export function modelLabel(agent: AgentName, id: string): string {
  return MODEL_PRESETS[agent].find((model) => model.id === id)?.label ?? id;
}
