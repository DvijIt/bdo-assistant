"use client";

import { AccountPage, useApiData } from "../_components/AccountPage";

type Worker = {
  worker_id: string;
  type_id: number;
  type_name: string;
  level: number;
  stamina: number;
  town_id: number;
  town_name: string;
  skills: { id: number; name: string }[];
  last_seen: number;
};

export default function WorkersPage() {
  const { data, error, reload } = useApiData<Worker[]>("/api/workers");
  const workers = data ?? [];

  const towns = new Map<string, Worker[]>();
  for (const worker of workers) {
    towns.set(worker.town_name, [...(towns.get(worker.town_name) ?? []), worker]);
  }
  const exhausted = workers.filter((worker) => worker.stamina === 0).length;

  return (
    <AccountPage
      active="/workers/"
      title="Робітники"
      subtitle="Список робітників приходить один раз при вході у світ. Швидкість роботи, пересування й удачу гра рахує сама — сервер їх не надсилає."
      onRecords={reload}
    >
      <section className="inventory-summary">
        <div>
          <span className="muted-label">РОБІТНИКІВ</span>
          <strong>{data ? workers.length : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">МІСТ</span>
          <strong>{data ? towns.size : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">БЕЗ ВИТРИВАЛОСТІ</span>
          <strong>{data ? exhausted : "—"}</strong>
        </div>
      </section>

      {error && <p className="inventory-feedback error">{error}</p>}

      {data !== null && workers.length === 0 ? (
        <div className="inventory-empty panel">
          <span>◇</span>
          <strong>Робітників ще немає</strong>
          <p>Увімкни агента й зайди персонажем у світ.</p>
        </div>
      ) : (
        [...towns.entries()].map(([town, group]) => (
          <section className="panel account-group" key={town}>
            <div className="inventory-list-heading">
              <div>
                <div className="eyebrow">{group.length} РОБІТН.</div>
                <h2>{town}</h2>
              </div>
            </div>
            <div className="table-scroll">
              <table className="account-table">
                <thead>
                  <tr>
                    <th>Робітник</th>
                    <th>Рівень</th>
                    <th>Витривалість</th>
                    <th>Навички</th>
                  </tr>
                </thead>
                <tbody>
                  {group.map((worker) => (
                    <tr key={worker.worker_id}>
                      <td>{worker.type_name}</td>
                      <td>{worker.level}</td>
                      <td className={worker.stamina === 0 ? "warn" : undefined}>{worker.stamina}</td>
                      <td>
                        {worker.skills.length === 0 ? (
                          <span className="inventory-muted">—</span>
                        ) : (
                          <ul className="chip-list">
                            {worker.skills.map((skill) => (
                              <li key={skill.id} title={`ID ${skill.id}`}>{skill.name}</li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
    </AccountPage>
  );
}
