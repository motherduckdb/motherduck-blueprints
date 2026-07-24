import { useSQLQuery } from "@motherduck/react-sql-query";
import type { CSSProperties } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export const REQUIRED_DATABASES = [{ alias: "wikipedia_pageviews", shareName: "wikipedia_pageviews" }];

type SummaryRow = {
  article: string;
  total_views: number | string;
  avg_daily_views: number | string;
  views_last_7_days: number | string;
  first_viewed_on: string;
  last_viewed_on: string;
  loaded_at_utc: string;
};

type DailyRow = {
  viewed_on: string;
  article: string;
  views: number | string;
};

const palette = ["#2563eb", "#059669", "#dc2626", "#7c3aed", "#d97706", "#0891b2"];

function asNumber(value: number | string | null | undefined) {
  if (value == null) return 0;
  return Number(value);
}

function formatNumber(value: number | string | null | undefined) {
  return new Intl.NumberFormat("en-US").format(asNumber(value));
}

function formatCompact(value: number | string | null | undefined) {
  return new Intl.NumberFormat("en-US", { notation: "compact" }).format(asNumber(value));
}

function transformDaily(rows: DailyRow[] | undefined) {
  const byDate = new Map<string, Record<string, number | string>>();
  for (const row of rows ?? []) {
    const current = byDate.get(row.viewed_on) ?? { viewed_on: row.viewed_on };
    current[row.article] = asNumber(row.views);
    byDate.set(row.viewed_on, current);
  }
  return Array.from(byDate.values()).sort((a, b) =>
    String(a.viewed_on).localeCompare(String(b.viewed_on)),
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div style={styles.loadingBlock}>
      <div style={styles.loadingTitle}>{label}</div>
      <div style={styles.loadingLine} />
      <div style={{ ...styles.loadingLine, width: "72%" }} />
    </div>
  );
}

function ErrorBlock({ message }: { message: string }) {
  return (
    <div style={styles.errorBlock}>
      <strong>Query failed</strong>
      <span>{message}</span>
    </div>
  );
}

export default function WikipediaPageviewsDive() {
  const summaryQuery = useSQLQuery<SummaryRow[]>(`
    SELECT
      article,
      total_views,
      avg_daily_views,
      views_last_7_days,
      first_viewed_on::VARCHAR AS first_viewed_on,
      last_viewed_on::VARCHAR AS last_viewed_on,
      loaded_at_utc::VARCHAR AS loaded_at_utc
    FROM "wikipedia_pageviews"."main"."pageviews_article_summary"
    ORDER BY total_views DESC
  `);

  const dailyQuery = useSQLQuery<DailyRow[]>(`
    SELECT
      viewed_on::VARCHAR AS viewed_on,
      article,
      views
    FROM "wikipedia_pageviews"."main"."pageviews_daily"
    WHERE viewed_on >= current_date - INTERVAL 30 DAY
    ORDER BY viewed_on, article
  `);

  const summary = summaryQuery.data ?? [];
  const daily = dailyQuery.data ?? [];
  const trend = transformDaily(daily);
  const articles = summary.map((row) => row.article);
  const totalViews = summary.reduce((sum, row) => sum + asNumber(row.total_views), 0);
  const last7 = summary.reduce((sum, row) => sum + asNumber(row.views_last_7_days), 0);
  const leadingArticle = summary[0];
  const latestLoad = summary[0]?.loaded_at_utc ?? "Pending";

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <div>
          <p style={styles.eyebrow}>MotherDuck Blueprints example</p>
          <h1 style={styles.title}>Wikipedia Pageviews</h1>
          <p style={styles.subtitle}>
            Recent public Wikimedia pageview counts, loaded by a Flight and read from a MotherDuck share.
          </p>
        </div>
        <div style={styles.timestamp}>
          <span style={styles.timestampLabel}>Last load</span>
          <span>{latestLoad}</span>
        </div>
      </header>

      {summaryQuery.error ? <ErrorBlock message={summaryQuery.error.message} /> : null}
      {dailyQuery.error ? <ErrorBlock message={dailyQuery.error.message} /> : null}

      <section style={styles.kpiGrid}>
        <div style={styles.kpiCard}>
          <span style={styles.kpiLabel}>Total views</span>
          <strong style={styles.kpiValue}>{formatCompact(totalViews)}</strong>
        </div>
        <div style={styles.kpiCard}>
          <span style={styles.kpiLabel}>Last 7 days</span>
          <strong style={styles.kpiValue}>{formatCompact(last7)}</strong>
        </div>
        <div style={styles.kpiCard}>
          <span style={styles.kpiLabel}>Tracked articles</span>
          <strong style={styles.kpiValue}>{summary.length}</strong>
        </div>
        <div style={styles.kpiCard}>
          <span style={styles.kpiLabel}>Top article</span>
          <strong style={styles.kpiValueSmall}>{leadingArticle?.article ?? "Pending"}</strong>
        </div>
      </section>

      <section style={styles.grid}>
        <div style={styles.panel}>
          <div style={styles.panelHeader}>
            <h2 style={styles.panelTitle}>Daily trend</h2>
          </div>
          {dailyQuery.isLoading ? (
            <LoadingBlock label="Loading daily trend" />
          ) : (
            <div style={styles.chart}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ top: 12, right: 18, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#e5e7eb" vertical={false} />
                  <XAxis dataKey="viewed_on" tick={{ fontSize: 11 }} minTickGap={24} />
                  <YAxis tickFormatter={formatCompact} tick={{ fontSize: 11 }} width={56} />
                  <Tooltip formatter={(value) => formatNumber(value as number)} />
                  <Legend />
                  {articles.map((article, index) => (
                    <Area
                      key={article}
                      type="monotone"
                      dataKey={article}
                      stroke={palette[index % palette.length]}
                      fill={palette[index % palette.length]}
                      fillOpacity={0.16}
                      strokeWidth={2}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div style={styles.panel}>
          <div style={styles.panelHeader}>
            <h2 style={styles.panelTitle}>Article totals</h2>
          </div>
          {summaryQuery.isLoading ? (
            <LoadingBlock label="Loading article totals" />
          ) : (
            <div style={styles.chart}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary} layout="vertical" margin={{ top: 8, right: 24, bottom: 0, left: 32 }}>
                  <CartesianGrid stroke="#e5e7eb" horizontal={false} />
                  <XAxis type="number" tickFormatter={formatCompact} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="article" width={92} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(value) => formatNumber(value as number)} />
                  <Bar dataKey="total_views" fill="#2563eb" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </section>

      <section style={styles.panel}>
        <div style={styles.panelHeader}>
          <h2 style={styles.panelTitle}>Summary table</h2>
        </div>
        {summaryQuery.isLoading ? (
          <LoadingBlock label="Loading summary table" />
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Article</th>
                  <th style={styles.thRight}>Total views</th>
                  <th style={styles.thRight}>Avg daily</th>
                  <th style={styles.thRight}>Last 7 days</th>
                  <th style={styles.th}>Range</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((row) => (
                  <tr key={row.article}>
                    <td style={styles.tdStrong}>{row.article}</td>
                    <td style={styles.tdRight}>{formatNumber(row.total_views)}</td>
                    <td style={styles.tdRight}>{formatNumber(Math.round(asNumber(row.avg_daily_views)))}</td>
                    <td style={styles.tdRight}>{formatNumber(row.views_last_7_days)}</td>
                    <td style={styles.td}>{row.first_viewed_on} to {row.last_viewed_on}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    padding: "28px",
    background: "#f6f7f9",
    color: "#111827",
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    gap: "24px",
    alignItems: "flex-end",
    marginBottom: "24px",
  },
  eyebrow: {
    margin: "0 0 8px",
    color: "#2563eb",
    fontSize: "12px",
    fontWeight: 700,
    textTransform: "uppercase",
  },
  title: {
    margin: 0,
    fontSize: "34px",
    fontWeight: 800,
    lineHeight: 1.1,
  },
  subtitle: {
    maxWidth: "760px",
    margin: "10px 0 0",
    color: "#4b5563",
    fontSize: "15px",
    lineHeight: 1.5,
  },
  timestamp: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    minWidth: "220px",
    color: "#374151",
    fontSize: "13px",
    textAlign: "right",
  },
  timestampLabel: {
    color: "#6b7280",
    fontSize: "12px",
    textTransform: "uppercase",
    fontWeight: 700,
  },
  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: "12px",
    marginBottom: "16px",
  },
  kpiCard: {
    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    padding: "16px",
    minHeight: "86px",
  },
  kpiLabel: {
    display: "block",
    color: "#6b7280",
    fontSize: "12px",
    fontWeight: 700,
    textTransform: "uppercase",
    marginBottom: "8px",
  },
  kpiValue: {
    display: "block",
    fontSize: "28px",
    lineHeight: 1,
  },
  kpiValueSmall: {
    display: "block",
    fontSize: "20px",
    lineHeight: 1.2,
    overflowWrap: "anywhere",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.35fr) minmax(360px, 0.65fr)",
    gap: "16px",
    marginBottom: "16px",
  },
  panel: {
    background: "#ffffff",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    padding: "16px",
  },
  panelHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
    marginBottom: "12px",
  },
  panelTitle: {
    margin: 0,
    fontSize: "16px",
  },
  chart: {
    width: "100%",
    height: "340px",
  },
  tableWrap: {
    overflowX: "auto",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "13px",
  },
  th: {
    textAlign: "left",
    color: "#6b7280",
    borderBottom: "1px solid #e5e7eb",
    padding: "10px 8px",
    whiteSpace: "nowrap",
  },
  thRight: {
    textAlign: "right",
    color: "#6b7280",
    borderBottom: "1px solid #e5e7eb",
    padding: "10px 8px",
    whiteSpace: "nowrap",
  },
  td: {
    borderBottom: "1px solid #f1f5f9",
    padding: "12px 8px",
    whiteSpace: "nowrap",
  },
  tdStrong: {
    borderBottom: "1px solid #f1f5f9",
    padding: "12px 8px",
    fontWeight: 700,
  },
  tdRight: {
    borderBottom: "1px solid #f1f5f9",
    padding: "12px 8px",
    textAlign: "right",
    whiteSpace: "nowrap",
  },
  loadingBlock: {
    minHeight: "160px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    gap: "12px",
    color: "#6b7280",
  },
  loadingTitle: {
    fontSize: "13px",
    fontWeight: 700,
  },
  loadingLine: {
    height: "12px",
    width: "88%",
    borderRadius: "999px",
    background: "#e5e7eb",
  },
  errorBlock: {
    display: "flex",
    gap: "12px",
    alignItems: "center",
    marginBottom: "16px",
    padding: "12px 14px",
    border: "1px solid #fecaca",
    borderRadius: "8px",
    background: "#fef2f2",
    color: "#991b1b",
    fontSize: "13px",
  },
};
