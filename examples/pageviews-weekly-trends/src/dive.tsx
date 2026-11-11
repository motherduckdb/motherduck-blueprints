import { useSQLQuery } from "@motherduck/react-sql-query";
import type { CSSProperties } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const REQUIRED_DATABASES = [{ alias: "pageviews_trends", shareName: "pageviews_trends" }];

type TrendRow = {
  article: string;
  week_start: string;
  views: number | string;
  previous_week_views: number | string | null;
  week_over_week_pct: number | string | null;
  four_week_average: number | string;
  transformed_at_utc: string;
};

const palette = ["#2563eb", "#059669", "#dc2626", "#7c3aed", "#d97706", "#0891b2"];

function asNumber(value: number | string | null | undefined) {
  return value == null ? 0 : Number(value);
}

function formatNumber(value: number | string | null | undefined) {
  return new Intl.NumberFormat("en-US").format(asNumber(value));
}

function formatChange(value: number | string | null) {
  if (value == null) return "n/a";
  const change = asNumber(value);
  return `${change > 0 ? "+" : ""}${change.toFixed(1)}%`;
}

function byWeek(rows: TrendRow[]) {
  const weeks = new Map<string, Record<string, number | string>>();
  for (const row of rows) {
    const week = weeks.get(row.week_start) ?? { week_start: row.week_start };
    week[row.article] = asNumber(row.views);
    weeks.set(row.week_start, week);
  }
  return Array.from(weeks.values()).sort((a, b) => String(a.week_start).localeCompare(String(b.week_start)));
}

export default function PageviewsWeeklyTrends() {
  // The Flight does the aggregation; the Dive only reads the finished reporting view.
  const trendsQuery = useSQLQuery<TrendRow[]>(`
    SELECT
      article,
      strftime(week_start, '%Y-%m-%d') AS week_start,
      views,
      previous_week_views,
      week_over_week_pct,
      four_week_average,
      strftime(transformed_at_utc, '%Y-%m-%d %H:%M UTC') AS transformed_at_utc
    FROM pageviews_trends.main.article_trends
    ORDER BY week_start, article
  `);

  const rows = trendsQuery.data ?? [];
  const articles = Array.from(new Set(rows.map((row) => row.article))).sort();
  const latestWeek = rows.reduce((latest, row) => (row.week_start > latest ? row.week_start : latest), "");
  const latest = rows.filter((row) => row.week_start === latestWeek);
  const refreshedAt = rows[0]?.transformed_at_utc;

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <p style={styles.eyebrow}>MotherDuck Dive</p>
        <h1 style={styles.title}>Pageviews weekly trends</h1>
        <p style={styles.subtitle}>
          Complete weeks only, Monday to Sunday.
          {refreshedAt ? ` Rebuilt ${refreshedAt}.` : ""}
        </p>
      </header>

      {trendsQuery.error ? (
        <div style={styles.error}>
          <strong>Query failed</strong>
          <span>{trendsQuery.error.message}</span>
        </div>
      ) : null}
      {trendsQuery.isLoading ? <p style={styles.muted}>Loading trends...</p> : null}
      {!trendsQuery.isLoading && !trendsQuery.error && rows.length === 0 ? (
        <p style={styles.muted}>No complete week is available yet. The transformation needs seven loaded days.</p>
      ) : null}

      <section style={styles.cards}>
        {latest.map((row) => (
          <article key={row.article} style={styles.card}>
            <span style={styles.cardLabel}>{row.article}</span>
            <strong style={styles.cardValue}>{formatNumber(row.views)}</strong>
            <span style={asNumber(row.week_over_week_pct) < 0 ? styles.down : styles.up}>
              {formatChange(row.week_over_week_pct)} vs previous week
            </span>
            <span style={styles.muted}>4-week average {formatNumber(row.four_week_average)}</span>
          </article>
        ))}
      </section>

      {rows.length > 0 ? (
        <section style={styles.panel}>
          <h2 style={styles.panelTitle}>Weekly views</h2>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={byWeek(rows)} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#e7ecf3" vertical={false} />
              <XAxis dataKey="week_start" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatNumber(value)} width={72} />
              <Tooltip formatter={(value) => formatNumber(value as number)} />
              <Legend />
              {articles.map((article, index) => (
                <Line
                  key={article}
                  type="monotone"
                  dataKey={article}
                  stroke={palette[index % palette.length]}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </section>
      ) : null}
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
  header: { marginBottom: "24px" },
  eyebrow: {
    margin: "0 0 8px",
    color: "#2563eb",
    fontSize: "12px",
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  },
  title: { margin: 0, fontSize: "34px", lineHeight: 1.1 },
  subtitle: { margin: "10px 0 0", color: "#526079", lineHeight: 1.6 },
  muted: { color: "#64748b", fontSize: "13px" },
  cards: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "14px",
    marginBottom: "18px",
  },
  card: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    padding: "20px",
    border: "1px solid #dce3ed",
    borderRadius: "14px",
    background: "#ffffff",
  },
  cardLabel: { color: "#64748b", fontSize: "13px", fontWeight: 600 },
  cardValue: { fontSize: "28px" },
  up: { color: "#047857", fontSize: "13px", fontWeight: 600 },
  down: { color: "#b91c1c", fontSize: "13px", fontWeight: 600 },
  panel: { padding: "20px 22px", border: "1px solid #dce3ed", borderRadius: "16px", background: "#ffffff" },
  panelTitle: { margin: "0 0 16px", fontSize: "19px" },
  error: {
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
