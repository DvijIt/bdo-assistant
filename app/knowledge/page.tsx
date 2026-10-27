"use client";

import { AccountPage, useApiData } from "../_components/AccountPage";
import { formatSeen } from "../_lib/api";

type Knowledge = {
  total: number;
  ecology_points: number | null;
  updated_at: number | null;
  by_level: { level: number; grade: string | null; count: number }[];
};

export default function KnowledgePage() {
  const { data, error, reload } = useApiData<Knowledge>("/api/knowledge");
  const largest = Math.max(1, ...(data?.by_level ?? []).map((row) => row.count));

  return (
    <AccountPage
      active="/knowledge/"
      title="Знання"
      subtitle="Книга знань сім'ї приходить при вході у світ. Сервер шле лише номери знань і їхній рівень — назв і розділів у трафіку немає."
      onRecords={reload}
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

      {error && <p className="inventory-feedback error">{error}</p>}

      {data !== null && data.total === 0 ? (
        <div className="inventory-empty panel">
          <span>◇</span>
          <strong>Знань ще немає</strong>
          <p>Увімкни агента й зайди персонажем у світ.</p>
        </div>
      ) : (
        data && (
          <section className="panel">
            <div className="eyebrow">РОЗПОДІЛ ЗА РІВНЯМИ</div>
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
              Букви рівнів (C…SS) — імовірна відповідність, ще не перевірена на конкретних знаннях. Знання без
              рівня (персонажі, географія) теж рахуються як найнижчий рівень.
            </p>
          </section>
        )
      )}
    </AccountPage>
  );
}
