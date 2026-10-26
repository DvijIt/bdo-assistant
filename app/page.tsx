"use client";

import { useState, useEffect } from "react";

type Task = {
  id: number;
  title: string;
  detail: string;
  reward: string;
  done: boolean;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [character, setCharacter] = useState("Мій персонаж");
  const [characterClass, setCharacterClass] = useState("Woosa");
  const [ap, setAp] = useState(280);
  const [dp, setDp] = useState(350);
  const [silver, setSilver] = useState("12.5");
  const [goal, setGoal] = useState("gear");
  const [editing, setEditing] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([
    {
      id: 1,
      title: "Перевірити спорядження",
      detail: "Уточни поточні предмети та рівень їх посилення",
      reward: "План прогресу",
      done: false,
    },
    {
      id: 2,
      title: "Визначити наступну ціль",
      detail: "Обери предмет або характеристику для покращення",
      reward: "Чіткий пріоритет",
      done: false,
    },
    {
      id: 3,
      title: "Підготувати ресурси",
      detail: "Перевір срібло й потрібні матеріали",
      reward: "Готовність до прогресу",
      done: false,
    },
  ]);
  const [apiStatus, setApiStatus] = useState("Завантаження...");
  const [saving, setSaving] = useState(false);


  useEffect(() => {
    async function loadProfile() {
      try {
        const response = await fetch(`${API}/api/profile`);

        if (!response.ok) {
          throw new Error("Не вдалося завантажити профіль");
        }

        const profile = await response.json();

        setCharacter(profile.character_name);
        setCharacterClass(profile.character_class);
        setAp(profile.ap);
        setDp(profile.dp);
        setSilver(String(profile.silver_billions));
        setGoal(profile.goal);
        setApiStatus("Дані завантажено з бази");
      } catch (error) {
        console.error(error);
        setApiStatus("API недоступний — перевір сервер");
      }
    }

    loadProfile();
  }, []);


  const completed = tasks.filter((task) => task.done).length;

  const goalLabels: Record<string, string> = {
    gear: "Покращити спорядження",
    silver: "Заробити срібло",
    pve: "Підготуватися до PvE",
    life: "Розвивати Life Skills",
  };


  async function saveProfile() {
    setSaving(true);
    setApiStatus("Збереження...");

    try {
      const response = await fetch(
        `${API}/api/profile`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            character_name: character,
            character_class: characterClass,
            ap,
            dp,
            silver_billions: Number(silver),
            goal,
          }),
        }
      );

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Помилка збереження");
      }

      const profile = await response.json();

      setCharacter(profile.character_name);
      setCharacterClass(profile.character_class);
      setAp(profile.ap);
      setDp(profile.dp);
      setSilver(String(profile.silver_billions));
      setGoal(profile.goal);
      setEditing(false);
      setApiStatus("Збережено в SQLite ✓");
    } catch (error) {
      console.error(error);
      setApiStatus("Помилка збереження. Перевір API та введені дані.");
    } finally {
      setSaving(false);
    }
  }


  function toggleTask(id: number) {
    setTasks((current) =>
      current.map((task) =>
        task.id === id ? { ...task, done: !task.done } : task
      )
    );
  }

  function addTask() {
    const title = window.prompt("Назва нового завдання?");
    if (!title?.trim()) return;

    setTasks((current) => [
      ...current,
      {
        id: Date.now(),
        title: title.trim(),
        detail: "Твоє персональне завдання",
        reward: "Власна ціль",
        done: false,
      },
    ]);
  }

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
        <div className="nav-item">⚔ <span>Мій персонаж</span></div>
        <div className="nav-item">◇ <span>Спорядження</span></div>
        <div className="nav-item">◉ <span>Мої ресурси</span></div>
        <div className="nav-item">◎ <span>План прогресу</span></div>

        <div className="sidebar-bottom">
          <div className="connection-dot" />
          <div>
            <strong>Локальний режим</strong>
            <span>Демонстраційні дані</span>
          </div>
        </div>
      </aside>

      <section className="main-content">
        <header className="topbar">
          <div>
            <div className="eyebrow">BLACK DESERT ONLINE / EU</div>
            <div className="api-status">{apiStatus}</div>
            <h1>Твоя пригода<span className="gold">.</span></h1>
          </div>
          <button
            className="outline-button"
            disabled={saving}
            onClick={() => {
              if (editing) {
                void saveProfile();
              } else {
                setEditing(true);
              }
            }}
          >
            {saving
              ? "Збереження..."
              : editing
                ? "✓ Зберегти"
                : "✎ Редагувати профіль"}
          </button>
        </header>

        <section className="welcome-panel">
          <div className="welcome-copy">
            <div className="eyebrow gold-text">ТВІЙ ПЕРСОНАЛЬНИЙ АСИСТЕНТ</div>
            <h2>Кожен крок має<br />наближати до цілі.</h2>
            <p>
              Відстежуй прогрес, плануй покращення та визначай,
              на чому варто зосередитися далі.
            </p>
            <button
              className="primary-button"
              onClick={() =>
                document.getElementById("next-steps")?.scrollIntoView({
                  behavior: "smooth",
                })
              }
            >
              Переглянути план <span>→</span>
            </button>
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
            <div className="eyebrow">CHARACTER OVERVIEW</div>
            <h2>Твій персонаж</h2>
          </div>
          <span className="demo-badge">DEMO DATA</span>
        </div>

        <section className="stats-grid">
          <div className="stat-card character-card">
            <div className="stat-top">
              <span className="stat-icon">♙</span>
              <span className="muted-label">ПЕРСОНАЖ</span>
            </div>
            {editing ? (
              <input
                className="edit-input"
                value={character}
                onChange={(e) => setCharacter(e.target.value)}
                aria-label="Ім'я персонажа"
              />
            ) : (
              <div className="stat-value">{character}</div>
            )}
            {editing ? (
              <input
                className="edit-input"
                value={characterClass}
                onChange={(e) => setCharacterClass(e.target.value)}
                aria-label="Клас персонажа"
              />
            ) : (
              <div className="stat-caption">{characterClass} · Class</div>
            )}
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-icon">⚔</span>
              <span className="muted-label">ATTACK</span>
            </div>
            {editing ? (
              <input
                className="edit-input"
                type="number"
                value={ap}
                onChange={(e) => setAp(Number(e.target.value))}
                aria-label="AP"
              />
            ) : (
              <div className="stat-value">{ap} <small>AP</small></div>
            )}
            <div className="stat-caption">Атака</div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-icon">⬡</span>
              <span className="muted-label">DEFENSE</span>
            </div>
            {editing ? (
              <input
                className="edit-input"
                type="number"
                value={dp}
                onChange={(e) => setDp(Number(e.target.value))}
                aria-label="DP"
              />
            ) : (
              <div className="stat-value">{dp} <small>DP</small></div>
            )}
            <div className="stat-caption">Захист</div>
          </div>

          <div className="stat-card">
            <div className="stat-top">
              <span className="stat-icon">◈</span>
              <span className="muted-label">SILVER</span>
            </div>
            {editing ? (
              <input
                className="edit-input"
                value={silver}
                onChange={(e) => setSilver(e.target.value)}
                aria-label="Срібло в мільярдах"
              />
            ) : (
              <div className="stat-value">{silver} <small>B</small></div>
            )}
            <div className="stat-caption">Срібло, млрд (приклад)</div>
          </div>
        </section>

        <div className="content-grid">
          <section className="panel" id="next-steps">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">YOUR ROADMAP</div>
                <h2>Наступні кроки</h2>
              </div>
              <button className="text-button" onClick={addTask}>+ Додати</button>
            </div>

            <div className="progress-row">
              <span>Виконано завдань</span>
              <strong>{completed} / {tasks.length}</strong>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{
                  width: `${tasks.length ? (completed / tasks.length) * 100 : 0}%`,
                }}
              />
            </div>

            <div className="task-list">
              {tasks.map((task, index) => (
                <button
                  className={`task-item ${task.done ? "task-done" : ""}`}
                  key={task.id}
                  onClick={() => toggleTask(task.id)}
                >
                  <span className="task-number">
                    {task.done ? "✓" : String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="task-copy">
                    <strong>{task.title}</strong>
                    <span>{task.detail}</span>
                    <small>{task.reward}</small>
                  </span>
                  <span className="task-arrow">{task.done ? "↺" : "→"}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="panel goal-panel">
            <div className="eyebrow">PERSONAL SETTINGS</div>
            <h2>Твоя ціль</h2>
            <p className="panel-description">
              Обери напрям, і ми адаптуємо рекомендації під твій стиль гри.
            </p>

            <label className="field-label" htmlFor="goal-select">
              ГОЛОВНИЙ ПРІОРИТЕТ
            </label>
            <select
              id="goal-select"
              className="goal-select"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            >
              <option value="gear">Покращити спорядження</option>
              <option value="silver">Заробити срібло</option>
              <option value="pve">Підготуватися до PvE</option>
              <option value="life">Розвивати Life Skills</option>
            </select>

            <div className="goal-result">
              <div className="goal-icon">✧</div>
              <div>
                <span className="muted-label">АКТИВНА ЦІЛЬ</span>
                <strong>{goalLabels[goal]}</strong>
                <p>
                  {goal === "gear" && "Почнемо з перевірки спорядження та доступних покращень."}
                  {goal === "silver" && "Порівняємо можливі джерела доходу й потрібні витрати."}
                  {goal === "pve" && "Оцінимо характеристики та підберемо напрям розвитку."}
                  {goal === "life" && "Зберемо інформацію про професії, рівні та ресурси."}
                </p>
              </div>
            </div>

            <div className="notice">
              <span>ⓘ</span>
              <p>
                Це початковий прототип. Рекомендації поки не використовують
                реальні дані твого акаунта.
              </p>
            </div>
          </section>
        </div>

        <footer>
          <span>BDO COMPANION <span className="gold">/</span> PERSONAL PROJECT</span>
          <span>Неофіційний фан-проєкт · Не пов'язаний із Pearl Abyss</span>
        </footer>
      </section>
    </main>
  );
}