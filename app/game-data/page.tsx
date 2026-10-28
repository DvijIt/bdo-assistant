"use client";

import { FormEvent, useState } from "react";

import { AccountPage, useApiData } from "../_components/AccountPage";
import { fetchJson, formatSeen } from "../_lib/api";

type Status = {
  source: string;
  imported_at: number;
  counts: Record<string, number>;
  images?: { items: boolean; knowledge: boolean };
} | null;

const COUNT_LABELS: Record<string, string> = {
  knowledge: "знань",
  categories: "розділів знань",
  quests: "квестів",
  characters: "персонажів, робітників і транспорту",
  worker_skills: "навичок робітників",
  nodes: "вузлів і міст",
  items: "предметів",
};

export default function GameDataPage() {
  const status = useApiData<Status>("/api/game-data");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function importData(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const counts = await fetchJson<Record<string, number>>("/api/game-data/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: path.trim() || status.data?.source }),
      });
      setMessage(`Імпортовано: ${Object.entries(counts).map(([k, v]) => `${v.toLocaleString("uk-UA")} ${COUNT_LABELS[k] ?? k}`).join(", ")}.`);
      status.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося імпортувати.");
    } finally {
      setBusy(false);
    }
  }

  const current = status.data;

  return (
    <AccountPage
      title="Дані гри"
      subtitle="Назви й картинки знань, квестів, робітників, міст, транспорту й предметів — з твого власного клієнта гри. Застосунок лише читає готовий вивід bdo-data-extractor: файли гри він не відкриває й нікуди не надсилає."
      onRecords={() => undefined}
    >
      <section className="panel account-group">
        <div className="eyebrow">СТАН</div>
        {current ? (
          <>
            <h2>Імпортовано {formatSeen(current.imported_at)}</h2>
            <p className="inventory-muted">Папка: {current.source}</p>
            {current.images && (
              <p className="inventory-muted">
                Картинки: предмети {current.images.items ? "є" : "немає"}, знання {current.images.knowledge ? "є" : "немає"}.
              </p>
            )}
            <dl className="account-facts account-facts-wide">
              {Object.entries(current.counts).map(([key, value]) => (
                <div key={key}><dt>{COUNT_LABELS[key] ?? key}</dt><dd>{value.toLocaleString("uk-UA")}</dd></div>
              ))}
            </dl>
          </>
        ) : (
          <h2>Ще не імпортовано</h2>
        )}
      </section>

      <section className="panel account-group">
        <div className="eyebrow">ЯК ОНОВИТИ (ПІСЛЯ ПАТЧА)</div>
        <ol className="game-data-steps">
          <li>
            Один раз встанови <a href="https://go.dev/dl/" target="_blank" rel="noreferrer">Go</a>. Випуск
            extractor v0.1.9 не читає клієнт 3464+ (змінились таблиці баффів і досвіду), тож збирай із локальної
            копії з виправленнями — <code className="inline">bdo-spike\bdo-data-extractor-pr6</code> (v0.1.9 + PR #6
            + досвід для 3483). Коли вийде новий випуск, підійде й{" "}
            <code className="inline">go install github.com/idevelopthings/bdo-data-extractor@latest</code>.
          </li>
          <li>
            З папки копії згенеруй таблиці зі свого клієнта (гра може бути закрита; extractor лише читає файли):
            <code>go run . build --game D:\BlackDesert --out D:\Projects\bdo-data --lang en</code>
            <code>go run . loc --game D:\BlackDesert --out D:\Projects\bdo-data --lang en</code>
            Шлях після <code className="inline">--game</code> — твоя папка гри.
          </li>
          <li>
            За бажанням — картинки предметів і знань (сотні МБ; після <code className="inline">build</code>):
            <code>go run . icons --game D:\BlackDesert --out D:\Projects\bdo-data</code>
            <code>go run . knowledge-icons --game D:\BlackDesert --out D:\Projects\bdo-data</code>
          </li>
          <li>Вкажи папку з результатом нижче й натисни «Імпортувати». Картинки не копіюються — їх показуємо прямо з цієї папки.</li>
        </ol>
        <form className="inventory-form game-data-form" onSubmit={(e) => void importData(e)}>
          <label htmlFor="game-data-path">Папка з виводом extractor</label>
          <input
            id="game-data-path"
            type="text"
            placeholder={current?.source ?? "D:\\bdo-data"}
            value={path}
            onChange={(e) => setPath(e.target.value)}
            disabled={busy}
          />
          <button className="primary-button" type="submit" disabled={busy || !(path.trim() || current?.source)}>
            {busy ? "Імпорт…" : "Імпортувати"}
          </button>
        </form>
        {(status.error || error) && <p className="inventory-feedback error">{status.error || error}</p>}
        {message && <p className="inventory-feedback">{message}</p>}
        <p className="inventory-muted">
          Таблиці лишаються лише в локальній базі. Ознаки «сімейний / персонажа» для квестів extractor не дає.
        </p>
      </section>
    </AccountPage>
  );
}
