"use client";

import Link from "next/link";

import { AgentBar, useApiData } from "./_components/AccountPage";
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
): Attention[] {
  const items: Attention[] = [];

  const tired = workers.filter((worker) => worker.stamina === 0);
  if (tired.length > 0) {
    const towns = [...new Set(tired.map((worker) => worker.town_name))].join(", ");
    items.push({
      key: "workers",
      title: `${tired.length} робітн. без витривалості`,
      detail: `Нагодуй їх, щоб відновити роботу: ${towns}.`,
      href: "/workers",
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
      href: "/transport",
    });
  }

  for (const character of characters) {
    if (character.xp_percent !== null && character.xp_percent >= NEAR_LEVEL_UP) {
      items.push({
        key: `level-${character.character_id}`,
        title: `${character.nick} близько до Lv. ${(character.level ?? 0) + 1}`,
        detail: `Досвід ${character.xp_percent.toFixed(1)}% — трохи гринду до нового рівня.`,
        href: "/characters",
      });
    }
  }

  if (snapshots !== null && snapshots.length === 0) {
    items.push({
      key: "inventory",
      title: "Знімків інвентаря ще немає",
      detail: "Увімкни агента й зайди персонажем у світ — інвентар і склади знімуться самі.",
      href: "/inventory",
    });
  } else if (account && (!account.prices_fetched_at || account.unpriced_stacks > account.priced_stacks)) {
    items.push({
      key: "prices",
      title: account.prices_fetched_at ? "Більшість предметів без ціни" : "Ціни ринку не завантажені",
      detail: "Без них вартість акаунта неповна. Онови ціни на сторінці ресурсів.",
      href: "/inventory",
    });
  }

  return items;
}

export default function Home() {
  const family = useApiData<Family>("/api/family");
  const characters = useApiData<Character[]>("/api/characters");
  const account = useApiData<Account>("/api/account");
  const workers = useApiData<Worker[]>("/api/workers");
  const servants = useApiData<Servants>("/api/servants");
  const knowledge = useApiData<Knowledge>("/api/knowledge");
  const snapshots = useApiData<Snapshot[]>("/api/snapshots");

  function reloadAll() {
    for (const source of [family, characters, account, workers, servants, knowledge, snapshots]) source.reload();
  }

  const list = characters.data ?? [];
  const top = list.reduce<Character | null>(
    (best, character) => ((character.level ?? 0) > (best?.level ?? -1) ? character : best),
    null,
  );
  const fame = family.data?.fame;
  const attention = attentionItems(list, workers.data ?? [], servants.data?.servants ?? [], snapshots.data,
    account.data);
  const error = [family, characters, account, workers, servants, knowledge, snapshots].find((s) => s.error)?.error;
  const hasData = list.length > 0;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">B</div>
          <div>
            <strong>BDO COMPANION</strong>
            <span>PERSONAL ADVENTURE</span>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>
        <div className="nav-item active">◈ <span>Огляд</span></div>
        <Link href="/characters" className="nav-item">⚔ <span>Мої персонажі</span></Link>
        <Link href="/inventory" className="nav-item">◉ <span>Мої ресурси</span></Link>
        <Link href="/workers" className="nav-item">⚒ <span>Робітники</span></Link>
        <Link href="/transport" className="nav-item">⚓ <span>Транспорт</span></Link>
        <Link href="/knowledge" className="nav-item">✦ <span>Знання</span></Link>
        <Link href="/game-data" className="nav-item">⚙ <span>Дані гри</span></Link>

        <div className="sidebar-bottom">
          <div className="connection-dot" />
          <div>
            <strong>Локальний режим</strong>
            <span>Дані з трафіку гри</span>
          </div>
        </div>
      </aside>

      <section className="main-content">
        <header className="topbar">
          <div>
            <div className="eyebrow">BLACK DESERT ONLINE / EU</div>
            <h1>{family.data?.name ?? "Твоя пригода"}<span className="gold">.</span></h1>
          </div>
        </header>

        <AgentBar onRecords={reloadAll} />

        {error && <p className="inventory-feedback error">{error}. Перевір, що API запущено.</p>}

        <section className="welcome-panel">
          <div className="welcome-copy">
            <div className="eyebrow gold-text">СІМ&apos;Я{family.data?.name ? ` ${family.data.name.toUpperCase()}` : ""}</div>
            {hasData ? (
              <h2>
                {list.length} персонаж{list.length === 1 ? "" : "ів"}
                <br />
                слава {fame ? fame.total.toLocaleString("uk-UA") : "—"}
              </h2>
            ) : (
              <h2>Зайди в гру<br />з увімкненим агентом.</h2>
            )}
            <p>
              {hasData && family.data
                ? `Дані оновлено ${formatSeen(family.data.updated_at)}. Усе приходить з трафіку гри при вході персонажем у світ.`
                : "Агент пасивно читає трафік гри: персонажі, робітники, транспорт, знання, інвентар і склади з'являться тут самі."}
            </p>
            <Link className="primary-button" href="/characters">
              Мої персонажі <span>→</span>
            </Link>
          </div>
          <div className="hero-emblem" aria-hidden="true">
            <div className="emblem-ring">
              <div className="emblem-inner">B</div>
            </div>
            <span>ADVENTURER</span>
          </div>
          <div className="welcome-decoration">BLACK DESERT</div>
        </section>

        <div className="section-heading">
          <div>
            <div className="eyebrow">ACCOUNT OVERVIEW</div>
            <h2>Акаунт</h2>
          </div>
        </div>

        <section className="stats-grid">
          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-icon">✧</span>
              <span className="muted-label">СЛАВА СІМ&apos;Ї</span>
            </div>
            <div className="stat-value">{fame ? fame.total.toLocaleString("uk-UA") : "—"}</div>
            <div className="stat-caption">
              {fame ? `Бій ${fame.combat} · Життя ${fame.life} · Інша ${fame.third}` : "Після входу персонажем"}
            </div>
          </div>

          <div className="stat-card character-card">
            <div className="stat-top">
              <span className="stat-icon">⚔</span>
              <span className="muted-label">НАЙВИЩИЙ РІВЕНЬ</span>
            </div>
            <div className="stat-value">{top ? `Lv. ${top.level ?? "—"}` : "—"}</div>
            <div className="stat-caption">{top ? `${top.nick} · ${top.class_name ?? "клас невідомий"}` : "Немає персонажів"}</div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-icon">◈</span>
              <span className="muted-label">ВАРТІСТЬ АКАУНТА</span>
            </div>
            <div className="stat-value">
              {account.data?.prices_fetched_at ? formatSilver(account.data.total_value) : "—"}
            </div>
            <div className="stat-caption">
              {account.data ? `Срібло ${formatSilver(account.data.silver)}` : "Після знімка інвентаря"}
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-icon">✦</span>
              <span className="muted-label">ЗНАННЯ</span>
            </div>
            <div className="stat-value">{knowledge.data?.total ? knowledge.data.total.toLocaleString("uk-UA") : "—"}</div>
            <div className="stat-caption">
              {knowledge.data?.ecology_points != null ? `Очки екології ${knowledge.data.ecology_points}` : "Після входу персонажем"}
            </div>
          </div>
        </section>

        <div className="content-grid">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">NEEDS ATTENTION</div>
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
                    <span className="task-arrow">→</span>
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">CHARACTERS</div>
                <h2>Персонажі</h2>
              </div>
              <Link className="text-button" href="/characters">Усі →</Link>
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

        <footer>
          <span>BDO COMPANION <span className="gold">/</span> PERSONAL PROJECT</span>
          <span>Неофіційний фан-проєкт · Не пов’язаний із Pearl Abyss</span>
        </footer>
      </section>
    </main>
  );
}
