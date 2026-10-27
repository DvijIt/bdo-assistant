export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.json()).detail ?? "";
    } catch {
      // Тіло відповіді не JSON — лишаємо загальне повідомлення.
    }
    throw new Error(detail || `Помилка API: ${response.status}`);
  }
  return response.json();
}

// Срібло в BDO рахують мільйонами й мільярдами.
export function formatSilver(value: number) {
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  return value.toLocaleString("uk-UA");
}

// Агент пише unix-час у секундах.
export function formatSeen(seconds: number) {
  return new Date(seconds * 1000).toLocaleString("uk-UA", { dateStyle: "short", timeStyle: "short" });
}

export type AgentStatus = {
  state: "stopped" | "starting" | "running" | "error";
  error: string | null;
  started_at: number | null;
  messages: number;
  records: number;
  last_record_at: number | null;
  inventory: {
    enabled: boolean;
    note: string | null;
    snapshots: number;
    last: { character: string; at: number; inventory_stacks: number; storage_stacks: number } | null;
  };
};
