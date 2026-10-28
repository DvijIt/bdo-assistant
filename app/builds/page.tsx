"use client";

import { useState } from "react";

import { AccountPage, useApiData } from "../_components/AccountPage";

type Stone = { item_id: number; name: string; count: number; have: number };

type Combo = {
  combo_id: number;
  name: string;
  description: string | null;
  stones: Stone[];
  ready: boolean;
  owned: number;
  total: number;
};

type Builds = { lightstones: Combo[]; crystals: { group_id: number; name: string; max: number }[] };

export default function BuildsPage() {
  const { data, error, reload } = useApiData<Builds>("/api/builds");
  const [query, setQuery] = useState("");
  const [onlyReady, setOnlyReady] = useState(false);
  const combos = data?.lightstones ?? [];
  const text = query.trim().toLowerCase();
  const shown = combos.filter(
    (c) => (!onlyReady || c.ready) &&
      (!text || c.name.toLowerCase().includes(text) || (c.description ?? "").toLowerCase().includes(text) ||
        c.stones.some((s) => s.name.toLowerCase().includes(text))),
  );
  // Ліміт 1000 у грі означає «без обмеження».
  const crystals = (data?.crystals ?? []).filter((c) => c.max < 1000);

  return (
    <AccountPage
      title="Лайтстоуни й кристали"
      subtitle="Комбінації лайтстоунів і обмеження кристалів з твого клієнта гри. Камені, що в тебе вже є, рахуються зі складів та інвентаря; посилені рахуються як звичайні."
      onRecords={reload}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      <section className="inventory-summary">
        <div>
          <span className="muted-label">КОМБІНАЦІЙ</span>
          <strong>{data ? combos.length : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">МОЖНА ЗІБРАТИ ВЖЕ</span>
          <strong className="grind-ok">{data ? combos.filter((c) => c.ready).length : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">ГРУП КРИСТАЛІВ З ЛІМІТОМ</span>
          <strong>{data ? crystals.length : "—"}</strong>
        </div>
      </section>

      <section className="panel account-group">
        <div className="eyebrow">КОМБІНАЦІЇ ЛАЙТСТОУНІВ</div>
        <div className="grind-filters">
          <input type="search" placeholder="Назва, ефект чи камінь…" value={query} onChange={(e) => setQuery(e.target.value)}
            aria-label="Пошук комбінації" />
          <label>
            <input type="checkbox" checked={onlyReady} onChange={(e) => setOnlyReady(e.target.checked)} />
            Лише ті, що можна зібрати
          </label>
        </div>
        <ul className="recipe-list">
          {shown.map((combo) => (
            <li key={combo.combo_id} className={combo.ready ? "build-ready" : undefined}>
              <div className="recipe-head">
                <div className="recipe-title">
                  <strong>{combo.name}</strong>
                  {combo.description && (
                    <small className="build-effects">{combo.description.split("\n").slice(1).join(" · ")}</small>
                  )}
                </div>
                <div className="recipe-money">
                  <strong className={combo.ready ? "grind-ok" : undefined}>{combo.owned} / {combo.total}</strong>
                  <small>{combo.ready ? "можна зібрати" : "каменів є"}</small>
                </div>
              </div>
              <ul className="chip-list gear-notes">
                {combo.stones.map((stone) => (
                  <li key={stone.item_id} className={stone.have >= stone.count ? "gear-have" : undefined}>
                    {stone.name}{stone.count > 1 ? ` ×${stone.count}` : ""} <small>(є {stone.have})</small>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel account-group">
        <div className="eyebrow">КРИСТАЛИ: СКІЛЬКИ ОДНІЄЇ ГРУПИ МОЖНА ВСТАВИТИ</div>
        <ul className="chip-list build-crystals">
          {crystals.map((group) => (
            <li key={group.group_id}>
              {group.name} <b>×{group.max}</b>
            </li>
          ))}
        </ul>
        <p className="inventory-muted">
          Сети спорядження в даних клієнта є лише номерами навичок без назв і переліку предметів, тож їх тут немає.
        </p>
      </section>
    </AccountPage>
  );
}
