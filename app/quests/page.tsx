"use client";

import { useEffect, useState } from "react";

import { AccountPage, useApiData } from "../_components/AccountPage";
import { fetchJson } from "../_lib/api";

type Status = "done" | "open" | "unknown";

type Quest = {
  quest_key: string;
  name: string;
  giver: string | null;
  objective: string | null;
  description: string | null;
  status: Status;
  min_level: number | null;
  disabled: boolean;
  alternatives: boolean;
  requires: { quest_key: string; name: string; status: Status }[];
};

type Quests = { characters: number; done: number; open: number; quests: Quest[] };

const STATUS_LABELS: Record<Status, string> = { done: "виконано", open: "відкрито", unknown: "немає в даних" };
const SEARCH_DELAY_MS = 250;

export default function QuestsPage() {
  const summary = useApiData<Quests>("/api/quests");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ query: string; quests: Quest[] } | null>(null);
  const [error, setError] = useState("");

  // Шукаємо з невеликою паузою після введення, щоб не питати бекенд на кожну літеру.
  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchJson<Quests>(`/api/quests?q=${encodeURIComponent(text)}`)
        .then((data) => {
          if (!cancelled) {
            setResults({ query: text, quests: data.quests });
            setError("");
          }
        })
        .catch((err: Error) => !cancelled && setError(err.message));
    }, SEARCH_DELAY_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  const shown = query.trim().length >= 2 && results ? results.quests : [];

  return (
    <AccountPage
      title="Квести"
      subtitle="Квести з твого клієнта гри: хто дає, що зробити й що треба виконати раніше. Стан — зі списків квестів, що приходять при вході персонажами."
      onRecords={summary.reload}
    >
      <section className="inventory-summary">
        <div>
          <span className="muted-label">ВИКОНАНО (У ДАНИХ)</span>
          <strong>{summary.data ? summary.data.done.toLocaleString("uk-UA") : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">ВІДКРИТО</span>
          <strong>{summary.data ? summary.data.open.toLocaleString("uk-UA") : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">ПЕРСОНАЖІВ У ДАНИХ</span>
          <strong>{summary.data ? summary.data.characters : "—"}</strong>
        </div>
      </section>
      <p className="inventory-muted">
        Сервер надсилає не всі виконані квести: у грі лічильник більший, ніж тут, тож «немає в даних» не завжди означає
        «не виконано».
      </p>

      {(summary.error || error) && <p className="inventory-feedback error">{summary.error || error}</p>}

      <section className="panel account-group">
        <div className="inventory-form quest-search">
          <label htmlFor="quest-search">Пошук за назвою квесту, NPC або ключем (наприклад, 40022-14)</label>
          <input
            id="quest-search"
            type="search"
            placeholder="Fughar, Igor Bartali, Kzarka…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {query.trim().length >= 2 && results && results.quests.length === 0 && (
          <p className="inventory-muted">Нічого не знайдено.</p>
        )}

        <ul className="quest-list">
          {shown.map((quest) => (
            <li key={quest.quest_key}>
              <details>
                <summary>
                  <span className="quest-title">
                    <strong>{quest.name}</strong>
                    <small>
                      {quest.giver ?? "—"} · {quest.quest_key}
                      {quest.disabled ? " · вимкнений у грі" : quest.min_level ? ` · з Lv. ${quest.min_level}` : ""}
                    </small>
                  </span>
                  <span className={`journal-status ${quest.status}`}>{STATUS_LABELS[quest.status]}</span>
                </summary>
                <div className="quest-details">
                  {quest.objective && (
                    <p>
                      <b>Завдання:</b> {quest.objective.split(";").join(" · ")}
                    </p>
                  )}
                  {quest.requires.length > 0 && (
                    <div>
                      <b>{quest.alternatives ? "Попередні квести (один із варіантів):" : "Спершу виконати:"}</b>
                      <ul>
                        {quest.requires.map((r) => (
                          <li key={r.quest_key}>
                            {r.name} <small>({r.quest_key})</small>{" "}
                            <span className={`journal-status ${r.status}`}>{STATUS_LABELS[r.status]}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {quest.description && <p className="quest-description">{quest.description}</p>}
                </div>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </AccountPage>
  );
}
