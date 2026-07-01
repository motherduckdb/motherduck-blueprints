import { useSQLQuery } from "@motherduck/react-sql-query";
import type { CSSProperties } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";

export const REQUIRED_DATABASES = [{ alias: "__DATABASE_NAME__", shareName: "__DATABASE_NAME__" }];

type SummaryRow = {
  metric: string;
  current_value: number | string;
  avg_value: number | string;
  total_value: number | string;
  first_measured_on: string;
  last_measured_on: string;
  loaded_at_utc: string;
};

type DailyRow = {
  measured_on: string;
  metric: string;
  value: number | string;
};

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

function formatMetricName(value: string) {
  return value.replace(/_/g, " ");
}

function transformDaily(rows: DailyRow[]) {
  const byDate = new Map<string, Record<string, number | string>>();
  for (const row of rows) {
    const current = byDate.get(row.measured_on) ?? { measured_on: row.measured_on };
    current[row.metric] = asNumber(row.value);
    byDate.set(row.measured_on, current);
  }
  return Array.from(byDate.values()).sort((left, right) =>
    String(left.measured_on).localeCompare(String(right.measured_on)),
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div style={styles.loadingBlock}>
      <span style={styles.loadingTitle}>{label}</span>
      <span style={styles.loadingLine} />
      <span style={{ ...styles.loadingLine, width: "64%" }} />
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

export default function BlueprintDive() {
  const summaryQuery = useSQLQuery<SummaryRow[]>(`
    SELECT
      metric,
      current_value,
      avg_value,
      total_value,
      first_measured_on::VARCHAR AS first_measured_on,
      last_measured_on::VARCHAR AS last_measured_on,
      loaded_at_utc::VARCHAR AS loaded_at_utc
    FROM "__DATABASE_NAME__"."main"."starter_metric_summary"
    ORDER BY current_value DESC
  `);

  const dailyQuery = useSQLQuery<DailyRow[]>(`
    SELECT
      measured_on::VARCHAR AS measured_on,
      metric,
      value
    FROM "__DATABASE_NAME__"."main"."starter_daily_metrics"
    ORDER BY measured_on, metric
  `);

  const summary = summaryQuery.data ?? [];
  const daily = dailyQuery.data ?? [];
  const trend = transformDaily(daily);
  const metrics = summary.map((row) => row.metric);
  const latestLoad = summary[0]?.loaded_at_utc ?? "Pending";

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <div>
          <p style={styles.eyebrow}>MotherDuck blueprint starter</p>
          <h1 style={styles.title}>__BLUEPRINT_NAME__</h1>
          <p style={styles.subtitle}>
            Daily starter metrics loaded by the project Flight and published through the project share.
          </p>
        </div>
        <div style={styles.loadBadge}>
          <span style={styles.loadLabel}>Last load</span>
          <span>{latestLoad}</span>
        </div>
      </header>

      {summaryQuery.error ? <ErrorBlock message={summaryQuery.error.message} /> : null}
      {dailyQuery.error ? <ErrorBlock message={dailyQuery.error.message} /> : null}

      {summaryQuery.isLoading ? (
        <LoadingBlock label="Loading metric summary" />
      ) : (
        <section style={styles.kpiGrid}>
          {summary.map((row) => (
            <article key={row.metric} style={styles.kpiCard}>
              <span style={styles.kpiLabel}>{formatMetricName(row.metric)}</span>
              <strong style={styles.kpiValue}>{formatCompact(row.current_value)}</strong>
              <span style={styles.kpiMeta}>avg {formatNumber(Math.round(asNumber(row.avg_value)))}</span>
            </article>
          ))}
        </section>
      )}

      <section style={styles.panel}>
        <div style={styles.panelHeader}>
          <h2 style={styles.panelTitle}>Daily metric trend</h2>
        </div>
        {dailyQuery.isLoading ? (
          <LoadingBlock label="Loading daily trend" />
        ) : (
          <div style={styles.chart}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend} margin={{ top: 12, right: 24, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="measured_on" minTickGap={24} tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={formatCompact} tick={{ fontSize: 11 }} width={56} />
                <Tooltip formatter={(value) => formatNumber(value as number)} />
                {metrics.map((metric, index) => (
                  <Line
                    key={metric}
                    type="monotone"
                    dataKey={metric}
                    name={formatMetricName(metric)}
                    stroke={palette[index % palette.length]}
                    dot={false}
                    strokeWidth={2}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section style={styles.panel}>
        <div style={styles.panelHeader}>
          <h2 style={styles.panelTitle}>Metric summary</h2>
        </div>
        {summaryQuery.isLoading ? (
          <LoadingBlock label="Loading summary table" />
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Metric</th>
                  <th style={styles.thRight}>Current</th>
                  <th style={styles.thRight}>Average</th>
                  <th style={styles.thRight}>Total</th>
                  <th style={styles.th}>Range</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((row) => (
                  <tr key={row.metric}>
                    <td style={styles.tdStrong}>{formatMetricName(row.metric)}</td>
                    <td style={styles.tdRight}>{formatNumber(row.current_value)}</td>
                    <td style={styles.tdRight}>{formatNumber(Math.round(asNumber(row.avg_value)))}</td>
                    <td style={styles.tdRight}>{formatNumber(row.total_value)}</td>
                    <td style={styles.td}>{row.first_measured_on} to {row.last_measured_on}</td>
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

const palette = ["#2563eb", "#059669", "#dc2626", "#7c3aed"];

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
    flexWrap: "wrap",
    justifyContent: "space-between",
    alignItems: "flex-end",
    gap: "20px",
    marginBottom: "22px",
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
    fontSize: "32px",
    lineHeight: 1.1,
  },
  subtitle: {
    maxWidth: "720px",
    margin: "10px 0 0",
    color: "#4b5563",
    fontSize: "15px",
    lineHeight: 1.5,
  },
  loadBadge: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    minWidth: "220px",
    color: "#374151",
    fontSize: "13px",
    textAlign: "right",
  },
  loadLabel: {
    color: "#6b7280",
    fontSize: "12px",
    fontWeight: 700,
    textTransform: "uppercase",
  },
  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: "12px",
    marginBottom: "16px",
  },
  kpiCard: {
    minHeight: "96px",
    padding: "16px",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    background: "#ffffff",
  },
  kpiLabel: {
    display: "block",
    marginBottom: "8px",
    color: "#6b7280",
    fontSize: "12px",
    fontWeight: 700,
    textTransform: "uppercase",
  },
  kpiValue: {
    display: "block",
    fontSize: "28px",
    lineHeight: 1,
  },
  kpiMeta: {
    display: "block",
    marginTop: "10px",
    color: "#6b7280",
    fontSize: "12px",
  },
  panel: {
    marginBottom: "16px",
    padding: "16px",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    background: "#ffffff",
  },
  panelHeader: {
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
    padding: "10px 8px",
    borderBottom: "1px solid #e5e7eb",
    color: "#6b7280",
    textAlign: "left",
    whiteSpace: "nowrap",
  },
  thRight: {
    padding: "10px 8px",
    borderBottom: "1px solid #e5e7eb",
    color: "#6b7280",
    textAlign: "right",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "12px 8px",
    borderBottom: "1px solid #f1f5f9",
    whiteSpace: "nowrap",
  },
  tdStrong: {
    padding: "12px 8px",
    borderBottom: "1px solid #f1f5f9",
    fontWeight: 700,
    textTransform: "capitalize",
  },
  tdRight: {
    padding: "12px 8px",
    borderBottom: "1px solid #f1f5f9",
    textAlign: "right",
    whiteSpace: "nowrap",
  },
  loadingBlock: {
    minHeight: "144px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    gap: "12px",
    marginBottom: "16px",
    padding: "16px",
    border: "1px solid #e5e7eb",
    borderRadius: "8px",
    background: "#ffffff",
    color: "#6b7280",
  },
  loadingTitle: {
    fontSize: "13px",
    fontWeight: 700,
  },
  loadingLine: {
    width: "84%",
    height: "12px",
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
