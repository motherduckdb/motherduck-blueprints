import { useSQLQuery } from "@motherduck/react-sql-query";

export const REQUIRED_DATABASES = [{ alias: "__BLUEPRINT_NAME__", shareName: "__DATABASE_NAME__" }];

export default function BlueprintDive() {
  const metrics = useSQLQuery(`
    SELECT metric, value, loaded_at_utc
    FROM "__BLUEPRINT_NAME__"."main"."starter_metrics"
    ORDER BY metric
  `);

  const rows = (metrics.data ?? []) as Array<{
    metric: string;
    value: number;
    loaded_at_utc: string;
  }>;

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: 32, maxWidth: 760 }}>
      <p style={{ color: "#5f6b7a", margin: 0 }}>MotherDuck blueprint starter</p>
      <h1 style={{ margin: "8px 0 24px" }}>__BLUEPRINT_NAME__</h1>
      {metrics.isLoading ? (
        <p>Loading metrics...</p>
      ) : metrics.isError ? (
        <p>Unable to load metrics.</p>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={headerStyle}>Metric</th>
              <th style={headerStyle}>Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.metric}>
                <td style={cellStyle}>{row.metric}</td>
                <td style={cellStyle}>{Number(row.value).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

const headerStyle = {
  textAlign: "left",
  borderBottom: "1px solid #d9dee7",
  padding: "10px 8px",
} as const;

const cellStyle = {
  borderBottom: "1px solid #eef1f5",
  padding: "10px 8px",
} as const;
