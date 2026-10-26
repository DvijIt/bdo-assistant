
"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type Category = "gear" | "material" | "consumable" | "other";

type InventoryItem = {
  id: number;
  name: string;
  category: Category;
  quantity: number;
  notes: string;
  created_at: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const categoryLabels: Record<Category, string> = {
  gear: "Спорядження",
  material: "Матеріали",
  consumable: "Витратні предмети",
  other: "Інше",
};

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [name, setName] = useState("");
  const [category, setCategory] = useState<Category>("material");
  const [quantity, setQuantity] = useState("1");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadItems = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API}/api/inventory`);

      if (!response.ok) {
        throw new Error("Не вдалося завантажити інвентар.");
      }

      const data: InventoryItem[] = await response.json();
      setItems(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Помилка з'єднання з API."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");

    const cleanName = name.trim();
    const parsedQuantity = Number(quantity);

    if (!cleanName) {
      setError("Вкажи назву предмета.");
      return;
    }

    if (
      !Number.isInteger(parsedQuantity) ||
      parsedQuantity < 1 ||
      parsedQuantity > 2_000_000_000
    ) {
      setError("Кількість має бути цілим числом від 1 до 2 000 000 000.");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch(`${API}/api/inventory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: cleanName,
          category,
          quantity: parsedQuantity,
          notes: notes.trim(),
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text() || "Не вдалося додати предмет.");
      }

      const created: InventoryItem = await response.json();
      setItems((current) => [created, ...current]);
      setName("");
      setQuantity("1");
      setNotes("");
      setMessage("Предмет збережено в SQLite.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Помилка збереження предмета."
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item: InventoryItem) {
    if (!window.confirm(`Видалити «${item.name}» з інвентаря?`)) {
      return;
    }

    setError("");
    setMessage("");

    try {
      const response = await fetch(`${API}/api/inventory/${item.id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Не вдалося видалити предмет.");
      }

      setItems((current) => current.filter((entry) => entry.id !== item.id));
      setMessage(`«${item.name}» видалено.`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Помилка видалення предмета."
      );
    }
  }

  const totalUnits = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <main className="inventory-page">
      <header className="inventory-header">
        <a href="/" className="inventory-back">← Головна панель</a>
        <div className="eyebrow">BLACK DESERT ONLINE / EU</div>
        <h1>Мій інвентар<span className="gold">.</span></h1>
        <p className="inventory-subtitle">
          Зберігай предмети та ресурси, щоб надалі планувати розвиток персонажа.
        </p>
      </header>

      <section className="inventory-summary">
        <div>
          <span className="muted-label">ЗАПИСІВ У БАЗІ</span>
          <strong>{items.length}</strong>
        </div>
        <div>
          <span className="muted-label">ЗАГАЛЬНА КІЛЬКІСТЬ</span>
          <strong>{totalUnits.toLocaleString("uk-UA")}</strong>
        </div>
        <div>
          <span className="muted-label">СХОВИЩЕ ДАНИХ</span>
          <strong>SQLite</strong>
        </div>
      </section>

      <div className="inventory-layout">
        <section className="panel">
          <div className="eyebrow">NEW ITEM</div>
          <h2>Додати предмет</h2>
          <p className="inventory-muted">
            Внось предмети вручну. Назви поки не перевіряються за каталогом гри.
          </p>

          <form className="inventory-form" onSubmit={handleSubmit}>
            <label htmlFor="item-name">Назва предмета</label>
            <input
              id="item-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={150}
              placeholder="Наприклад, Black Stone"
              required
            />

            <label htmlFor="item-category">Категорія</label>
            <select
              id="item-category"
              value={category}
              onChange={(event) => setCategory(event.target.value as Category)}
            >
              <option value="gear">Спорядження</option>
              <option value="material">Матеріали</option>
              <option value="consumable">Витратні предмети</option>
              <option value="other">Інше</option>
            </select>

            <label htmlFor="item-quantity">Кількість</label>
            <input
              id="item-quantity"
              type="number"
              min="1"
              max="2000000000"
              step="1"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              required
            />

            <label htmlFor="item-notes">Нотатки (необов'язково)</label>
            <textarea
              id="item-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={500}
              rows={3}
              placeholder="Рівень посилення, місце зберігання..."
            />

            <button className="primary-button" type="submit" disabled={saving}>
              {saving ? "Збереження..." : "+ Зберегти предмет"}
            </button>
          </form>
        </section>

        <section className="panel">
          <div className="inventory-list-heading">
            <div>
              <div className="eyebrow">YOUR COLLECTION</div>
              <h2>Збережені предмети</h2>
            </div>
            <button
              className="outline-button"
              type="button"
              onClick={() => void loadItems()}
              disabled={loading}
            >
              ↻ Оновити
            </button>
          </div>

          {error && <p className="inventory-feedback error">{error}</p>}
          {message && <p className="inventory-feedback">{message}</p>}

          {loading ? (
            <p className="inventory-muted">Завантаження інвентаря...</p>
          ) : items.length === 0 ? (
            <div className="inventory-empty">
              <span>◇</span>
              <strong>Інвентар поки порожній</strong>
              <p>Додай перший предмет у формі ліворуч.</p>
            </div>
          ) : (
            <div className="inventory-items">
              {items.map((item) => (
                <article className="inventory-item" key={item.id}>
                  <div className="inventory-item-icon">◇</div>
                  <div className="inventory-item-copy">
                    <strong>{item.name}</strong>
                    <span>{categoryLabels[item.category]}</span>
                    {item.notes && <p>{item.notes}</p>}
                  </div>
                  <div className="inventory-item-actions">
                    <strong>×{item.quantity.toLocaleString("uk-UA")}</strong>
                    <button
                      className="delete-button"
                      type="button"
                      onClick={() => void handleDelete(item)}
                      aria-label={`Видалити ${item.name}`}
                    >
                      Видалити
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      <footer className="inventory-footer">
        BDO COMPANION / Локальний прототип · Неофіційний фан-проєкт
      </footer>
    </main>
  );
}
