"use client";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { formatSeen } from "../_lib/api";

type Node = {
  node_id: number;
  name: string;
  territory: string | null;
  manager_id: number | null;
  manager_name: string | null;
  contribution: number | null;
  products: string[];
};

type Nodes = {
  contribution: { available: number; total: number; updated_at: number } | null;
  nodes: Node[];
};

const NO_TERRITORY = "Без території";

export default function NodesPage() {
  const { data, error, reload } = useApiData<Nodes>("/api/nodes");
  const nodes = data?.nodes ?? [];
  const points = data?.contribution;

  // Підвузли (ферми, шахти) показуємо під їхнім головним вузлом, якщо його теж вкладено.
  const invested = new Set(nodes.map((node) => node.node_id));
  const children = new Map<number, Node[]>();
  for (const node of nodes) {
    if (node.manager_id && invested.has(node.manager_id)) {
      children.set(node.manager_id, [...(children.get(node.manager_id) ?? []), node]);
    }
  }
  const tops = nodes.filter((node) => !(node.manager_id && invested.has(node.manager_id)));
  const territories = new Map<string, Node[]>();
  for (const node of tops) {
    const key = node.territory ?? NO_TERRITORY;
    territories.set(key, [...(territories.get(key) ?? []), node]);
  }

  return (
    <AccountPage
      title="Вузли"
      subtitle="Очки внеску сім'ї й вузли, у які їх вкладено, приходять при вході у світ. Назви, території й продукти вузлів — з твого клієнта гри."
      onRecords={reload}
    >
      <section className="inventory-summary">
        <div>
          <span className="muted-label">ВІЛЬНІ CP</span>
          <strong>{points ? points.available.toLocaleString("uk-UA") : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">УСЬОГО CP</span>
          <strong>{points ? points.total.toLocaleString("uk-UA") : "—"}</strong>
        </div>
        <div>
          <span className="muted-label">ВКЛАДЕНИХ ВУЗЛІВ</span>
          <strong>{data ? nodes.length.toLocaleString("uk-UA") : "—"}</strong>
        </div>
      </section>

      {points && (
        <p className="inventory-muted">
          Оновлено {formatSeen(points.updated_at)}. Решта витрачених CP ({(points.total - points.available).toLocaleString("uk-UA")} усього)
          може йти на житло й майстерні в містах — їх тут поки не видно.
        </p>
      )}

      {error && <p className="inventory-feedback error">{error}</p>}

      {data !== null && nodes.length === 0 ? (
        <EmptyState title="Вузлів ще немає">Увімкни агента й зайди персонажем у світ.</EmptyState>
      ) : (
        [...territories.entries()].map(([territory, group]) => (
          <section className="panel account-group" key={territory}>
            <div className="inventory-list-heading">
              <div>
                <div className="eyebrow">{group.length} ВУЗЛ.</div>
                <h2>{territory}</h2>
              </div>
            </div>
            <ul className="node-list">
              {group.map((node) => (
                <li key={node.node_id}>
                  <div className="node-row">
                    <span>
                      <strong>{node.name}</strong>
                      {node.products.length > 0 && <small>{node.products.join(", ")}</small>}
                    </span>
                    {node.contribution ? <span className="node-cost">{node.contribution} CP</span> : null}
                  </div>
                  {(children.get(node.node_id) ?? []).length > 0 && (
                    <ul className="node-children">
                      {(children.get(node.node_id) ?? []).map((child) => (
                        <li key={child.node_id}>
                          <div className="node-row">
                            <span>
                              {child.name}
                              {child.products.length > 0 && <small>{child.products.join(", ")}</small>}
                            </span>
                            {child.contribution ? <span className="node-cost">{child.contribution} CP</span> : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </AccountPage>
  );
}
