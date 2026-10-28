"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";

import { AgentStatus, fetchJson, formatSeen } from "../_lib/api";

const SECTIONS: { label: string; pages: { href: string; icon: string; label: string }[] }[] = [
  {
    label: "АКАУНТ",
    pages: [
      { href: "/", icon: "◈", label: "Огляд" },
      { href: "/characters/", icon: "⚔", label: "Персонажі" },
      { href: "/inventory/", icon: "◉", label: "Ресурси" },
      { href: "/workers/", icon: "⚒", label: "Робітники" },
      { href: "/nodes/", icon: "⌖", label: "Вузли" },
      { href: "/transport/", icon: "⚓", label: "Транспорт" },
    ],
  },
  {
    label: "ПРОГРЕС",
    pages: [
      { href: "/knowledge/", icon: "✦", label: "Знання" },
      { href: "/quests/", icon: "❖", label: "Квести" },
      { href: "/journals/", icon: "❦", label: "Журнали пригод" },
    ],
  },
  {
    label: "ЩО РОБИТИ",
    pages: [
      { href: "/grind/", icon: "☠", label: "Гринд" },
      { href: "/crafting/", icon: "⚗", label: "Що зготувати" },
      { href: "/gear/", icon: "⛨", label: "Спорядження" },
      { href: "/builds/", icon: "◆", label: "Лайтстоуни й кристали" },
      { href: "/map/", icon: "⊕", label: "Карта" },
    ],
  },
  {
    label: "НАЛАШТУВАННЯ",
    pages: [{ href: "/game-data/", icon: "⚙", label: "Дані гри" }],
  },
];

const STATE_LABELS: Record<AgentStatus["state"], string> = {
  stopped: "Агент вимкнено",
  starting: "Агент запускається…",
  running: "Агент слухає гру",
  error: "Помилка агента",
};

const POLL_MS = 3000;

function inventoryLine(inventory: AgentStatus["inventory"]) {
  if (inventory.note) return inventory.note;
  if (!inventory.enabled) return "Інвентар не знімається.";
  if (!inventory.last) return "Інвентар і склади знімаються при кожному вході у світ.";
  const { last } = inventory;
  return (
    `Інвентар: ${inventory.snapshots} знімк. · останній ${last.character}, ${formatSeen(last.at)} — ` +
    `${last.inventory_stacks} в інвентарі, ${last.storage_stacks} на складах`
  );
}

/** Стан агента з опитуванням; `onRecords` викликається, коли агент записав нові дані. */
function useAgent(onRecords: () => void) {
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
        if (!cancelled) setAgentError("API недоступний — перевір, що застосунок запущено.");
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
  return { agent, agentError, busy, running, toggleAgent };
}

type Agent = ReturnType<typeof useAgent>;

/** Панель агента: стан, лічильники, знімки інвентаря й кнопка ввімкнення. */
function AgentBar({ agent: { agent, agentError, busy, running, toggleAgent } }: { agent: Agent }) {
  return (
    <section className={`agent-bar ${agentError ? "error" : agent?.state ?? "unknown"}`}>
      <div className="connection-dot" />
      <div className="agent-bar-copy">
        <strong>{agentError ? "Немає зв'язку з застосунком" : agent ? STATE_LABELS[agent.state] : "Перевіряю агента…"}</strong>
        <span>
          {agentError ||
            agent?.error ||
            (agent && running
              ? `${agent.messages.toLocaleString("uk-UA")} повідомлень · ${agent.records} записів` +
                (agent.last_record_at ? ` · останній ${formatSeen(agent.last_record_at)}` : "")
              : "Дані приходять лише при вході персонажем у світ — увімкни агента до входу.")}
        </span>
        {agent && running && <span>{inventoryLine(agent.inventory)}</span>}
      </div>
      <button
        className={running ? "outline-button" : "primary-button"}
        type="button"
        onClick={() => void toggleAgent()}
        disabled={!agent || busy}
      >
        {running ? "■ Зупинити" : "▶ Увімкнути агента"}
      </button>
    </section>
  );
}

function normalize(path: string) {
  return path.length > 1 ? path.replace(/\/$/, "") : path;
}

/** Каркас усіх сторінок: бічна навігація, заголовок і панель агента.
 * `onRecords` викликається, коли агент записав нові дані — сторінка перезавантажує свої. */
export function AccountPage({
  title,
  subtitle,
  onRecords,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  onRecords: () => void;
  children: ReactNode;
}) {
  const pathname = normalize(usePathname() ?? "/");
  const agent = useAgent(onRecords);
  const state = agent.agentError ? "error" : agent.agent?.state ?? "unknown";

  // На телефоні меню — смуга, що гортається: показуємо в ній поточний розділ.
  useEffect(() => {
    document.querySelector(".sidebar-nav .nav-item.active")?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [pathname]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <div className="brand-mark">B</div>
          <div>
            <strong>BDO COMPANION</strong>
            <span>BLACK DESERT · EU</span>
          </div>
        </Link>

        <nav className="sidebar-nav" aria-label="Розділи">
          {SECTIONS.map((section) => (
            <div className="nav-section" key={section.label}>
              <div className="nav-label">{section.label}</div>
              {section.pages.map((page) => {
                const active = normalize(page.href) === pathname;
                return (
                  <Link
                    key={page.href}
                    href={page.href}
                    className={`nav-item${active ? " active" : ""}`}
                    aria-current={active ? "page" : undefined}
                  >
                    <span aria-hidden="true">{page.icon}</span>
                    <span>{page.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className={`sidebar-bottom agent-state ${state}`}>
          <div className="connection-dot" />
          <div>
            <strong>{agent.agentError ? "Немає зв'язку" : agent.agent ? STATE_LABELS[agent.agent.state] : "…"}</strong>
            <span>Дані з трафіку гри</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="page-header">
          <div className="eyebrow">BLACK DESERT ONLINE / EU</div>
          <h1>{title}<span className="gold">.</span></h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </header>

        <AgentBar agent={agent} />

        {children}

        <footer className="page-footer">
          <span>BDO COMPANION <span className="gold">/</span> ЛОКАЛЬНО НА ТВОЄМУ ПК</span>
          <span>Неофіційний фан-проєкт · Не пов’язаний із Pearl Abyss</span>
        </footer>
      </main>
    </div>
  );
}

/** Завантажує дані сторінки й перезавантажує їх на вимогу (`reload`). */
export function useApiData<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchJson<T>(path)
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setLoaded(true);
          setError("");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`${err.message}. Перевір, що застосунок запущено.`);
      });
    return () => {
      cancelled = true;
    };
  }, [path, version]);

  // `loaded` відрізняє відповідь null (даних немає) від ще не отриманої відповіді.
  return { data, loaded, error, reload: () => setVersion((v) => v + 1) };
}

/** Порожній стан розділу: що зробити, щоб дані з'явились. */
export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="inventory-empty panel">
      <span aria-hidden="true">◇</span>
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
