"use client";

import Link from "next/link";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";

type Status = "done" | "open" | "locked";

type Bonus = { type: number; label: string; value: number; unit: string | null };

type Page = { quest_key: string; name: string; status: Status; bonus: Bonus | null };

type Book = { book_key: number; name: string; requirement: string | null; done: number; pages: Page[] };

type Journal = { journal_key: number; name: string; description: string | null; done: number; total: number; books: Book[] };

type FamilyBonus = Bonus & {
  gained: number;
  missing: {
    quest_key: string;
    name: string;
    giver: string | null;
    value: number;
    status: Status;
    journal_key: number | null;
    book_key: number | null;
  }[];
};

type Journals = { journals: Journal[]; bonuses: FamilyBonus[]; quests_known: boolean };

const STATUS_LABELS: Record<Status, string> = { done: "виконано", open: "відкрито", locked: "не відкрито" };

function amount(value: number, unit: string | null) {
  const text = Number.isInteger(value) ? value.toLocaleString("uk-UA") : value.toFixed(1);
  return unit ? `${text} ${unit}` : text;
}

function complete(done: number, total: number) {
  return total > 0 && done >= total ? " complete" : "";
}

/** Розгортає журнал і книгу зі сторінкою та прокручує до неї, ненадовго підсвітивши. */
function openPage(journal: number, book: number, quest: string) {
  for (const id of [`journal-${journal}`, `book-${journal}-${book}`]) {
    const details = document.getElementById(id);
    if (details instanceof HTMLDetailsElement) details.open = true;
  }
  const page = document.getElementById(`page-${quest}`);
  if (!page) return;
  page.scrollIntoView({ behavior: "smooth", block: "center" });
  page.classList.remove("flash");
  void page.offsetWidth; // перезапуск анімації при повторному кліку
  page.classList.add("flash");
}

function Progress({ done, total }: { done: number; total: number }) {
  return (
    <span className="knowledge-progress">
      <span className="progress-track">
        <span className="progress-fill" style={{ width: `${total ? (100 * done) / total : 0}%` }} />
      </span>
      <small>{done} / {total}</small>
    </span>
  );
}

export default function JournalsPage() {
  const { data, error, reload } = useApiData<Journals>("/api/journals");
  const journals = data?.journals ?? [];

  return (
    <AccountPage
      title="Журнали пригод"
      subtitle="Журнали з твого клієнта гри, прогрес — за списками квестів, що приходять при вході кожним персонажем. Журнали спільні для сім'ї."
      onRecords={reload}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {data && !data.quests_known && (
        <p className="inventory-feedback">
          Списків квестів ще немає: увімкни агента й зайди у світ персонажами — прогрес з&apos;явиться сам.
        </p>
      )}

      {data !== null && journals.length === 0 ? (
        <EmptyState title="Журналів ще немає">
          Імпортуй вивід bdo-data-extractor на сторінці <Link className="text-link" href="/game-data/">«Дані гри»</Link>.
        </EmptyState>
      ) : (
        <>
          {data && data.bonuses.length > 0 && (
            <section className="panel account-group">
              <div className="eyebrow">БОНУСИ СІМ&apos;Ї ЗА КВЕСТИ</div>
              <ul className="journal-bonuses">
                {data.bonuses.map((bonus) => (
                  <li key={bonus.type}>
                    <details className={complete(bonus.gained, bonus.value).trim() || undefined}>
                      <summary>
                        <strong>{bonus.label}</strong>
                        <span className="journal-bonus-total">
                          <span className="progress-track">
                            <span className="progress-fill" style={{ width: `${bonus.value ? (100 * bonus.gained) / bonus.value : 0}%` }} />
                          </span>
                          <span className={bonus.gained >= bonus.value ? "journal-complete" : undefined}>
                            {amount(bonus.gained, bonus.unit)} / {amount(bonus.value, bonus.unit)}
                          </span>
                        </span>
                      </summary>
                      {bonus.missing.length === 0 ? (
                        <p className="inventory-muted">Усе отримано.</p>
                      ) : (
                        <ul className="journal-missing">
                          {bonus.missing.map((quest) => (
                            <li key={quest.quest_key}>
                              <span>
                                {quest.journal_key !== null && quest.book_key !== null ? (
                                  <a
                                    href={`#page-${quest.quest_key}`}
                                    onClick={(event) => {
                                      event.preventDefault();
                                      openPage(quest.journal_key!, quest.book_key!, quest.quest_key);
                                    }}
                                  >
                                    {quest.name}
                                  </a>
                                ) : (
                                  <Link href={`/quests/?q=${encodeURIComponent(quest.name)}`}>{quest.name}</Link>
                                )}
                                <small>
                                  {quest.giver}
                                  {quest.journal_key !== null
                                    ? ` · ${journals.find((j) => j.journal_key === quest.journal_key)?.name ?? "журнал"}`
                                    : " · не з журналу"}
                                </small>
                              </span>
                              <span className={`journal-status ${quest.status}`}>
                                +{amount(quest.value, bonus.unit)} · {STATUS_LABELS[quest.status]}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </details>
                  </li>
                ))}
              </ul>
              <p className="inventory-muted">
                Список виконаних квестів із трафіку неповний (у грі лічильник більший), тож частина «не відкритих»
                може бути вже виконана.
              </p>
            </section>
          )}

          <section className="panel account-group">
            <div className="eyebrow">ЖУРНАЛИ</div>
            <div className="knowledge-tree">
              {journals.map((journal) => (
                <details
                  className={`knowledge-category${complete(journal.done, journal.total)}`}
                  key={journal.journal_key}
                  id={`journal-${journal.journal_key}`}
                >
                  <summary>
                    <strong>{journal.name}</strong>
                    <Progress done={journal.done} total={journal.total} />
                  </summary>
                  <div className="knowledge-children">
                    {journal.description && <p className="inventory-muted">{journal.description}</p>}
                    {journal.books.map((book) => (
                      <details
                        className={`knowledge-category${complete(book.done, book.pages.length)}`}
                        key={book.book_key}
                        id={`book-${journal.journal_key}-${book.book_key}`}
                      >
                        <summary>
                          <strong>{book.name}</strong>
                          <Progress done={book.done} total={book.pages.length} />
                        </summary>
                        <div className="knowledge-children">
                          {book.requirement && <p className="journal-requirement">{book.requirement}</p>}
                          <ol className="journal-pages">
                            {book.pages.map((page) => (
                              <li key={page.quest_key} className={page.status} id={`page-${page.quest_key}`}>
                                <span className="journal-mark" aria-hidden="true">
                                  {page.status === "done" ? "✓" : page.status === "open" ? "•" : "○"}
                                </span>
                                <span className="journal-page-name">{page.name}</span>
                                {page.bonus && (
                                  <span className="journal-bonus">+{amount(page.bonus.value, page.bonus.unit)} {page.bonus.label}</span>
                                )}
                                <span className={`journal-status ${page.status}`}>{STATUS_LABELS[page.status]}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      </details>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </section>
        </>
      )}
    </AccountPage>
  );
}
