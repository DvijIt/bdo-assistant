"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { fetchJson } from "../_lib/api";

type Status = "ok" | "close" | "low" | "unknown";

type Spot = {
  spot_id: number;
  name: string;
  region: string | null;
  sheet_ap: number | null;
  sheet_dp: number | null;
  on_map: boolean;
  status: Status;
};

type Gear = { ap: number | null; dp: number | null };

type Grind = { gear: Gear; spots: Spot[] };

const STATUS_LABELS: Record<Status, string> = {
  ok: "підходить",
  close: "трохи не вистачає",
  low: "заслабко",
  unknown: "—",
};

function diff(have: number | null, need: number | null) {
  if (have === null || !need) return null;
  const delta = have - need;
  return delta >= 0 ? `+${delta}` : String(delta);
}

export default function GrindPage() {
  const { data, error, reload } = useApiData<Grind>("/api/grind");
  const [form, setForm] = useState<{ ap: string; dp: string } | null>(null);
  const [region, setRegion] = useState("");
  const [onlyFitting, setOnlyFitting] = useState(false);
  const [saveError, setSaveError] = useState("");
  const gear = data?.gear;
  const values = form ?? { ap: gear?.ap?.toString() ?? "", dp: gear?.dp?.toString() ?? "" };

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaveError("");
    try {
      await fetchJson("/api/gear", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ap: Number(values.ap), dp: Number(values.dp) }),
      });
      setForm(null);
      reload();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Не вдалося зберегти.");
    }
  }

  const spots = data?.spots ?? [];
  const regions = [...new Set(spots.map((s) => s.region).filter((r): r is string => Boolean(r)))].sort();
  const shown = spots.filter(
    (s) => (!region || s.region === region) && (!onlyFitting || s.status === "ok" || s.status === "close"),
  );
  const count = (status: Status) => spots.filter((s) => s.status === status).length;

  return (
    <AccountPage
      title="Гринд"
      subtitle="Місця для гринду з Monster Zone Info твого клієнта гри з рекомендованими AP/DP. Свої AP/DP введи сам: сервер їх не надсилає, гра рахує їх на твоєму ПК."
      onRecords={reload}
    >
      {(error || saveError) && <p className="inventory-feedback error">{error || saveError}</p>}

      <section className="panel account-group">
        <div className="eyebrow">МОЇ AP / DP</div>
        <form className="grind-gear" onSubmit={(e) => void save(e)}>
          <label>
            AP
            <input
              type="number"
              min={0}
              max={1000}
              required
              value={values.ap}
              onChange={(e) => setForm({ ...values, ap: e.target.value })}
            />
          </label>
          <label>
            DP
            <input
              type="number"
              min={0}
              max={1000}
              required
              value={values.dp}
              onChange={(e) => setForm({ ...values, dp: e.target.value })}
            />
          </label>
          <button className="primary-button" type="submit" disabled={!form}>
            Зберегти
          </button>
        </form>
        <p className="inventory-muted">
          Значення з вікна персонажа (без баффів). «Трохи не вистачає» — обидва показники щонайменше 90 % від
          рекомендованих.
        </p>
      </section>

      {data !== null && spots.length === 0 ? (
        <EmptyState title="Місць для гринду ще немає">
          Імпортуй вивід bdo-data-extractor на сторінці <Link className="text-link" href="/game-data/">«Дані гри»</Link>.
        </EmptyState>
      ) : (
        <>
          <section className="inventory-summary">
            <div>
              <span className="muted-label">ПІДХОДИТЬ</span>
              <strong className="grind-ok">{gear?.ap != null ? count("ok") : "—"}</strong>
            </div>
            <div>
              <span className="muted-label">ТРОХИ НЕ ВИСТАЧАЄ</span>
              <strong className="grind-close">{gear?.ap != null ? count("close") : "—"}</strong>
            </div>
            <div>
              <span className="muted-label">ЗАСЛАБКО</span>
              <strong>{gear?.ap != null ? count("low") : "—"}</strong>
            </div>
          </section>

          <section className="panel account-group">
            <div className="grind-filters">
              <select value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Регіон">
                <option value="">Усі регіони</option>
                {regions.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              <label>
                <input type="checkbox" checked={onlyFitting} onChange={(e) => setOnlyFitting(e.target.checked)} />
                Лише ті, що підходять або майже
              </label>
            </div>
            <div className="table-scroll">
              <table className="account-table grind-table">
                <thead>
                  <tr>
                    <th>Місце</th>
                    <th>AP</th>
                    <th>DP</th>
                    <th>Стан</th>
                    <th aria-label="Карта" />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((spot) => (
                    <tr key={spot.spot_id} className={`grind-${spot.status}`}>
                      <td>
                        <strong>{spot.name}</strong>
                        {spot.region && <small>{spot.region}</small>}
                      </td>
                      <td>
                        {spot.sheet_ap ?? "—"}
                        {diff(gear?.ap ?? null, spot.sheet_ap) && <small>{diff(gear?.ap ?? null, spot.sheet_ap)}</small>}
                      </td>
                      <td>
                        {spot.sheet_dp ?? "—"}
                        {diff(gear?.dp ?? null, spot.sheet_dp) && <small>{diff(gear?.dp ?? null, spot.sheet_dp)}</small>}
                      </td>
                      <td><span className={`grind-status ${spot.status}`}>{STATUS_LABELS[spot.status]}</span></td>
                      <td>
                        {spot.on_map && (
                          <Link className="text-link" href={`/map/?spot=${spot.spot_id}`}>на карті</Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="inventory-muted">Дроп і шанси вирішує сервер, у клієнті їх немає.</p>
          </section>
        </>
      )}
    </AccountPage>
  );
}
