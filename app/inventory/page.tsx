"use client";

import Link from "next/link";
import { ChangeEvent, useEffect, useState } from "react";

type ContainerKind = "inventory" | "currency" | "storage";

type Holding = {
  item_id: number;
  name: string | null;
  grade: number | null;
  enhancement: number;
  quantity: number;
};

type Container = {
  id: number;
  kind: ContainerKind;
  game_code: number;
  name: string;
  character: string | null;
  observed_at: string;
  items: Holding[];
};

type Holdings = {
  containers: Container[];
  missing_names: number;
};

type Snapshot = {
  id: number;
  taken_at: string;
  character: string;
  storage_status: string | null;
  stacks: number;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SILVER_ITEM_ID = 1;

const kindLabels: Record<ContainerKind, string> = {
  inventory: "Інвентар",
  currency: "Валюти",
  storage: "Склади міст",
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
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

function loadAll() {
  return Promise.all([
    fetchJson<Holdings>("/api/holdings"),
    fetchJson<Snapshot[]>("/api/snapshots"),
  ]);
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("uk-UA", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function InventoryPage() {
  const [holdings, setHoldings] = useState<Holdings | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  function applyLoaded([nextHoldings, nextSnapshots]: [Holdings, Snapshot[]]) {
    setHoldings(nextHoldings);
    setSnapshots(nextSnapshots);
  }

  useEffect(() => {
    let cancelled = false;

    loadAll()
      .then((data) => {
        if (!cancelled) applyLoaded(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`${err.message}. Перевір, що API запущено.`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setBusy(true);
    setError("");
    setMessage("");

    try {
      let data: unknown;
      try {
        data = JSON.parse(await file.text());
      } catch {
        throw new Error("Файл не є коректним JSON.");
      }

      const summary = await fetchJson<{
        inventory_stacks: number;
        storage_stacks: number;
        missing_names: number;
      }>("/api/snapshots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });

      applyLoaded(await loadAll());
      setMessage(
        `Знімок імпортовано: ${summary.inventory_stacks} стеків в інвентарі, ` +
          `${summary.storage_stacks} на складах.` +
          (summary.missing_names
            ? ` Без назви лишилось ${summary.missing_names} предметів.`
            : "")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося імпортувати знімок.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshNames() {
    setBusy(true);
    setError("");

    try {
      await fetchJson("/api/items/refresh", { method: "POST" });
      applyLoaded(await loadAll());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося оновити назви.");
    } finally {
      setBusy(false);
    }
  }

  const containers = holdings?.containers ?? [];
  const stacks = containers
    .filter((container) => container.kind !== "currency")
    .reduce((sum, container) => sum + container.items.length, 0);
  const storagesWithItems = containers.filter(
    (container) => container.kind === "storage" && container.items.length > 0
  ).length;
  const silver = containers
    .filter((container) => container.kind === "currency")
    .flatMap((container) => container.items)
    .find((holding) => holding.item_id === SILVER_ITEM_ID)?.quantity;

  return (
    <main className="inventory-page">
      <header className="inventory-header">
        <Link href="/" className="inventory-back">← Головна панель</Link>
        <div className="eyebrow">BLACK DESERT ONLINE / EU</div>
        <h1>Мій інвентар<span className="gold">.</span></h1>
        <p className="inventory-subtitle">
          Предмети зі знімків bdo-toolkit: для кожного складу й вкладки
          показано останній стан, який бачив знімок.
        </p>
      </header>

      <section className="inventory-summary">
        <div>
          <span className="muted-label">СТЕКІВ ПРЕДМЕТІВ</span>
          <strong>{stacks.toLocaleString("uk-UA")}</strong>
        </div>
        <div>
          <span className="muted-label">СКЛАДІВ З ПРЕДМЕТАМИ</span>
          <strong>{storagesWithItems}</strong>
        </div>
        <div>
          <span className="muted-label">СРІБЛО В ІНВЕНТАРІ</span>
          <strong>{silver === undefined ? "—" : silver.toLocaleString("uk-UA")}</strong>
        </div>
      </section>

      <div className="inventory-layout">
        <section className="panel">
          <div className="eyebrow">IMPORT</div>
          <h2>Імпорт знімка</h2>
          <p className="inventory-muted">
            Вибери JSON з папки snapshots після запуску snapshot.py. Склади
            приходять лише з першого входу після запуску гри, інвентар — з
            будь-якого входу чи зміни персонажа.
          </p>

          <div className="inventory-form">
            <label htmlFor="snapshot-file">Файл знімка (.json)</label>
            <input
              id="snapshot-file"
              type="file"
              accept="application/json,.json"
              onChange={(event) => void handleFile(event)}
              disabled={busy}
            />
          </div>

          {error && <p className="inventory-feedback error">{error}</p>}
          {message && <p className="inventory-feedback">{message}</p>}

          {holdings && holdings.missing_names > 0 && (
            <button
              className="outline-button snapshot-refresh"
              type="button"
              onClick={() => void refreshNames()}
              disabled={busy}
            >
              ↻ Дотягнути назви ({holdings.missing_names})
            </button>
          )}

          <div className="eyebrow snapshot-list-title">ЗНІМКИ</div>
          {snapshots.length === 0 ? (
            <p className="inventory-muted">Ще нічого не імпортовано.</p>
          ) : (
            <ul className="snapshot-list">
              {snapshots.map((snapshot) => (
                <li key={snapshot.id}>
                  <strong>{formatDate(snapshot.taken_at)}</strong>
                  <span>
                    {snapshot.character} · {snapshot.stacks} записів
                    {snapshot.storage_status === "compatible" && " · склади"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="inventory-list-heading">
            <div>
              <div className="eyebrow">YOUR ACCOUNT</div>
              <h2>Поточний стан</h2>
            </div>
          </div>

          {loading ? (
            <p className="inventory-muted">Завантаження...</p>
          ) : containers.length === 0 ? (
            <div className="inventory-empty">
              <span>◇</span>
              <strong>Даних ще немає</strong>
              <p>Імпортуй перший знімок у панелі ліворуч.</p>
            </div>
          ) : (
            (["inventory", "currency", "storage"] as const).map((kind) => {
              const group = containers.filter((container) => container.kind === kind);
              if (group.length === 0) return null;

              return (
                <div className="holdings-kind" key={kind}>
                  <div className="eyebrow">{kindLabels[kind].toUpperCase()}</div>
                  {group.map((container) => (
                    <details className="holdings-group" key={container.id}>
                      <summary>
                        <strong>{container.name}</strong>
                        <span>
                          {container.items.length} · {formatDate(container.observed_at)}
                        </span>
                      </summary>

                      {container.items.length === 0 ? (
                        <p className="inventory-muted">Порожньо.</p>
                      ) : (
                        <div className="inventory-items">
                          {container.items.map((holding, index) => (
                            <article
                              className="inventory-item"
                              key={`${holding.item_id}-${holding.enhancement}-${index}`}
                            >
                              <div
                                className={`inventory-item-icon ${holding.enhancement > 0 ? "enhanced" : ""}`}
                              >
                                {holding.enhancement > 0 ? `+${holding.enhancement}` : "◇"}
                              </div>
                              <div className="inventory-item-copy">
                                <strong>{holding.name ?? `Предмет #${holding.item_id}`}</strong>
                                <span>ID {holding.item_id}</span>
                              </div>
                              <div className="inventory-item-actions">
                                <strong>×{holding.quantity.toLocaleString("uk-UA")}</strong>
                              </div>
                            </article>
                          ))}
                        </div>
                      )}
                    </details>
                  ))}
                </div>
              );
            })
          )}
        </section>
      </div>

      <footer className="inventory-footer">
        BDO COMPANION / Локальний прототип · Неофіційний фан-проєкт
      </footer>
    </main>
  );
}
