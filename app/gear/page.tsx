"use client";

import Link from "next/link";
import { useState } from "react";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { GameImage } from "../_components/GameImage";

type LevelView = { level: number; name: string; ap: number | null; dp: number | null };

type CaphrasStep = { level: number; stones: number; total: number; stats: Record<string, number> };

type GearItem = {
  item_id: number;
  name: string;
  category: string | null;
  place: string;
  enhancement: number;
  max_level: number;
  current: LevelView | null;
  next: LevelView | null;
  gain: Record<string, number> | null;
  chance: number | null;
  aids: { item_id: number; name: string; have: number }[];
  caphras: { steps: CaphrasStep[]; stones: number } | null;
  reforms: { item_id: number; name: string }[];
};

const CATEGORY_LABELS: Record<string, string> = {
  MainWeapon: "Основна зброя",
  SubWeapon: "Додаткова зброя",
  AwakenWeapon: "Пробуджена зброя",
  Armor: "Броня",
  Accessory: "Аксесуари",
  Vehicle: "Спорядження транспорту",
  PearlGoods: "Перлові речі",
  Etc: "Інше",
};

const STAT_LABELS: Record<string, string> = {
  ap: "AP", dp: "DP", accuracy: "влучність", evasion: "ухилення", hiddenEvasion: "прих. ухилення",
  damageReduction: "зниж. шкоди", hiddenDamageReduction: "прих. зниж. шкоди", maxHp: "HP", maxMp: "MP",
};

function stats(values: Record<string, number>) {
  return Object.entries(values).map(([k, v]) => `${STAT_LABELS[k] ?? k} +${v}`).join(", ");
}

function percent(chance: number) {
  const value = chance * 100;
  return `${value >= 10 ? value.toFixed(0) : value >= 1 ? value.toFixed(1) : value.toFixed(2)}%`;
}

function Caphras({ caphras }: { caphras: NonNullable<GearItem["caphras"]> }) {
  const last = caphras.steps[caphras.steps.length - 1];
  const reachable = caphras.steps.filter((s) => s.total <= caphras.stones).at(-1);
  return (
    <details className="gear-caphras">
      <summary>
        Caphras на цьому рівні: до {last.level} кроку — {last.total.toLocaleString("uk-UA")} каменів (у тебе{" "}
        {caphras.stones.toLocaleString("uk-UA")}
        {reachable ? `, вистачає до кроку ${reachable.level}` : ""})
      </summary>
      <div className="table-scroll">
        <table className="account-table">
          <thead>
            <tr><th>Крок</th><th>Каменів</th><th>Усього</th><th>Разом дає</th></tr>
          </thead>
          <tbody>
            {caphras.steps.map((step) => (
              <tr key={step.level} className={step.total <= caphras.stones ? "gear-reachable" : undefined}>
                <td>{step.level}</td>
                <td>{step.stones.toLocaleString("uk-UA")}</td>
                <td>{step.total.toLocaleString("uk-UA")}</td>
                <td>{stats(step.stats)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="inventory-muted">Поточний рівень Caphras предмета сервер не надсилає — рахуй від свого.</p>
    </details>
  );
}

export default function GearPage() {
  const { data, error, reload } = useApiData<{ items: GearItem[] }>("/api/gear-plan");
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [onlyEnhanced, setOnlyEnhanced] = useState(true);
  const items = data?.items ?? [];
  const categories = [...new Set(items.map((i) => i.category).filter((c): c is string => Boolean(c)))];
  const text = query.trim().toLowerCase();
  const shown = items.filter(
    (i) => (!category || i.category === category) && (!onlyEnhanced || i.enhancement > 0) &&
      (!text || i.name.toLowerCase().includes(text)),
  );

  return (
    <AccountPage
      title="Спорядження"
      subtitle="Заточування, Caphras і реформа для предметів з твоїх складів, інвентаря й транспорту. Рівні, базові шанси й камені — з твого клієнта гри."
      onRecords={reload}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {data !== null && items.length === 0 ? (
        <EmptyState title="Спорядження ще немає">
          Потрібні знімок інвентаря (увімкни агента й зайди у світ) і дані гри з{" "}
          <Link className="text-link" href="/game-data/">«Дані гри»</Link>.
        </EmptyState>
      ) : (
        <section className="panel account-group">
          <div className="grind-filters">
            <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Тип спорядження">
              <option value="">Усе спорядження</option>
              {categories.map((c) => (
                <option key={c} value={c}>{CATEGORY_LABELS[c] ?? c}</option>
              ))}
            </select>
            <input type="search" placeholder="Назва предмета…" value={query} onChange={(e) => setQuery(e.target.value)}
              aria-label="Пошук предмета" />
            <label>
              <input type="checkbox" checked={onlyEnhanced} onChange={(e) => setOnlyEnhanced(e.target.checked)} />
              Лише заточене
            </label>
          </div>

          <ul className="recipe-list">
            {shown.map((item, index) => (
              <li key={`${item.item_id}-${item.enhancement}-${item.place}-${index}`}>
                <div className="recipe-head">
                  <div className={`inventory-item-icon ${item.enhancement > 0 ? "enhanced" : ""}`}>
                    <GameImage kind="item" id={item.item_id} size={42} fallback={item.enhancement > 0 ? null : "◇"} />
                    {item.enhancement > 0 && <span className="item-enhancement">+{item.enhancement}</span>}
                  </div>
                  <div className="recipe-title">
                    <strong>{item.current && item.enhancement > 0 ? `${item.current.name} ${item.name}` : item.name}</strong>
                    <small>{CATEGORY_LABELS[item.category ?? ""] ?? item.category ?? "—"} · {item.place}</small>
                  </div>
                  <div className="recipe-money">
                    {item.next ? (
                      <>
                        <strong>→ {item.next.name}</strong>
                        <small>
                          {item.chance !== null ? `базовий шанс ${percent(item.chance)}` : ""}
                          {item.gain && Object.keys(item.gain).length > 0 ? ` · ${stats(item.gain)}` : ""}
                        </small>
                      </>
                    ) : (
                      <span className="grind-ok">максимум</span>
                    )}
                  </div>
                </div>
                {(item.aids.length > 0 || item.reforms.length > 0) && (
                  <ul className="chip-list gear-notes">
                    {item.aids.map((aid) => (
                      <li key={aid.item_id} className={aid.have > 0 ? "gear-have" : undefined}>
                        можна використати: {aid.name} {aid.have > 0 ? `(є ${aid.have})` : "(немає)"}
                      </li>
                    ))}
                    {item.reforms.map((reform) => (
                      <li key={reform.item_id}>реформа → {reform.name}</li>
                    ))}
                  </ul>
                )}
                {item.caphras && <Caphras caphras={item.caphras} />}
              </li>
            ))}
          </ul>
          <p className="inventory-muted">
            Шанс — базовий, без накопичених невдач (failstack): його сервер не надсилає. Рівень заточування спорядження
            транспорту в трафіку не приходить, тож воно рахується як +0.
          </p>
        </section>
      )}
    </AccountPage>
  );
}
