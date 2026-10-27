"use client";

import { AccountPage, useApiData } from "../_components/AccountPage";
import { formatSeen } from "../_lib/api";

type Character = {
  character_id: string;
  nick: string;
  family: string | null;
  class_id: number | null;
  class_name: string | null;
  level: number | null;
  xp: number | null;
  xp_to_next: number | null;
  xp_percent: number | null;
  last_seen: number;
};

type Family = {
  name: string | null;
  fame: { combat: number; life: number; third: number; total: number };
  updated_at: number;
} | null;

export default function CharactersPage() {
  const characters = useApiData<Character[]>("/api/characters");
  const family = useApiData<Family>("/api/family");
  const list = characters.data ?? [];
  const fame = family.data?.fame;
  const error = characters.error || family.error;

  return (
    <AccountPage
      active="/characters/"
      title="Мої персонажі"
      subtitle="Персонаж з'являється тут після входу ним у світ, поки агент увімкнено: клас, рівень і досвід приходять з трафіку гри. Слава — спільна для сім'ї."
      onRecords={() => {
        characters.reload();
        family.reload();
      }}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {fame && (
        <section className="panel account-group">
          <div className="inventory-list-heading">
            <div>
              <div className="eyebrow">СІМ&apos;Я · ОНОВЛЕНО {formatSeen(family.data!.updated_at)}</div>
              <h2>{family.data!.name ?? "Сім'я"}</h2>
            </div>
          </div>
          <dl className="account-facts account-facts-wide">
            <div><dt>Слава</dt><dd>{fame.total.toLocaleString("uk-UA")}</dd></div>
            <div><dt>Бій</dt><dd>{fame.combat.toLocaleString("uk-UA")}</dd></div>
            <div><dt>Життя</dt><dd>{fame.life.toLocaleString("uk-UA")}</dd></div>
            <div><dt>Інша</dt><dd>{fame.third.toLocaleString("uk-UA")}</dd></div>
          </dl>
        </section>
      )}

      {characters.data === null && !error ? (
        <p className="inventory-muted">Завантаження...</p>
      ) : list.length === 0 ? (
        <div className="inventory-empty panel">
          <span>◇</span>
          <strong>Персонажів ще немає</strong>
          <p>Увімкни агента й зайди персонажем у світ.</p>
        </div>
      ) : (
        <section className="account-cards account-group">
          {list.map((character) => (
            <article className="panel account-card" key={character.character_id}>
              <div className="eyebrow">{character.class_name ?? "КЛАС НЕВІДОМИЙ"}</div>
              <h2>{character.nick}</h2>
              <div className="account-card-level">
                <strong>Lv. {character.level ?? "—"}</strong>
                {character.xp_percent !== null && <span>{character.xp_percent.toFixed(3)}%</span>}
              </div>
              {character.xp_percent !== null && (
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${Math.min(character.xp_percent, 100)}%` }} />
                </div>
              )}
              {character.xp !== null && character.xp_to_next !== null && (
                <p className="inventory-muted">
                  XP {character.xp.toLocaleString("uk-UA")} / {character.xp_to_next.toLocaleString("uk-UA")}
                </p>
              )}
              <p className="account-seen">Оновлено {formatSeen(character.last_seen)}</p>
            </article>
          ))}
        </section>
      )}
    </AccountPage>
  );
}
