"use client";

import Link from "next/link";

import { AccountPage, useApiData } from "./_components/AccountPage";
import { formatSeen, formatSilver } from "./_lib/api";

type Family = {
  name: string | null;
  fame: { combat: number; life: number; third: number; total: number };
  updated_at: number;
} | null;

type Character = {
  character_id: string;
  nick: string;
  class_name: string | null;
  level: number | null;
  xp_percent: number | null;
};

type Account = {
  total_value: number;
  silver: number;
  priced_stacks: number;
  unpriced_stacks: number;
  prices_fetched_at: string | null;
};

type Worker = { worker_id: string; stamina: number; town_name: string };

type Servants = {
  servants: {
    name: string;
    gear: { name: string | null; item_id: number; durability: number | null; max_durability: number | null }[];
  }[];
};

type Knowledge = { total: number; ecology_points: number | null };

type Snapshot = { id: number };

type GameData = { imported_at: number } | null;

type Attention = { key: string; title: string; detail: string; href: string };

// Нижче цієї частки міцності спорядження варто полагодити.
const LOW_DURABILITY = 0.5;
// Персонаж близько до наступного рівня.
const NEAR_LEVEL_UP = 90;

function attentionItems(
  characters: Character[],
  workers: Worker[],
  servants: Servants["servants"],
  snapshots: Snapshot[] | null,
  account: Account | null,
  gameData: GameData | undefined,
): Attention[] {
  const items: Attention[] = [];

  const tired = workers.filter((worker) => worker.stamina === 0);
  if (tired.length > 0) {
    const towns = [...new Set(tired.map((worker) => worker.town_name))].join(", ");
    items.push({
      key: "workers",
      title: `${tired.length} робітн. без витривалості`,
      detail: `Нагодуй їх, щоб відновити роботу: ${towns}.`,
      href: "/workers/",
    });
  }

  const worn = servants.flatMap((servant) =>
    servant.gear
      .filter((gear) => gear.max_durability && gear.durability !== null &&
        gear.durability < gear.max_durability * LOW_DURABILITY)
      .map((gear) => `${servant.name}: ${gear.name ?? `#${gear.item_id}`} ${gear.durability}/${gear.max_durability}`),
  );
  if (worn.length > 0) {
    items.push({
      key: "gear",
      title: `${worn.length} предм. спорядження зношено`,
      detail: worn.join(" · "),
      href: "/transport/",
    });
  }

  for (const character of characters) {
    if (character.xp_percent !== null && character.xp_percent >= NEAR_LEVEL_UP) {
      items.push({
        key: `level-${character.character_id}`,
        title: `${character.nick} близько до Lv. ${(character.level ?? 0) + 1}`,
        detail: `Досвід ${character.xp_percent.toFixed(1)}% — трохи гринду до нового рівня.`,
        href: "/characters/",
      });
    }
  }

  if (snapshots !== null && snapshots.length === 0) {
    items.push({
      key: "inventory",
      title: "Знімків інвентаря ще немає",
      detail: "Увімкни агента й зайди персонажем у світ — інвентар і склади знімуться самі.",
      href: "/inventory/",
    });
  } else if (account && (!account.prices_fetched_at || account.unpriced_stacks > account.priced_stacks)) {
    items.push({
      key: "prices",
      title: account.prices_fetched_at ? "Більшість предметів без ціни" : "Ціни ринку не завантажені",
      detail: "Без них вартість акаунта неповна. Онови ціни на сторінці ресурсів.",
      href: "/inventory/",
    });
  }

  if (gameData === null) {
    items.push({
      key: "game-data",
      title: "Назви з клієнта гри не імпортовано",
      detail: "Без них робітники, транспорт і знання показуються номерами. Імпортуй вивід bdo-data-extractor.",
      href: "/game-data/",
    });
  }

  return items;
}

const FIRST_STEPS = [
  { title: "Увімкни агента", detail: "Кнопка вгорі. Агент лише слухає трафік гри, нічого не надсилає." },
  { title: "Зайди персонажем у світ", detail: "Персонажі, робітники, транспорт, знання й склади приходять саме при вході." },
  { title: "Імпортуй дані гри", detail: "Назви, іконки й картинки — з твого клієнта, на сторінці «Дані гри»." },
];

export default function Home() {
  const family = useApiData<Family>("/api/family");
  const characters = useApiData<Character[]>("/api/characters");
  const account = useApiData<Account>("/api/account");
  const workers = useApiData<Worker[]>("/api/workers");
  const servants = useApiData<Servants>("/api/servants");
  const knowledge = useApiData<Knowledge>("/api/knowledge");
  const snapshots = useApiData<Snapshot[]>("/api/snapshots");
  const gameData = useApiData<GameData>("/api/game-data");
  const sources = [family, characters, account, workers, servants, knowledge, snapshots, gameData];

  function reloadAll() {
    for (const source of sources) source.reload();
  }

  const list = characters.data ?? [];
  const top = list.reduce<Character | null>(
    (best, character) => ((character.level ?? 0) > (best?.level ?? -1) ? character : best),
    null,
  );
  const fame = family.data?.fame;
  const attention = attentionItems(list, workers.data ?? [], servants.data?.servants ?? [], snapshots.data,
    account.data, gameData.loaded ? gameData.data : undefined);
  const error = sources.find((s) => s.error)?.error;
  const loaded = characters.data !== null;
  const hasData = list.length > 0;

  return (
    <AccountPage
      title={family.data?.name ? `Сім'я ${family.data.name}` : "Огляд"}
      subtitle={
        hasData && family.data
          ? `Дані оновлено ${formatSeen(family.data.updated_at)}. Усе приходить з трафіку гри при вході персонажем у світ.`
          : "Агент пасивно читає трафік гри: персонажі, робітники, транспорт, знання, інвентар і склади з'являються тут самі."
      }
      onRecords={reloadAll}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {loaded && !hasData && (
        <section className="panel account-group">
          <div className="eyebrow">З ЧОГО ПОЧАТИ</div>
          <ol className="first-steps">
            {FIRST_STEPS.map((step, index) => (
              <li key={step.title}>
                <span className="task-number">{String(index + 1).padStart(2, "0")}</span>
                <span className="task-copy">
                  <strong>{step.title}</strong>
                  <span>{step.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="stats-grid">
        <Link className="stat-card" href="/characters/">
          <div className="stat-top">
            <span className="stat-icon" aria-hidden="true">✧</span>
            <span className="muted-label">СЛАВА СІМ&apos;Ї</span>
          </div>
          <div className="stat-value">{fame ? fame.total.toLocaleString("uk-UA") : "—"}</div>
          <div className="stat-caption">
            {fame ? `Бій ${fame.combat} · Життя ${fame.life} · Інша ${fame.third}` : "Після входу персонажем"}
          </div>
        </Link>

        <Link className="stat-card character-card" href="/characters/">
          <div className="stat-top">
            <span className="stat-icon" aria-hidden="true">⚔</span>
            <span className="muted-label">НАЙВИЩИЙ РІВЕНЬ</span>
          </div>
          <div className="stat-value">{top ? `Lv. ${top.level ?? "—"}` : "—"}</div>
          <div className="stat-caption">{top ? `${top.nick} · ${top.class_name ?? "клас невідомий"}` : "Немає персонажів"}</div>
        </Link>

        <Link className="stat-card" href="/inventory/">
          <div className="stat-top">
            <span className="stat-icon" aria-hidden="true">◈</span>
            <span className="muted-label">ВАРТІСТЬ АКАУНТА</span>
          </div>
          <div className="stat-value">
            {account.data?.prices_fetched_at ? formatSilver(account.data.total_value) : "—"}
          </div>
          <div className="stat-caption">
            {account.data ? `Срібло ${formatSilver(account.data.silver)}` : "Після знімка інвентаря"}
          </div>
        </Link>

        <Link className="stat-card" href="/knowledge/">
          <div className="stat-top">
            <span className="stat-icon" aria-hidden="true">✦</span>
            <span className="muted-label">ЗНАННЯ</span>
          </div>
          <div className="stat-value">{knowledge.data?.total ? knowledge.data.total.toLocaleString("uk-UA") : "—"}</div>
          <div className="stat-caption">
            {knowledge.data?.ecology_points != null ? `Очки екології ${knowledge.data.ecology_points}` : "Після входу персонажем"}
          </div>
        </Link>
      </section>

      <div className="content-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">ЩО ЗРОБИТИ</div>
              <h2>Потребує уваги</h2>
            </div>
          </div>

          {attention.length === 0 ? (
            <p className="panel-description">
              {hasData ? "Усе гаразд: робітники мають витривалість, спорядження ціле." : "Даних ще немає."}
            </p>
          ) : (
            <div className="task-list">
              {attention.map((item, index) => (
                <Link className="task-item" href={item.href} key={item.key}>
                  <span className="task-number">{String(index + 1).padStart(2, "0")}</span>
                  <span className="task-copy">
                    <strong>{item.title}</strong>
                    <span>{item.detail}</span>
                  </span>
                  <span className="task-arrow" aria-hidden="true">→</span>
                </Link>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">ПЕРСОНАЖІ</div>
              <h2>Рівні</h2>
            </div>
            <Link className="text-button" href="/characters/">Усі →</Link>
          </div>

          {list.length === 0 ? (
            <p className="panel-description">Персонажі з&apos;являться після входу ними у світ.</p>
          ) : (
            <ul className="home-characters">
              {list.map((character) => (
                <li key={character.character_id}>
                  <div className="progress-row">
                    <span>
                      <strong>{character.nick}</strong> · {character.class_name ?? "клас невідомий"}
                    </span>
                    <strong>Lv. {character.level ?? "—"}</strong>
                  </div>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${Math.min(character.xp_percent ?? 0, 100)}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </AccountPage>
  );
}
