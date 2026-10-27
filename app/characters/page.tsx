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
  fame: { combat: number; life: number; third: number; total: number } | null;
  last_seen: number;
};

export default function CharactersPage() {
  const { data, error, reload } = useApiData<Character[]>("/api/characters");
  const characters = data ?? [];

  return (
    <AccountPage
      active="/characters/"
      title="Мої персонажі"
      subtitle="Персонаж з'являється тут після входу ним у світ, поки агент увімкнено: клас, рівень, досвід і слава приходять з трафіку гри."
      onRecords={reload}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {data === null && !error ? (
        <p className="inventory-muted">Завантаження...</p>
      ) : characters.length === 0 ? (
        <div className="inventory-empty panel">
          <span>◇</span>
          <strong>Персонажів ще немає</strong>
          <p>Увімкни агента й зайди персонажем у світ.</p>
        </div>
      ) : (
        <section className="account-cards">
          {characters.map((character) => (
            <article className="panel account-card" key={character.character_id}>
              <div className="eyebrow">{character.family ? `${character.family.toUpperCase()} · ` : ""}{character.class_name ?? "КЛАС НЕВІДОМИЙ"}</div>
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
              {character.fame && (
                <dl className="account-facts">
                  <div><dt>Слава</dt><dd>{character.fame.total.toLocaleString("uk-UA")}</dd></div>
                  <div><dt>Бій</dt><dd>{character.fame.combat.toLocaleString("uk-UA")}</dd></div>
                  <div><dt>Життя</dt><dd>{character.fame.life.toLocaleString("uk-UA")}</dd></div>
                  <div><dt>Інша</dt><dd>{character.fame.third.toLocaleString("uk-UA")}</dd></div>
                </dl>
              )}
              <p className="account-seen">Оновлено {formatSeen(character.last_seen)}</p>
            </article>
          ))}
        </section>
      )}
    </AccountPage>
  );
}
