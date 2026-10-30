"use client";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { GameImage } from "../_components/GameImage";
import { formatSeen } from "../_lib/api";

type WornItem = {
  slot: number;
  slot_name: string;
  item_id: number;
  name: string | null;
  grade: number | null;
  enhancement: number;
  durability: number | null;
  max_durability: number | null;
};

// Назви слотів з bdo_toolkit англійською; невідомі приходять як "slot#21".
const SLOT_LABELS: Record<string, string> = {
  "main weapon": "Основна зброя", "sub-weapon": "Додаткова зброя", "awakening weapon": "Зброя пробудження",
  armor: "Броня", gloves: "Рукавиці", shoes: "Чоботи", helmet: "Шолом",
  necklace: "Намисто", ring: "Перстень", earring: "Сережка", belt: "Пояс",
  "alchemy stone": "Алхімічний камінь", tome: "Том", artifact: "Артефакт",
  "lumbering axe": "Сокира", "fluid collector": "Збирач рідини", hoe: "Мотика", "butcher knife": "Ніж м'ясника",
  "tanning knife": "Ніж для шкур", pickaxe: "Кирка",
};

const GRADES = ["PRI", "DUO", "TRI", "TET", "PEN"];
const ACCESSORY_SLOTS = new Set(["necklace", "ring", "earring", "belt"]);
const WEAPON_ARMOR_SLOTS = new Set([
  "main weapon", "sub-weapon", "awakening weapon", "armor", "gloves", "shoes", "helmet",
]);

// Аксесуари рахують PRI–PEN як 1–5, бойова зброя й броня — як 16–20; решта — просто +N.
function enhancementLabel(item: WornItem) {
  const level = item.enhancement;
  if (level <= 0) return "";
  if (ACCESSORY_SLOTS.has(item.slot_name) && level <= 5) return GRADES[level - 1];
  if (WEAPON_ARMOR_SLOTS.has(item.slot_name) && level >= 16 && level <= 20) return GRADES[level - 16];
  return `+${level}`;
}

function slotLabel(slotName: string) {
  if (slotName.startsWith("slot#")) return "Інший слот";
  const costume = slotName.startsWith("costume ");
  const base = costume ? slotName.slice("costume ".length) : slotName;
  const label = SLOT_LABELS[base] ?? base;
  return costume ? `Костюм: ${label.toLowerCase()}` : label;
}

function GearList({ gear }: { gear: WornItem[] }) {
  return (
    <ul className="account-gear">
      {gear.map((item) => (
        <li key={item.slot}>
          <GameImage kind="item" id={item.item_id} size={32} className="account-gear-icon" />
          <div>
            <strong>
              {enhancementLabel(item) && `${enhancementLabel(item)} `}
              {item.name ?? `Предмет #${item.item_id}`}
            </strong>
            <span>{slotLabel(item.slot_name)}</span>
          </div>
          {item.max_durability !== null && item.durability !== null ? (
            <span className={item.durability < item.max_durability * 0.5 ? "warn" : undefined}>
              {item.durability}/{item.max_durability}
            </span>
          ) : (
            <span className="inventory-muted">∞</span>
          )}
        </li>
      ))}
    </ul>
  );
}

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
  skill_points: number | null;
  skill_points_total: number | null;
  gear: WornItem[];
  last_seen: number;
};

type Family = {
  name: string | null;
  fame: { combat: number; life: number; third: number; total: number };
  contribution: { available: number; total: number } | null;
  life_gear: WornItem[];
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
      title="Персонажі"
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
            {family.data!.contribution && (
              <div>
                <dt>Очки внеску</dt>
                <dd>{family.data!.contribution.available} / {family.data!.contribution.total}</dd>
              </div>
            )}
          </dl>
          {family.data!.life_gear.length > 0 && (
            <details className="holdings-group">
              <summary>
                <strong>Життєве спорядження</strong>
                <span>{family.data!.life_gear.length} поз. · спільне для сім&apos;ї</span>
              </summary>
              <GearList gear={family.data!.life_gear} />
            </details>
          )}
        </section>
      )}

      {characters.data === null && !error ? (
        <p className="inventory-muted">Завантаження...</p>
      ) : list.length === 0 ? (
        <EmptyState title="Персонажів ще немає">Увімкни агента й зайди персонажем у світ.</EmptyState>
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
              {character.skill_points !== null && character.skill_points_total !== null && (
                <p className="inventory-muted">
                  Очки навичок {character.skill_points.toLocaleString("uk-UA")} / {character.skill_points_total.toLocaleString("uk-UA")}
                </p>
              )}
              {character.gear.length > 0 && (
                <details className="holdings-group">
                  <summary>
                    <strong>Спорядження</strong>
                    <span>{character.gear.length} поз.</span>
                  </summary>
                  <GearList gear={character.gear} />
                </details>
              )}
              <p className="account-seen">Оновлено {formatSeen(character.last_seen)}</p>
            </article>
          ))}
        </section>
      )}
    </AccountPage>
  );
}
