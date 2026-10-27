"use client";

import Link from "next/link";
import { ReactNode, useEffect, useRef, useState } from "react";

import { AgentStatus, fetchJson, formatSeen } from "../_lib/api";

const PAGES = [
  { href: "/characters/", label: "Персонажі" },
  { href: "/workers/", label: "Робітники" },
  { href: "/transport/", label: "Транспорт" },
  { href: "/knowledge/", label: "Знання" },
  { href: "/inventory/", label: "Ресурси" },
];

const STATE_LABELS: Record<AgentStatus["state"], string> = {
  stopped: "Агент вимкнено",
  starting: "Агент запускається…",
  running: "Агент слухає гру",
  error: "Помилка агента",
};

const POLL_MS = 3000;

/** Каркас сторінок акаунта: шапка, навігація й панель агента.
 * `onRecords` викликається, коли агент записав нові дані — сторінка перезавантажує свої. */
export function AccountPage({
  active,
  title,
  subtitle,
  onRecords,
  children,
}: {
  active: string;
  title: string;
  subtitle: string;
  onRecords: () => void;
  children: ReactNode;
}) {
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [agentError, setAgentError] = useState("");
  const [busy, setBusy] = useState(false);
  const records = useRef<number | null>(null);
  const reload = useRef(onRecords);

  useEffect(() => {
    reload.current = onRecords;
  });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const status = await fetchJson<AgentStatus>("/api/agent");
        if (cancelled) return;
        setAgent(status);
        setAgentError("");
        if (records.current !== null && status.records !== records.current) reload.current();
        records.current = status.records;
      } catch {
        if (!cancelled) setAgentError("API недоступний — перевір, що бекенд запущено.");
      }
    }

    void poll();
    const timer = setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  async function toggleAgent() {
    if (!agent) return;
    setBusy(true);
    try {
      const running = agent.state === "running" || agent.state === "starting";
      setAgent(await fetchJson<AgentStatus>(`/api/agent/${running ? "stop" : "start"}`, { method: "POST" }));
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : "Не вдалося змінити стан агента.");
    } finally {
      setBusy(false);
    }
  }

  const running = agent?.state === "running" || agent?.state === "starting";

  return (
    <main className="inventory-page">
      <header className="inventory-header">
        <Link href="/" className="inventory-back">← Головна панель</Link>
        <div className="eyebrow">BLACK DESERT ONLINE / EU</div>
        <h1>{title}<span className="gold">.</span></h1>
        <p className="inventory-subtitle">{subtitle}</p>
        <nav className="account-nav">
          {PAGES.map((page) => (
            <Link key={page.href} href={page.href} className={page.href === active ? "active" : undefined}>
              {page.label}
            </Link>
          ))}
        </nav>
      </header>

      <section className={`agent-bar ${agent?.state ?? "unknown"}`}>
        <div className="connection-dot" />
        <div className="agent-bar-copy">
          <strong>{agent ? STATE_LABELS[agent.state] : "Стан агента невідомий"}</strong>
          <span>
            {agentError ||
              agent?.error ||
              (agent && running
                ? `${agent.messages.toLocaleString("uk-UA")} повідомлень · ${agent.records} записів` +
                  (agent.last_record_at ? ` · останній ${formatSeen(agent.last_record_at)}` : "")
                : "Дані приходять лише при вході персонажем у світ — увімкни агента до входу.")}
          </span>
        </div>
        <button className="outline-button" type="button" onClick={() => void toggleAgent()} disabled={!agent || busy}>
          {running ? "■ Зупинити" : "▶ Увімкнути агента"}
        </button>
      </section>

      {children}

      <footer className="inventory-footer">
        BDO COMPANION / Локальний прототип · Неофіційний фан-проєкт
      </footer>
    </main>
  );
}

/** Завантажує дані сторінки й перезавантажує їх на вимогу (`reload`). */
export function useApiData<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchJson<T>(path)
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setError("");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`${err.message}. Перевір, що API запущено.`);
      });
    return () => {
      cancelled = true;
    };
  }, [path, version]);

  return { data, error, reload: () => setVersion((v) => v + 1) };
}
