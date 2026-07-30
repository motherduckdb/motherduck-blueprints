import { useSQLQuery } from "@motherduck/react-sql-query";
import { useState } from "react";
import { ExternalLink, Info, Loader2 } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export const REQUIRED_DATABASES = [{ alias: "ncs_field_recovery", shareName: "ncs_field_recovery" }];

type Area = "All areas" | "North sea" | "Norwegian sea" | "Barents sea";
type Status = "All statuses" | "Producing" | "Approved for production" | "Shut down";
type Hydrocarbon =
  | "All types"
  | "OIL"
  | "OIL/GAS"
  | "GAS"
  | "GAS/CONDENSATE"
  | "OIL/CONDENSATE";
type Ranking = "Highest recovery" | "Lowest recovery";

const AREAS: Area[] = ["All areas", "North sea", "Norwegian sea", "Barents sea"];
const STATUSES: Status[] = [
  "All statuses",
  "Producing",
  "Approved for production",
  "Shut down",
];
const HYDROCARBON_TYPES: Hydrocarbon[] = [
  "All types",
  "OIL",
  "OIL/GAS",
  "GAS",
  "GAS/CONDENSATE",
  "OIL/CONDENSATE",
];

const AREA_SQL: Record<Area, string> = {
  "All areas": "TRUE",
  "North sea": "main_area = 'North sea'",
  "Norwegian sea": "main_area = 'Norwegian sea'",
  "Barents sea": "main_area = 'Barents sea'",
};

const STATUS_SQL: Record<Status, string> = {
  "All statuses": "TRUE",
  Producing: "activity_status = 'Producing'",
  "Approved for production": "activity_status = 'Approved for production'",
  "Shut down": "activity_status = 'Shut down'",
};

const HYDROCARBON_SQL: Record<Hydrocarbon, string> = {
  "All types": "TRUE",
  OIL: "hydrocarbon_type = 'OIL'",
  "OIL/GAS": "hydrocarbon_type = 'OIL/GAS'",
  GAS: "hydrocarbon_type = 'GAS'",
  "GAS/CONDENSATE": "hydrocarbon_type = 'GAS/CONDENSATE'",
  "OIL/CONDENSATE": "hydrocarbon_type = 'OIL/CONDENSATE'",
};

const N = (value: unknown): number => (value != null ? Number(value) : 0);
const S = (value: unknown): string => (value != null ? String(value) : "");

function validChoice<T extends string>(value: T, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value) ? value : fallback;
}

function formatVolume(value: unknown): string {
  return `${N(value).toLocaleString("en-US", { maximumFractionDigits: 1 })}M`;
}

function formatPercent(value: unknown): string {
  return `${N(value).toFixed(1)}%`;
}

function formatOptionalPercent(value: unknown): string {
  return value == null ? "—" : formatPercent(value);
}

function QueryError({ message }: { message: string }) {
  return (
    <div
      className="flex gap-2 items-center text-sm py-3"
      style={{ color: "#bc1200" }}
      role="alert"
    >
      <Info size={16} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

function Skeleton({ height = 48 }: { height?: number }) {
  return (
    <div
      className="bg-gray-200 animate-pulse rounded"
      style={{ height, width: "100%" }}
      aria-hidden="true"
    />
  );
}

export default function NcsFieldRecoveryExplorer() {
  const [rawArea, setArea] = useState<Area>("All areas");
  const [rawStatus, setStatus] = useState<Status>("All statuses");
  const [rawHydrocarbon, setHydrocarbon] = useState<Hydrocarbon>("All types");
  const [rawRanking, setRanking] = useState<Ranking>("Highest recovery");

  const area = validChoice(rawArea, AREAS, "All areas");
  const status = validChoice(rawStatus, STATUSES, "All statuses");
  const hydrocarbon = validChoice(
    rawHydrocarbon,
    HYDROCARBON_TYPES,
    "All types",
  );
  const ranking = validChoice(
    rawRanking,
    ["Highest recovery", "Lowest recovery"] as const,
    "Highest recovery",
  );
  const filters = [
    AREA_SQL[area],
    STATUS_SQL[status],
    HYDROCARBON_SQL[hydrocarbon],
  ].join(" AND ");
  const rankingDirection = ranking === "Highest recovery" ? "DESC" : "ASC";

  const summaryQuery = useSQLQuery(`
    SELECT
      count(*) FILTER (WHERE oil_recovery_factor_pct IS NOT NULL) AS field_count,
      median(oil_recovery_factor_pct) AS median_recovery_pct,
      sum(recovered_oil_mill_sm3) AS recovered_oil_mill_sm3,
      sum(remaining_oe_mill_sm3_nonnegative) AS remaining_oe_mill_sm3,
      max(reserve_version) AS reserve_version,
      strftime(max(loaded_at_utc), '%Y-%m-%d %H:%M UTC') AS loaded_at
    FROM "ncs_field_recovery"."main"."field_recovery_latest"
    WHERE ${filters}
  `);

  const rankingQuery = useSQLQuery(`
    SELECT
      field_name,
      round(oil_recovery_factor_pct, 1) AS oil_recovery_factor_pct,
      round(inplace_oil_mill_sm3, 1) AS inplace_oil_mill_sm3,
      round(recoverable_oil_mill_sm3, 1) AS recoverable_oil_mill_sm3,
      activity_status
    FROM "ncs_field_recovery"."main"."field_recovery_latest"
    WHERE ${filters}
      AND oil_recovery_factor_pct IS NOT NULL
    ORDER BY oil_recovery_factor_pct ${rankingDirection}, field_name
    LIMIT 18
  `);

  const opportunityQuery = useSQLQuery(`
    SELECT
      field_name,
      main_area,
      operator_name,
      round(remaining_oe_mill_sm3_nonnegative, 1) AS remaining_oe_mill_sm3,
      round(remaining_oil_mill_sm3, 1) AS remaining_oil_mill_sm3,
      round(produced_share_of_recoverable_oil_pct, 1) AS produced_share_pct,
      fact_page_url
    FROM "ncs_field_recovery"."main"."field_recovery_latest"
    WHERE ${filters}
      AND remaining_oe_mill_sm3_nonnegative > 0
    ORDER BY remaining_oe_mill_sm3_nonnegative DESC, field_name
    LIMIT 7
  `);

  const summaryRows = Array.isArray(summaryQuery.data) ? summaryQuery.data : [];
  const summary = summaryRows[0] ?? {};
  const rankingRows = (Array.isArray(rankingQuery.data) ? rankingQuery.data : []).map(
    (row) => ({
      field_name: S(row.field_name),
      oil_recovery_factor_pct: N(row.oil_recovery_factor_pct),
      inplace_oil_mill_sm3: N(row.inplace_oil_mill_sm3),
      recoverable_oil_mill_sm3: N(row.recoverable_oil_mill_sm3),
      activity_status: S(row.activity_status),
    }),
  );
  const opportunityRows = Array.isArray(opportunityQuery.data)
    ? opportunityQuery.data
    : [];

  const resetFilters = () => {
    setArea("All areas");
    setStatus("All statuses");
    setHydrocarbon("All types");
    setRanking("Highest recovery");
  };

  return (
    <main
      className="min-h-screen p-4 md:p-6"
      style={{
        backgroundColor: "#f8f8f8",
        color: "#231f20",
        fontFamily:
          "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      <header className="flex flex-col sm:flex-row justify-between gap-4 sm:gap-6 mb-6 items-start">
        <div>
          <div className="flex gap-2 items-center mb-2">
            <span
              className="text-xs font-semibold uppercase tracking-wide px-2 py-1 rounded"
              style={{ backgroundColor: "#dcecf4", color: "#075d8c" }}
            >
              Official NCS data
            </span>
            <span className="text-xs" style={{ color: "#6a6a6a" }}>
              SODIR FactMaps
            </span>
          </div>
          <h1 className="text-2xl font-bold">NCS Field Recovery Explorer</h1>
          <p className="text-sm mt-2" style={{ color: "#6a6a6a", maxWidth: 680 }}>
            Transparent field comparisons using official recoverable, remaining,
            and in-place volume estimates. This is not an OREC calculation.
          </p>
        </div>
        <a
          href="https://factpages.sodir.no/en/field/TableView/Resources"
          target="_blank"
          rel="noopener noreferrer"
          className="flex gap-1 items-center text-sm font-medium min-h-11 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ color: "#0777b3", whiteSpace: "nowrap" }}
        >
          Source data <ExternalLink size={14} />
        </a>
      </header>

      <section className="flex flex-wrap gap-3 items-end mb-6">
        <label className="text-xs font-medium">
          <span className="block mb-1" style={{ color: "#6a6a6a" }}>Area</span>
          <select
            value={area}
            onChange={(event) => setArea(event.target.value as Area)}
            className="px-3 py-2 rounded border border-gray-200 text-sm min-h-11 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{ backgroundColor: "#ffffff", minWidth: 150 }}
          >
            {AREAS.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium">
          <span className="block mb-1" style={{ color: "#6a6a6a" }}>Field status</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as Status)}
            className="px-3 py-2 rounded border border-gray-200 text-sm min-h-11 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{ backgroundColor: "#ffffff", minWidth: 190 }}
          >
            {STATUSES.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium">
          <span className="block mb-1" style={{ color: "#6a6a6a" }}>Hydrocarbon type</span>
          <select
            value={hydrocarbon}
            onChange={(event) => setHydrocarbon(event.target.value as Hydrocarbon)}
            className="px-3 py-2 rounded border border-gray-200 text-sm min-h-11 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{ backgroundColor: "#ffffff", minWidth: 160 }}
          >
            {HYDROCARBON_TYPES.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <div className="flex gap-1" role="group" aria-label="Recovery ranking order">
          {(["Highest recovery", "Lowest recovery"] as Ranking[]).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setRanking(value)}
              aria-pressed={ranking === value}
              className="px-3 py-2 rounded text-sm font-medium min-h-11 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              style={{
                color: ranking === value ? "#ffffff" : "#231f20",
                backgroundColor: ranking === value ? "#0777b3" : "#e5e7eb",
              }}
            >
              {value}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={resetFilters}
          className="px-3 py-2 text-sm font-medium min-h-11 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ color: "#6a6a6a" }}
        >
          Reset
        </button>
      </section>

      <section className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-6 md:gap-8 mb-8">
        {[
          ["Fields with oil ratio", N(summary.field_count).toLocaleString()],
          ["Median oil recovery", formatOptionalPercent(summary.median_recovery_pct)],
          ["Recovered oil", formatVolume(summary.recovered_oil_mill_sm3)],
          ["Remaining oil equivalent", formatVolume(summary.remaining_oe_mill_sm3)],
        ].map(([label, value]) => (
          <div key={label}>
            {summaryQuery.isLoading ? (
              <Skeleton />
            ) : (
              <p className="text-3xl sm:text-4xl lg:text-5xl font-bold break-words" style={{ lineHeight: 1 }}>
                {value}
              </p>
            )}
            <p className="text-sm mt-2" style={{ color: "#6a6a6a" }}>{label}</p>
          </div>
        ))}
      </section>
      {summaryQuery.isError ? (
        <QueryError message={summaryQuery.error?.message || "Summary query failed"} />
      ) : null}

      <section className="mb-8">
        <div className="flex justify-between items-end gap-4 mb-3">
          <div>
            <h2 className="text-lg font-semibold">Official oil recovery ratio</h2>
            <p className="text-xs mt-1" style={{ color: "#6a6a6a" }}>
              Original recoverable oil ÷ original oil in place for oil-bearing
              field types. Up to 18 fields matching the filters.
            </p>
          </div>
          <span className="text-xs" style={{ color: "#6a6a6a" }}>
            Reserve version {S(summary.reserve_version) || "—"}
          </span>
        </div>
        {rankingQuery.isLoading ? (
          <div
            className="flex items-center justify-center"
            style={{ height: 280 }}
            role="status"
          >
            <Loader2
              className="animate-spin"
              size={24}
              style={{ color: "#0777b3" }}
              aria-hidden="true"
            />
            <span className="sr-only">Loading field recovery ranking</span>
          </div>
        ) : rankingRows.length === 0 ? (
          <p className="text-sm py-12 text-center" style={{ color: "#6a6a6a" }}>
            No fields with an official oil recovery ratio match these filters.
          </p>
        ) : (
          <div
            role="img"
            aria-label={`${ranking} oil recovery ratios for ${rankingRows.length} fields`}
          >
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={rankingRows}
                layout="vertical"
                margin={{ top: 4, right: 24, bottom: 4, left: 24 }}
                accessibilityLayer
              >
                <CartesianGrid stroke="#e0e0e0" horizontal={false} />
                <XAxis
                  type="number"
                  domain={[0, "dataMax"]}
                  tickFormatter={(value) => `${N(value).toFixed(0)}%`}
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  type="category"
                  dataKey="field_name"
                  width={112}
                  tick={{ fontSize: 10 }}
                />
                <Tooltip
                  formatter={(value, name) => [
                    name === "oil_recovery_factor_pct"
                      ? formatPercent(value)
                      : N(value).toFixed(1),
                    name === "oil_recovery_factor_pct"
                      ? "Oil recovery ratio"
                      : String(name),
                  ]}
                />
                <Bar
                  dataKey="oil_recovery_factor_pct"
                  fill="#0777b3"
                  radius={[0, 3, 3, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {rankingQuery.isError ? (
          <QueryError message={rankingQuery.error?.message || "Ranking query failed"} />
        ) : null}
      </section>

      <section>
        <div className="flex justify-between items-end gap-4 mb-2">
          <div>
            <h2 className="text-lg font-semibold">Largest remaining resource estimates</h2>
            <p className="text-xs mt-1" style={{ color: "#6a6a6a" }}>
              Official remaining oil-equivalent volume for the current selection.
            </p>
          </div>
          <span className="text-xs" style={{ color: "#6a6a6a" }}>
            Loaded {S(summary.loaded_at) || "—"}
          </span>
        </div>
        {opportunityQuery.isLoading ? (
          <div className="space-y-3 py-3">
            {[0, 1, 2, 3, 4].map((value) => <Skeleton key={value} height={34} />)}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">
                Fields with the largest remaining official oil-equivalent resource estimates
              </caption>
              <thead>
                <tr className="border-b border-gray-200">
                  <th scope="col" className="text-left py-3 font-semibold">Field</th>
                  <th scope="col" className="text-left py-3 font-semibold">Area</th>
                  <th scope="col" className="text-left py-3 font-semibold">Operator</th>
                  <th scope="col" className="text-right py-3 font-semibold">Remaining OE</th>
                  <th scope="col" className="text-right py-3 font-semibold">Remaining oil</th>
                  <th scope="col" className="text-right py-3 font-semibold">Produced share</th>
                </tr>
              </thead>
              <tbody>
                {opportunityRows.map((row, index) => (
                  <tr
                    key={S(row.field_name)}
                    className="border-b border-gray-200"
                    style={{
                      backgroundColor: index % 2 === 0 ? "transparent" : "#f0f0f0",
                    }}
                  >
                    <td className="py-3 font-medium">
                      <a
                        href={S(row.fact_page_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex gap-1 items-center"
                        style={{ color: "#0777b3" }}
                      >
                        {S(row.field_name)}
                        <ExternalLink size={12} />
                      </a>
                    </td>
                    <td className="py-3" style={{ color: "#6a6a6a" }}>{S(row.main_area)}</td>
                    <td className="py-3">{S(row.operator_name)}</td>
                    <td className="py-3 text-right">{formatVolume(row.remaining_oe_mill_sm3)}</td>
                    <td className="py-3 text-right">{formatVolume(row.remaining_oil_mill_sm3)}</td>
                    <td className="py-3 text-right">{formatPercent(row.produced_share_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {opportunityQuery.isError ? (
          <QueryError message={opportunityQuery.error?.message || "Table query failed"} />
        ) : null}
      </section>
    </main>
  );
}
