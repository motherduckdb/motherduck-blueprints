import { useSQLQuery } from "@motherduck/react-sql-query";

export const REQUIRED_DATABASES = [];

export default function Dive() {
  const result = useSQLQuery("SELECT 1 AS value");

  if (result.isLoading) {
    return <div style={{ padding: 24 }}>Loading...</div>;
  }

  if (result.error) {
    return <div style={{ padding: 24, color: "#b91c1c" }}>{result.error.message}</div>;
  }

  return (
    <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
      <h1>__DIVE_NAME__</h1>
      <pre>{JSON.stringify(result.data, null, 2)}</pre>
    </main>
  );
}

