"use client";

import Link from "next/link";
import { useState } from "react";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { GameImage } from "../_components/GameImage";
import { fetchJson, formatSilver } from "../_lib/api";

type Input = { item_id: number; name: string; count: number; have: number };

type Recipe = {
  recipe_id: string;
  output_id: number;
  output: string;
  type: string;
  type_label: string;
  station: string | null;
  inputs: Input[];
  times: number;
  best_place: string | null;
  best_times: number;
  unit_price: number | null;
  value: number | null;
  cost: number | null;
  profit: number | null;
};

type Recipes = { recipes: Recipe[]; known: number; holdings: boolean };

const PAGE = 60;

function silver(value: number) {
  return value < 0 ? `−${formatSilver(-value)}` : formatSilver(value);
}

export default function CraftingPage() {
  const { data, error, reload } = useApiData<Recipes>("/api/recipes");
  const [type, setType] = useState("");
  const [query, setQuery] = useState("");
  const [onePlace, setOnePlace] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refreshPrices() {
    setBusy(true);
    setMessage("Оновлюю ціни з ринку. Перший раз це може тривати до хвилини…");
    try {
      const result = await fetchJson<{ requested: number }>("/api/prices/refresh", { method: "POST" });
      setMessage(`Ціни оновлено для ${result.requested} предметів.`);
      reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не вдалося оновити ціни.");
    } finally {
      setBusy(false);
    }
  }

  const recipes = data?.recipes ?? [];
  const types = [...new Map(recipes.map((r) => [r.type, r.type_label])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const text = query.trim().toLowerCase();
  const filtered = recipes.filter(
    (r) =>
      (!type || r.type === type) &&
      (!onePlace || r.best_times > 0) &&
      (!text || r.output.toLowerCase().includes(text) || r.inputs.some((i) => i.name.toLowerCase().includes(text))),
  );

  return (
    <AccountPage
      title="Що зготувати"
      subtitle="Рецепти з твого клієнта гри, для яких вистачає інгредієнтів у інвентарі й на складах з останнього знімка агента. Ціни — Central Market EU (arsha.io), до податку."
      onRecords={reload}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {data && !data.holdings ? (
        <EmptyState title="Знімків інвентаря ще немає">
          Увімкни агента й зайди персонажем у світ — інвентар і склади знімуться самі.
        </EmptyState>
      ) : data && data.known === 0 ? (
        <EmptyState title="Рецептів ще немає">
          Імпортуй вивід bdo-data-extractor на сторінці <Link className="text-link" href="/game-data/">«Дані гри»</Link>.
        </EmptyState>
      ) : (
        <>
          <div className="price-status">
            <span>
              {data ? `${recipes.length} рецептів можна зробити з того, що є` : "Завантаження…"}
              {data && `, з них з вигодою відомою — ${recipes.filter((r) => r.profit !== null).length}.`}
            </span>
            <button className="outline-button" type="button" onClick={() => void refreshPrices()} disabled={busy}>
              ↻ Оновити ціни
            </button>
          </div>
          {message && <p className="inventory-feedback">{message}</p>}

          <section className="panel account-group">
            <div className="grind-filters">
              <select value={type} onChange={(e) => { setType(e.target.value); setLimit(PAGE); }} aria-label="Тип">
                <option value="">Усі типи</option>
                {types.map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
              <input
                type="search"
                placeholder="Результат чи інгредієнт…"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }}
                aria-label="Пошук рецепта"
              />
              <label>
                <input type="checkbox" checked={onePlace} onChange={(e) => setOnePlace(e.target.checked)} />
                Усе вже в одному місці
              </label>
            </div>

            <ul className="recipe-list">
              {filtered.slice(0, limit).map((recipe) => (
                <li key={recipe.recipe_id}>
                  <div className="recipe-head">
                    <div className="inventory-item-icon">
                      <GameImage kind="item" id={recipe.output_id} size={42} fallback="◇" />
                    </div>
                    <div className="recipe-title">
                      <strong>{recipe.output}</strong>
                      <small>
                        {recipe.type_label}
                        {recipe.station ? ` · ${recipe.station}` : ""} · до ×{recipe.times.toLocaleString("uk-UA")}
                      </small>
                    </div>
                    <div className="recipe-money">
                      {recipe.profit !== null ? (
                        <strong className={recipe.profit >= 0 ? "grind-ok" : "warn"}>{silver(recipe.profit)}</strong>
                      ) : recipe.value !== null ? (
                        <strong>{formatSilver(recipe.value)}</strong>
                      ) : (
                        <span className="inventory-muted">ціни немає</span>
                      )}
                      <small>{recipe.profit !== null ? "вигода за все" : recipe.value !== null ? "результат за все" : ""}</small>
                    </div>
                  </div>
                  <p className="recipe-place">
                    {recipe.best_times > 0
                      ? recipe.best_times >= recipe.times
                        ? `Усе є в: ${recipe.best_place}`
                        : `У ${recipe.best_place} вистачає на ×${recipe.best_times}; решту треба перенести з інших складів`
                      : "Інгредієнти на різних складах — спершу перенеси їх в одне місце"}
                  </p>
                  <ul className="chip-list">
                    {recipe.inputs.map((input) => (
                      <li key={input.item_id}>
                        {input.name} ×{input.count} <small>(є {input.have.toLocaleString("uk-UA")})</small>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
            {filtered.length > limit && (
              <button className="outline-button recipe-more" type="button" onClick={() => setLimit(limit + PAGE)}>
                Показати ще ({filtered.length - limit})
              </button>
            )}
            <p className="inventory-muted">
              У даних клієнта рецепт містить лише основні інгредієнти: замінники, які приймає гра (наприклад, будь-яке
              зерно замість пшениці), не враховано — тож можливих рецептів буває більше.
            </p>
          </section>
        </>
      )}
    </AccountPage>
  );
}
