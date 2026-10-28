"use client";

import Link from "next/link";
import { useState } from "react";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { GameImage } from "../_components/GameImage";
import { fetchJson, formatSeen } from "../_lib/api";

type Knowledge = {
  total: number;
  ecology_points: number | null;
  updated_at: number | null;
  by_level: { level: number; grade: string | null; count: number }[];
  ungraded: number | null;
  names_loaded: number;
};

type CategoryRow = { category_id: number; name: string; total: number; gained: number; has_children: boolean };
type Entry = { knowledge_id: number; name: string; gained: boolean; level: number | null; grade: string | null };
type CategoryView = { categories: CategoryRow[]; entries: Entry[] };

function Progress({ gained, total }: { gained: number; total: number }) {
  return (
    <span className="knowledge-progress">
      <span className="progress-track">
        <span className="progress-fill" style={{ width: `${total ? (100 * gained) / total : 0}%` }} />
      </span>
      <small>{gained} / {total}</small>
    </span>
  );
}

/** Розділ знань, що підвантажує підрозділи й знання при першому розгортанні. */
function Category({ row, version }: { row: CategoryRow; version: number }) {
  const [view, setView] = useState<CategoryView | null>(null);
  const [error, setError] = useState("");

  async function load() {
    if (view) return;
    try {
      setView(await fetchJson<CategoryView>(`/api/knowledge/categories?parent=${row.category_id}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося завантажити розділ.");
    }
  }

  return (
    <details className="knowledge-category" onToggle={(e) => (e.currentTarget.open ? void load() : undefined)}>
      <summary>
        <strong>{row.name}</strong>
        <Progress gained={row.gained} total={row.total} />
      </summary>
      {error && <p className="inventory-feedback error">{error}</p>}
      {!view && !error && <p className="inventory-muted">Завантаження...</p>}
      {view && (
        <div className="knowledge-children">
          {view.categories.map((child) => (
            <Category key={`${child.category_id}-${version}`} row={child} version={version} />
          ))}
          {view.entries.length > 0 && (
            <ul className="knowledge-entries">
              {view.entries.map((entry) => (
                <li key={entry.knowledge_id} className={entry.gained ? undefined : "missing"} title={`ID ${entry.knowledge_id}`}>
                  <GameImage
                    kind="knowledge"
                    id={entry.knowledge_id}
                    size={28}
                    className="knowledge-entry-image"
                    fallback={<span className="knowledge-entry-image" aria-hidden="true" />}
                  />
                  <span className="knowledge-entry-name">{entry.name}</span>
                  <span className="knowledge-entry-state">
                    {!entry.gained ? "не зібрано" : entry.grade && entry.grade !== "—" ? <b>{entry.grade}</b> : "✓"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </details>
  );
}

export default function KnowledgePage() {
  const summary = useApiData<Knowledge>("/api/knowledge");
  const roots = useApiData<CategoryView>("/api/knowledge/categories");
  const [version, setVersion] = useState(0);
  const data = summary.data;
  const largest = Math.max(1, ...(data?.by_level ?? []).map((row) => row.count));

  function reloadAll() {
    summary.reload();
    roots.reload();
    setVersion((v) => v + 1);
  }

  return (
    <AccountPage
      title="Знання"
      subtitle="Книга знань сім'ї приходить при вході у світ (лише номери й рівні). Назви, розділи й картинки — з твого клієнта гри."
      onRecords={reloadAll}
    >
      <section className="inventory-summary">
        <div>
          <span className="muted-label">ЗНАНЬ ЗІБРАНО</span>
          <strong>{data?.total ? data.total.toLocaleString("uk-UA") : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">ОЧКИ ЕКОЛОГІЇ</span>
          <strong>{data?.ecology_points != null ? data.ecology_points.toLocaleString("uk-UA") : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">ОНОВЛЕНО</span>
          <strong className="account-summary-date">{data?.updated_at ? formatSeen(data.updated_at) : "—"}</strong>
        </div>
      </section>

      {summary.error && <p className="inventory-feedback error">{summary.error}</p>}

      {data && !data.names_loaded && (
        <section className="panel account-group">
          <div className="eyebrow">НАЗВИ ЗНАНЬ</div>
          <h2>Назви ще не завантажено</h2>
          <p className="inventory-muted">
            Без них знання показуються лише кількістю. Імпортуй вивід bdo-data-extractor на сторінці{" "}
            <Link className="text-link" href="/game-data/">«Дані гри»</Link> — з&apos;явиться дерево розділів із прогресом.
          </p>
        </section>
      )}

      {data !== null && data.total === 0 ? (
        <EmptyState title="Знань ще немає">Увімкни агента й зайди персонажем у світ.</EmptyState>
      ) : (
        data && (
          <section className="panel account-group">
            <div className="eyebrow">РОЗПОДІЛ ЗА РІВНЯМИ{data.ungraded != null ? " (ЕКОЛОГІЯ Й ТОРГІВЛЯ)" : ""}</div>
            <ul className="knowledge-levels">
              {data.by_level.map((row) => (
                <li key={row.level}>
                  <span className="knowledge-grade">{row.grade ?? `#${row.level}`}</span>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${(100 * row.count) / largest}%` }} />
                  </div>
                  <strong>{row.count.toLocaleString("uk-UA")}</strong>
                </li>
              ))}
            </ul>
            <p className="inventory-muted">
              C, B, A і S звірено з грою (S — це рівень 5). Букву для рівня 4 ще не підтверджено.
              {data.ungraded != null
                ? ` Ще ${data.ungraded.toLocaleString("uk-UA")} знань — без рівня (персонажі, географія тощо).`
                : " Доки назви не завантажено, знання без рівня рахуються як C."}
            </p>
          </section>
        )
      )}

      {data?.names_loaded ? (
        <section className="panel account-group">
          <div className="eyebrow">РОЗДІЛИ</div>
          {roots.error && <p className="inventory-feedback error">{roots.error}</p>}
          <div className="knowledge-tree">
            {(roots.data?.categories ?? []).map((row) => (
              <Category key={`${row.category_id}-${version}`} row={row} version={version} />
            ))}
          </div>
        </section>
      ) : null}
    </AccountPage>
  );
}
