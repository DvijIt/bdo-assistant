"use client";

import { useState } from "react";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { GameImage } from "../_components/GameImage";
import { fetchJson, formatSilver } from "../_lib/api";

type ContainerKind = "inventory" | "currency" | "storage";

type Holding = {
  item_id: number;
  name: string | null;
  grade: number | null;
  enhancement: number;
  quantity: number;
  unit_price: number | null;
  value: number | null;
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

type ValuedItem = {
  item_id: number;
  name: string | null;
  enhancement: number;
  quantity: number;
  container: string;
  value: number;
};

type Duplicate = {
  item_id: number;
  name: string | null;
  enhancement: number;
  quantity: number;
  value: number | null;
  places: { container: string; quantity: number }[];
};

type Account = {
  total_value: number;
  items_value: number;
  silver: number;
  priced_stacks: number;
  unpriced_stacks: number;
  prices_fetched_at: string | null;
  by_container: { id: number; value: number }[];
  top_items: ValuedItem[];
  duplicates: Duplicate[];
};

type Snapshot = {
  id: number;
  taken_at: string;
  character: string;
  storage_status: string | null;
  stacks: number;
};

const kindLabels: Record<ContainerKind, string> = {
  inventory: "Інвентар",
  currency: "Валюти",
  storage: "Склади міст",
};

function itemLabel(item: { name: string | null; item_id: number; enhancement: number }) {
  const name = item.name ?? `Предмет #${item.item_id}`;
  return item.enhancement > 0 ? `+${item.enhancement} ${name}` : name;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("uk-UA", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function InventoryPage() {
  const holdings = useApiData<Holdings>("/api/holdings");
  const snapshots = useApiData<Snapshot[]>("/api/snapshots");
  const account = useApiData<Account>("/api/account");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  function reloadAll() {
    holdings.reload();
    snapshots.reload();
    account.reload();
  }

  async function run(path: string, pending: string, done: (result: { requested?: number }) => string) {
    setBusy(true);
    setError("");
    setMessage(pending);
    try {
      const result = await fetchJson<{ requested?: number }>(path, { method: "POST" });
      reloadAll();
      setMessage(done(result));
    } catch (err) {
      setMessage("");
      setError(err instanceof Error ? err.message : "Не вдалося оновити.");
    } finally {
      setBusy(false);
    }
  }

  const containers = holdings.data?.containers ?? [];
  const missingNames = holdings.data?.missing_names ?? 0;
  const value = account.data;
  const containerValues = new Map((value?.by_container ?? []).map((container) => [container.id, container.value]));
  const loadError = holdings.error || snapshots.error || account.error;

  return (
    <AccountPage
      title="Ресурси"
      subtitle="Інвентар і склади з останнього знімка агента: для кожного складу показано стан, який він бачив востаннє. Вартість — за базовою ціною Central Market EU (arsha.io), до податку."
      onRecords={reloadAll}
    >
      <section className="inventory-summary">
        <div>
          <span className="muted-label">ВАРТІСТЬ АКАУНТА</span>
          <strong>{value?.prices_fetched_at ? formatSilver(value.total_value) : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">ПРЕДМЕТИ ЗА РИНКОМ</span>
          <strong>{value?.prices_fetched_at ? formatSilver(value.items_value) : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">СРІБЛО В ІНВЕНТАРІ</span>
          <strong>{value ? formatSilver(value.silver) : "—"}</strong>
        </div>
      </section>

      {value && containers.length > 0 && (
        <div className="price-status">
          <span>
            {value.prices_fetched_at
              ? `Ціни: ${formatDate(value.prices_fetched_at)} · з ціною ${value.priced_stacks} стеків, ` +
                `без ціни ${value.unpriced_stacks} (поза ринком або прив’язані)`
              : "Ціни ще не завантажені."}
          </span>
          <span className="account-actions">
            {missingNames > 0 && (
              <button
                className="outline-button"
                type="button"
                onClick={() => void run("/api/items/refresh", "Шукаю назви на arsha.io…", () => "Назви оновлено.")}
                disabled={busy}
              >
                ↻ Дотягнути назви ({missingNames})
              </button>
            )}
            <button
              className="outline-button"
              type="button"
              onClick={() =>
                void run(
                  "/api/prices/refresh",
                  "Оновлюю ціни з ринку. Перший раз це може тривати до хвилини…",
                  (result) => `Ціни оновлено для ${result.requested ?? 0} предметів.`,
                )
              }
              disabled={busy}
            >
              ↻ Оновити ціни
            </button>
          </span>
        </div>
      )}

      {(loadError || error) && <p className="inventory-feedback error">{loadError || error}</p>}
      {message && <p className="inventory-feedback">{message}</p>}

      {holdings.data === null && !loadError ? (
        <p className="inventory-muted">Завантаження…</p>
      ) : containers.length === 0 ? (
        <EmptyState title="Даних ще немає">
          Увімкни агента й зайди персонажем у світ — інвентар і склади знімуться самі.
        </EmptyState>
      ) : (
        <div className="inventory-layout">
          <section className="panel">
            <div className="eyebrow">ПОТОЧНИЙ СТАН</div>
            {(["inventory", "currency", "storage"] as const).map((kind) => {
              // Спільні для сім'ї контейнери спершу, далі — згруповані за персонажем.
              const group = containers
                .filter((container) => container.kind === kind)
                .sort((a, b) => (a.character ?? "").localeCompare(b.character ?? "") || a.name.localeCompare(b.name));
              if (group.length === 0) return null;

              return (
                <div className="holdings-kind" key={kind}>
                  <h2>{kindLabels[kind]}</h2>
                  {group.map((container) => (
                    <details className="holdings-group" key={container.id}>
                      <summary>
                        <strong>
                          {container.name}
                          {kind !== "storage" && ` · ${container.character ?? "сім'я"}`}
                        </strong>
                        <span>
                          {container.items.length} поз.
                          {containerValues.get(container.id) ? ` · ${formatSilver(containerValues.get(container.id)!)}` : ""}
                          {` · ${formatDate(container.observed_at)}`}
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
                              <div className={`inventory-item-icon ${holding.enhancement > 0 ? "enhanced" : ""}`}>
                                <GameImage
                                  kind="item"
                                  id={holding.item_id}
                                  size={42}
                                  fallback={holding.enhancement > 0 ? null : "◇"}
                                />
                                {holding.enhancement > 0 && (
                                  <span className="item-enhancement">+{holding.enhancement}</span>
                                )}
                              </div>
                              <div className="inventory-item-copy">
                                <strong>{holding.name ?? `Предмет #${holding.item_id}`}</strong>
                                <span>
                                  {holding.unit_price ? `${formatSilver(holding.unit_price)} / шт.` : `ID ${holding.item_id}`}
                                </span>
                              </div>
                              <div className="inventory-item-actions">
                                <strong>×{holding.quantity.toLocaleString("uk-UA")}</strong>
                                {holding.value !== null && (
                                  <span className="item-value">{formatSilver(holding.value)}</span>
                                )}
                              </div>
                            </article>
                          ))}
                        </div>
                      )}
                    </details>
                  ))}
                </div>
              );
            })}
          </section>

          <aside className="panel">
            {value && value.top_items.length > 0 && (
              <>
                <div className="eyebrow">НАЙДОРОЖЧІ ПРЕДМЕТИ</div>
                <ul className="snapshot-list">
                  {value.top_items.map((top, index) => (
                    <li key={`${top.item_id}-${top.enhancement}-${index}`}>
                      <strong>{itemLabel(top)} — {formatSilver(top.value)}</strong>
                      <span>{top.container} · ×{top.quantity.toLocaleString("uk-UA")}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            {value && value.duplicates.length > 0 && (
              <>
                <div className="eyebrow snapshot-list-title">ДУБЛІКАТИ МІЖ СКЛАДАМИ</div>
                <ul className="snapshot-list">
                  {value.duplicates.map((duplicate) => (
                    <li key={`${duplicate.item_id}-${duplicate.enhancement}`}>
                      <strong>
                        {itemLabel(duplicate)} — ×{duplicate.quantity.toLocaleString("uk-UA")}
                        {duplicate.value !== null && `, ${formatSilver(duplicate.value)}`}
                      </strong>
                      <span>
                        {duplicate.places
                          .map((place) => `${place.container} ×${place.quantity.toLocaleString("uk-UA")}`)
                          .join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <div className="eyebrow snapshot-list-title">ОСТАННІ ЗНІМКИ</div>
            <ul className="snapshot-list">
              {(snapshots.data ?? []).slice(0, 8).map((snapshot) => (
                <li key={snapshot.id}>
                  <strong>{formatDate(snapshot.taken_at)}</strong>
                  <span>
                    {snapshot.character} · {snapshot.stacks} записів
                    {snapshot.storage_status === "compatible" && " · склади"}
                  </span>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      )}
    </AccountPage>
  );
}
