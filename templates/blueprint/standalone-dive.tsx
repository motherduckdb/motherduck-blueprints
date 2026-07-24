import { useSQLQuery } from "@motherduck/react-sql-query";
import type { CSSProperties } from "react";

export const REQUIRED_DATABASES = [__REQUIRED_DATABASE__] as const;

type TableRow = {
  table_schema: string;
  table_name: string;
  table_type: string;
  column_count: number | string;
};

function asNumber(value: number | string) {
  return Number(value);
}

function ErrorBlock({ message }: { message: string }) {
  return (
    <div style={styles.errorBlock}>
      <strong>Query failed</strong>
      <span>{message}</span>
    </div>
  );
}

export default function StandaloneDive() {
  const tablesQuery = useSQLQuery<TableRow[]>(`
    SELECT
      tables.table_schema,
      tables.table_name,
      tables.table_type,
      count(columns.column_name)::BIGINT AS column_count
    FROM information_schema.tables AS tables
    LEFT JOIN information_schema.columns AS columns
      ON tables.table_catalog = columns.table_catalog
      AND tables.table_schema = columns.table_schema
      AND tables.table_name = columns.table_name
    WHERE tables.table_catalog = '__DATABASE_NAME__'
    GROUP BY ALL
    ORDER BY tables.table_schema, tables.table_name
  `);

  const tables = tablesQuery.data ?? [];
  const schemas = new Set(tables.map((table) => table.table_schema)).size;
  const columns = tables.reduce((total, table) => total + asNumber(table.column_count), 0);

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <div>
          <p style={styles.eyebrow}>MotherDuck Dive</p>
          <h1 style={styles.title}>__BLUEPRINT_NAME__</h1>
          <p style={styles.subtitle}>
            The declared share is connected. Replace this catalog view with queries and visualizations for your data.
          </p>
        </div>
        <span style={styles.databaseBadge}>__DATABASE_NAME__</span>
      </header>

      {tablesQuery.error ? <ErrorBlock message={tablesQuery.error.message} /> : null}

      <section style={styles.summaryGrid}>
        <article style={styles.summaryCard}>
          <span style={styles.summaryLabel}>Schemas</span>
          <strong style={styles.summaryValue}>{schemas}</strong>
        </article>
        <article style={styles.summaryCard}>
          <span style={styles.summaryLabel}>Tables and views</span>
          <strong style={styles.summaryValue}>{tables.length}</strong>
        </article>
        <article style={styles.summaryCard}>
          <span style={styles.summaryLabel}>Columns</span>
          <strong style={styles.summaryValue}>{columns}</strong>
        </article>
      </section>

      <section style={styles.panel}>
        <div style={styles.panelHeader}>
          <div>
            <p style={styles.panelEyebrow}>Connected data</p>
            <h2 style={styles.panelTitle}>Available tables</h2>
          </div>
          {tablesQuery.isLoading ? <span style={styles.loading}>Loading catalog...</span> : null}
        </div>

        {!tablesQuery.isLoading && tables.length === 0 && !tablesQuery.error ? (
          <p style={styles.empty}>The connected share does not expose any tables yet.</p>
        ) : null}

        {tables.length > 0 ? (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Schema</th>
                  <th style={styles.th}>Name</th>
                  <th style={styles.th}>Type</th>
                  <th style={styles.thRight}>Columns</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((table) => (
                  <tr key={`${table.table_schema}.${table.table_name}`}>
                    <td style={styles.td}>{table.table_schema}</td>
                    <td style={styles.tdStrong}>{table.table_name}</td>
                    <td style={styles.td}>{table.table_type}</td>
                    <td style={styles.tdRight}>{asNumber(table.column_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    padding: "32px",
    background: "#f5f7fb",
    color: "#172033",
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
  },
  header: {
    display: "flex",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: "24px",
    marginBottom: "24px",
  },
  eyebrow: {
    margin: "0 0 8px",
    color: "#2563eb",
    fontSize: "12px",
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  },
  title: { margin: 0, fontSize: "34px", lineHeight: 1.1 },
  subtitle: { maxWidth: "720px", margin: "10px 0 0", color: "#526079", lineHeight: 1.6 },
  databaseBadge: {
    padding: "8px 12px",
    border: "1px solid #cbd5e1",
    borderRadius: "999px",
    background: "#ffffff",
    color: "#334155",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    fontSize: "12px",
  },
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: "14px",
    marginBottom: "18px",
  },
  summaryCard: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    padding: "20px",
    border: "1px solid #dce3ed",
    borderRadius: "14px",
    background: "#ffffff",
  },
  summaryLabel: { color: "#64748b", fontSize: "13px", fontWeight: 600 },
  summaryValue: { fontSize: "28px" },
  panel: {
    overflow: "hidden",
    border: "1px solid #dce3ed",
    borderRadius: "16px",
    background: "#ffffff",
  },
  panelHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "16px",
    padding: "20px 22px",
    borderBottom: "1px solid #e7ecf3",
  },
  panelEyebrow: {
    margin: "0 0 4px",
    color: "#64748b",
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  },
  panelTitle: { margin: 0, fontSize: "19px" },
  loading: { color: "#64748b", fontSize: "13px" },
  empty: { margin: 0, padding: "28px 22px", color: "#64748b" },
  tableWrap: { overflowX: "auto" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "14px" },
  th: {
    padding: "12px 16px",
    borderBottom: "1px solid #e7ecf3",
    color: "#64748b",
    fontSize: "12px",
    textAlign: "left",
    textTransform: "uppercase",
  },
  thRight: {
    padding: "12px 16px",
    borderBottom: "1px solid #e7ecf3",
    color: "#64748b",
    fontSize: "12px",
    textAlign: "right",
    textTransform: "uppercase",
  },
  td: { padding: "13px 16px", borderBottom: "1px solid #eef2f7", color: "#526079" },
  tdStrong: { padding: "13px 16px", borderBottom: "1px solid #eef2f7", fontWeight: 650 },
  tdRight: { padding: "13px 16px", borderBottom: "1px solid #eef2f7", textAlign: "right" },
  errorBlock: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    marginBottom: "18px",
    padding: "14px 16px",
    border: "1px solid #fecaca",
    borderRadius: "12px",
    background: "#fef2f2",
    color: "#991b1b",
  },
};
