"use client";

import { useState } from "react";

import { AccountPage, useApiData } from "../_components/AccountPage";
import { GameImage } from "../_components/GameImage";
import { fetchJson, formatSilver } from "../_lib/api";

type Gear = {
  slot: number;
  item_id: number;
  name: string | null;
  grade: number | null;
  count: number;
  durability: number | null;
  max_durability: number | null;
  unit_price: number | null;
};

type Servant = {
  kind_id: number;
  kind_name: string | null;
  name: string;
  category: string;
  level_guess: number | null;
  gear: Gear[];
  last_seen: number;
};

type Servants = { servants: Servant[]; missing_names: number };

const CATEGORIES: { key: string; label: string }[] = [
  { key: "ship", label: "Кораблі" },
  { key: "horse", label: "Коні та в'ючні" },
  { key: "camp", label: "Табір" },
];

export default function TransportPage() {
  const { data, error, reload } = useApiData<Servants>("/api/servants");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const servants = data?.servants ?? [];
  const known = new Set(CATEGORIES.map((category) => category.key));
  const groups = [
    ...CATEGORIES,
    ...[...new Set(servants.map((s) => s.category))].filter((c) => !known.has(c)).map((c) => ({ key: c, label: c })),
  ];

  async function run(path: string) {
    setBusy(true);
    setActionError("");
    try {
      await fetchJson(path, { method: "POST" });
      reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не вдалося оновити.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AccountPage
      active="/transport/"
      title="Транспорт"
      subtitle="Коні, кораблі й табір сім'ї зі спорядженням і його міцністю. Назви й ціни предметів — з бази arsha.io та Central Market EU."
      onRecords={reload}
    >
      {servants.length > 0 && (
        <div className="price-status">
          <span>
            {data && data.missing_names > 0
              ? `Без назви ${data.missing_names} предметів спорядження.`
              : "Назви спорядження завантажені."}
          </span>
          <span className="account-actions">
            {data && data.missing_names > 0 && (
              <button className="outline-button" type="button" onClick={() => void run("/api/items/refresh")} disabled={busy}>
                ↻ Дотягнути назви
              </button>
            )}
            <button className="outline-button" type="button" onClick={() => void run("/api/prices/refresh")} disabled={busy}>
              ↻ Оновити ціни
            </button>
          </span>
        </div>
      )}

      {(error || actionError) && <p className="inventory-feedback error">{error || actionError}</p>}

      {data !== null && servants.length === 0 ? (
        <div className="inventory-empty panel">
          <span>◇</span>
          <strong>Транспорту ще немає</strong>
          <p>Увімкни агента й зайди персонажем у світ.</p>
        </div>
      ) : (
        groups.map(({ key, label }) => {
          const group = servants.filter((servant) => servant.category === key);
          if (group.length === 0) return null;
          return (
            <section className="panel account-group" key={key}>
              <div className="eyebrow">{label.toUpperCase()}</div>
              <div className="account-cards">
                {group.map((servant) => (
                  <article className="account-servant" key={`${servant.kind_id}-${servant.name}`}>
                    <div className="account-servant-head">
                      <strong>{servant.name}</strong>
                      <span>{servant.kind_name ?? `тип ${servant.kind_id}`}</span>
                    </div>
                    {servant.gear.length === 0 ? (
                      <p className="inventory-muted">Без спорядження.</p>
                    ) : (
                      <ul className="account-gear">
                        {servant.gear.map((gear) => (
                          <li key={gear.slot}>
                            <GameImage kind="item" id={gear.item_id} size={32} className="account-gear-icon" />
                            <div>
                              <strong>{gear.name ?? `Предмет #${gear.item_id}`}</strong>
                              <span>
                                Слот {gear.slot}
                                {gear.unit_price ? ` · ${formatSilver(gear.unit_price)}` : ""}
                              </span>
                            </div>
                            {gear.max_durability !== null && gear.durability !== null ? (
                              <span className={gear.durability < gear.max_durability * 0.5 ? "warn" : undefined}>
                                {gear.durability}/{gear.max_durability}
                              </span>
                            ) : (
                              <span className="inventory-muted">∞</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </article>
                ))}
              </div>
            </section>
          );
        })
      )}
    </AccountPage>
  );
}
