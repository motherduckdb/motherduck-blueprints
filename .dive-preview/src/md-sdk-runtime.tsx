/**
 * Local Vite preview runtime behind the @motherduck/react-sql-query shim (md-sdk.tsx).
 * Dives see only what md-sdk.tsx re-exports, the production v1 API. The preview host
 * (main.tsx) also uses MotherDuckSDKProvider and useConnectionStatus from this file.
 */
import { MDConnection } from "@motherduck/wasm-client";
import type { DuckDBRow } from "@motherduck/wasm-client";
import { keepPreviousData, notifyManager, QueryClient, QueryObserver } from "@tanstack/query-core";
import type {
  QueryFunctionContext, QueryKey, QueryObserverOptions, QueryObserverResult,
} from "@tanstack/query-core";
import {
  createContext, useContext, useEffect, useMemo, useRef, useState,
  useCallback, useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";

// ── Types ──────────────────────────────────────────────────────────

// Production's useSQLQuery is backed by @tanstack/query-core (TanStack Query v5), and so is this one.
type QueryStatus = "pending" | "error" | "success";

type ConnectionState =
  | { status: "idle" }
  | { status: "connecting" }
  | { status: "connected"; connection: MDConnection }
  | { status: "error"; error: Error };

export type RequiredDatabase = {
  alias: string;
  path?: string;
  shareName?: string;
  type?: "share" | "database";
};

export type ExportQueryOptions = {
  format: "csv" | "json" | "parquet" | "xlsx";
  title?: string;
  filename?: string;
  sheetName?: string;
  // Format-specific settings are accepted for API compatibility; the saved Dive applies them.
  [setting: string]: unknown;
};

export type UseSQLQueryResult<TData = readonly DuckDBRow[]> = {
  data: TData | undefined;
  /**
   * Kept for older Dives: true while connecting and during every fetch, including background
   * refetches. Unlike TanStack's isLoading, it is not limited to the first load; use isPending for that.
   */
  isLoading: boolean;
  /** True until the query has data: first load, connecting, or disabled before it has data. */
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  /** True while data holds the previous SQL's rows (or placeholderData) as the new SQL loads. */
  isPlaceholderData: boolean;
  /** True while a fetch is in flight, including a re-run after the SQL changes or refetch(). */
  isFetching: boolean;
  error: Error | null;
  /** Re-runs the query, cancelling a run in flight. Does nothing while the query is disabled. */
  refetch: () => void;
  exportAs: (options: ExportQueryOptions) => Promise<void>;
  status: QueryStatus;
};

// The saved Dive runtime generates and downloads export files. Locally, log the request instead.
async function simulateLocalExport(sql: string, options: ExportQueryOptions): Promise<void> {
  const filename = options.filename || options.title || "export";
  console.info(`Dive export requested in local preview: ${filename}.${options.format}`, { sql, options });
}

type UseSQLQueryOptions<TData = readonly DuckDBRow[]> = {
  enabled?: boolean;
  select?: (data: readonly DuckDBRow[]) => TData;
  /** Raw rows to use before the query has run (considered fresh). They are passed through select. */
  initialData?: readonly DuckDBRow[];
  /**
   * Raw rows to show while loading, or a function of the previous rows. They are passed through select.
   * Defaults to keeping the previous rows; pass () => undefined to show no data while new SQL loads.
   */
  placeholderData?:
    | readonly DuckDBRow[]
    | ((previousData: readonly DuckDBRow[] | undefined) => readonly DuckDBRow[] | undefined);
};

// ── Query client (the same @tanstack/query-core setup as production) ──

type SQLQueryKey = readonly ["sql-query", sql: string];

// No retries, no refetch on focus or reconnect, and a result is dropped once no hook uses its SQL.
function createSQLQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 0,
        staleTime: 0,
        gcTime: 0,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        networkMode: "always",
      },
    },
  });
}

function createSQLQueryFn(getConnection: () => MDConnection | null) {
  return async (ctx: QueryFunctionContext<SQLQueryKey>): Promise<readonly DuckDBRow[]> => {
    const [, sql] = ctx.queryKey;
    const connection = getConnection();
    if (!connection) throw new Error("No active MotherDuck connection.");
    if (ctx.signal.aborted) throw new DOMException("Aborted", "AbortError");
    // A cancelled query still runs to completion in DuckDB; its result is ignored.
    const result = await connection.safeEvaluateQuery(sql);
    if (ctx.signal.aborted) throw new DOMException("Aborted", "AbortError");
    if (result.status === "error") throw result.err;
    return result.result.data.toRows();
  };
}

// A thin React binding over QueryObserver, as in production: useSyncExternalStore makes every state
// transition visible, and getOptimisticResult gives the result for this render's options.
function useQueryCoreObserver<TQueryFnData, TError, TData, TQueryKey extends QueryKey = QueryKey>(
  client: QueryClient,
  options: QueryObserverOptions<TQueryFnData, TError, TData, TQueryFnData, TQueryKey>,
): QueryObserverResult<TData, TError> {
  const defaultedOptions = useMemo(() => {
    const defaulted = client.defaultQueryOptions(options);
    defaulted._optimisticResults = "optimistic";
    return defaulted;
  }, [client, options]);

  const observerRef = useRef<QueryObserver<TQueryFnData, TError, TData, TQueryFnData, TQueryKey> | null>(null);
  if (!observerRef.current) observerRef.current = new QueryObserver(client, defaultedOptions);
  const observer = observerRef.current;

  const result = observer.getOptimisticResult(defaultedOptions);

  const subscribe = useCallback((onStoreChange: () => void) => {
    const unsubscribe = observer.subscribe(notifyManager.batchCalls(onStoreChange));
    // The observer may have changed between rendering and subscribing.
    observer.updateResult();
    return unsubscribe;
  }, [observer]);
  const getSnapshot = useCallback(() => observer.getCurrentResult(), [observer]);
  useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    observer.setOptions(defaultedOptions);
  }, [observer, defaultedOptions]);

  return result;
}

// ── Provider ───────────────────────────────────────────────────────

/**
 * Which Flights the host lets the Dive run. Production allows "any" for every signed-in viewer and "none"
 * in embeds; MotherDuck then runs a Flight only for its owner or a user with a run grant on it.
 */
export type AllowedFlights = "none" | "any" | readonly string[];

type ContextValue = { state: ConnectionState; allowedFlights: AllowedFlights; queryClient: QueryClient };
const SDKContext = createContext<ContextValue | null>(null);

/** Single-quotes a SQL string literal, escaping contained single quotes. */
export function quoteSqlString(value: string) {
  return `'${value.replace(/'/g, "''")}'`;
}

/** Double-quotes a SQL identifier, escaping contained double quotes. */
export function quoteSqlIdentifier(value: string) {
  return `"${value.replace(/"/g, '""')}"`;
}

const sqlString = quoteSqlString;
const sqlIdentifier = quoteSqlIdentifier;

async function resolveDatabasePath(connection: MDConnection, database: RequiredDatabase) {
  if (database.path) return database.path;
  if (!database.shareName) {
    throw new Error(`Required database ${database.alias} must declare path or shareName`);
  }

  // Shares you own come first; a share created by the CI service account is shared with you instead.
  const name = sqlString(database.shareName);
  for (const sql of [
    `SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = ${name}`,
    `SELECT url FROM MD_INFORMATION_SCHEMA.SHARED_WITH_ME WHERE name = ${name}`,
  ]) {
    const result = await connection.safeEvaluateQuery(sql);
    if (result.status === "error") throw result.err;
    const urls = result.result.data.toRows().map((row) => row.url).filter((url) => typeof url === "string" && url);
    if (urls.length > 1) {
      throw new Error(
        `Several shares named ${database.shareName} are shared with you. ` +
          `Set path to the share URL in REQUIRED_DATABASES for ${database.alias}.`,
      );
    }
    if (urls.length === 1) return String(urls[0]);
  }
  throw new Error(
    `Could not find share ${database.shareName}, which ${database.alias} requires, among the shares you own ` +
      "or that are shared with you. Deploy it first, or check that the share name and your token's user are correct.",
  );
}

async function attachRequiredDatabases(
  connection: MDConnection,
  requiredDatabases: readonly RequiredDatabase[],
) {
  for (const database of requiredDatabases) {
    const path = await resolveDatabasePath(connection, database);
    const result = await connection.safeEvaluateQuery(
      `ATTACH IF NOT EXISTS ${sqlString(path)} AS ${sqlIdentifier(database.alias)} (READ_ONLY)`,
    );
    if (result.status === "error") throw result.err;
  }
}

function useSDKContext() {
  const ctx = useContext(SDKContext);
  if (!ctx) throw new Error("Must be used within MotherDuckSDKProvider");
  return ctx;
}

const CONNECT_TIMEOUT_MS = 60_000;

export function MotherDuckSDKProvider(
  {
    token,
    requiredDatabases,
    allowedFlights = "none",
    children,
  }: {
    token: string;
    requiredDatabases: readonly RequiredDatabase[];
    allowedFlights?: AllowedFlights;
    children: ReactNode;
  },
) {
  const [state, setState] = useState<ConnectionState>({ status: "idle" });

  // One query cache per provider, as in production. Hooks that run the same SQL share a result.
  const queryClientRef = useRef<QueryClient | null>(null);
  if (queryClientRef.current === null) queryClientRef.current = createSQLQueryClient();
  const queryClient = queryClientRef.current;
  useEffect(() => () => queryClient.clear(), [queryClient]);

  useEffect(() => {
    if (!token) { setState({ status: "idle" }); return; }
    let cancelled = false;
    let conn: MDConnection | null = null;
    (async () => {
      setState({ status: "connecting" });
      try {
        // Like production, a Dive with required databases sees only those, so a share alias
        // cannot collide with one of the viewer's own databases.
        conn = MDConnection.create({
          mdToken: token,
          useDuckDBWasmCOI: false,
          ...(requiredDatabases.length > 0 && { attachMode: "single" as const, skipWelcomePack: true }),
        });
        const connection = conn;
        // A blocked network or a failed worker never settles, so give up instead of spinning forever.
        let timer: ReturnType<typeof setTimeout> | undefined;
        const timeout = new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(new Error(
            `No response from MotherDuck after ${CONNECT_TIMEOUT_MS / 1000} seconds. ` +
              "Check your network, proxy, or VPN, and the browser console for worker errors.",
          )), CONNECT_TIMEOUT_MS);
        });
        try {
          await Promise.race([
            (async () => {
              await connection.isInitialized();
              await attachRequiredDatabases(connection, requiredDatabases);
            })(),
            timeout,
          ]);
        } finally {
          clearTimeout(timer);
        }
        if (!cancelled) setState({ status: "connected", connection: conn });
      } catch (err) {
        if (!cancelled) setState({
          status: "error",
          error: err instanceof Error ? err : new Error(String(err)),
        });
      }
    })();
    return () => { cancelled = true; conn?.close(); };
  }, [token, requiredDatabases]);

  const value = useMemo(() => ({ state, allowedFlights, queryClient }), [state, allowedFlights, queryClient]);
  return <SDKContext.Provider value={value}>{children}</SDKContext.Provider>;
}

// ── useSQLQuery ────────────────────────────────────────────────────

export function useSQLQuery<TData = readonly DuckDBRow[]>(
  sql: string,
  options?: UseSQLQueryOptions<TData>,
): UseSQLQueryResult<TData> {
  const { state: connState, queryClient } = useSDKContext();
  const enabled = (options?.enabled ?? true) && connState.status === "connected";
  const queryKey = useMemo<SQLQueryKey>(() => ["sql-query", sql], [sql]);

  // Like production, the previous rows stay visible while new SQL loads unless the Dive sets
  // placeholderData. select keeps the caller's identity, so an inline select re-runs on each render.
  const { select, initialData, placeholderData = keepPreviousData } = options ?? {};
  const observerOptions = useMemo(() => ({
    queryKey,
    queryFn: createSQLQueryFn(() => (connState.status === "connected" ? connState.connection : null)),
    enabled,
    select,
    initialData,
    placeholderData,
  }), [queryKey, enabled, select, initialData, placeholderData, connState]);

  const result = useQueryCoreObserver<readonly DuckDBRow[], Error, TData, SQLQueryKey>(queryClient, observerOptions);

  // Production keeps isLoading for older Dives: true while connecting and during every fetch.
  const isLoading = connState.status === "connecting" || result.isLoading || result.isFetching;

  // The observer lives as long as the hook, so its refetch, and this callback, are stable.
  const observerRefetch = result.refetch;
  const refetch = useCallback(() => {
    if (enabled) observerRefetch();
  }, [enabled, observerRefetch]);

  const exportAs = useCallback(async (exportOptions: ExportQueryOptions) => {
    if (connState.status !== "connected") {
      throw new Error("Cannot export before the MotherDuck connection is ready.");
    }
    await simulateLocalExport(sql, exportOptions);
  }, [connState.status, sql]);

  return {
    data: result.data,
    isLoading,
    isPending: result.isPending,
    isSuccess: result.isSuccess,
    isError: result.isError,
    isPlaceholderData: result.isPlaceholderData,
    isFetching: result.isFetching,
    error: result.error,
    refetch,
    exportAs,
    status: result.status,
  };
}

// ── useExport ──────────────────────────────────────────────────────

export function useExport() {
  const { state } = useSDKContext();
  const exportQuery = useCallback(async ({ sql, ...options }: { sql: string } & ExportQueryOptions) => {
    if (state.status !== "connected") {
      throw new Error("Cannot export before the MotherDuck connection is ready.");
    }
    await simulateLocalExport(sql, options as ExportQueryOptions);
  }, [state.status]);
  return { exportQuery };
}

// ── useDiveState ───────────────────────────────────────────────────

// Production stores the state bag with the shared Dive link. The preview keeps
// it in a URL search parameter so it survives reloads and copied local links.
const DIVE_STATE_PARAM = "diveState";
const DIVE_STATE_MAX_BYTES = 64 * 1024;

type DiveStateBag = Record<string, unknown>;

// DuckDB-Wasm returns BIGINT and HUGEINT values as bigint, which JSON cannot hold.
// Like production, the stored bag writes each bigint as { "$bigint": "<digits>" } and
// reads it back as a bigint, so a reloaded Dive gets the same value and type.
const BIGINT_TAG_KEY = "$bigint";
const BIGINT_DIGITS = /^-?\d+$/;

function diveStateJsonReplacer(_key: string, value: unknown): unknown {
  return typeof value === "bigint" ? { [BIGINT_TAG_KEY]: value.toString() } : value;
}

function diveStateJsonReviver(_key: string, value: unknown): unknown {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    const obj = value as Record<string, unknown>;
    const digits = obj[BIGINT_TAG_KEY];
    if (Object.keys(obj).length === 1 && typeof digits === "string" && BIGINT_DIGITS.test(digits)) {
      return BigInt(digits);
    }
  }
  return value;
}

function readDiveStateBag(): DiveStateBag {
  const raw = new URLSearchParams(window.location.search).get(DIVE_STATE_PARAM);
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw, diveStateJsonReviver);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as DiveStateBag;
    }
  } catch {
    // Fall through: an unreadable bag opens with per-call-site defaults.
  }
  console.warn("Ignoring unreadable Dive state in the URL");
  return {};
}

let diveStateBag: DiveStateBag = readDiveStateBag();
const diveStateListeners = new Set<() => void>();

function notifyDiveState() {
  diveStateListeners.forEach((l) => l());
}

function subscribeDiveState(listener: () => void) {
  diveStateListeners.add(listener);
  return () => { diveStateListeners.delete(listener); };
}

window.addEventListener("popstate", () => {
  diveStateBag = readDiveStateBag();
  notifyDiveState();
});

function assertJsonValue(value: unknown, path: string): void {
  if (value === null) return;
  switch (typeof value) {
    case "string":
    case "boolean":
    case "bigint":
      return;
    case "number":
      if (Number.isFinite(value)) return;
      throw new Error(`useDiveState value at ${path} must be a finite number`);
    case "object": {
      if (Array.isArray(value)) {
        value.forEach((item, i) => assertJsonValue(item, `${path}[${i}]`));
        return;
      }
      const proto = Object.getPrototypeOf(value);
      if (proto !== Object.prototype && proto !== null) {
        throw new Error(
          `useDiveState value at ${path} must be a plain object, array, or primitive`,
        );
      }
      for (const [k, v] of Object.entries(value)) assertJsonValue(v, `${path}.${k}`);
      return;
    }
    default:
      throw new Error(`useDiveState value at ${path} is not JSON-serializable`);
  }
}

function writeDiveStateBag(next: DiveStateBag) {
  const params = new URLSearchParams(window.location.search);
  if (Object.keys(next).length === 0) {
    params.delete(DIVE_STATE_PARAM);
  } else {
    const encoded = JSON.stringify(next, diveStateJsonReplacer);
    if (new TextEncoder().encode(encoded).length > DIVE_STATE_MAX_BYTES) {
      throw new Error("Dive state exceeds the 64 KB limit");
    }
    params.set(DIVE_STATE_PARAM, encoded);
  }
  const search = params.toString();
  const url = `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`;
  window.history.replaceState(window.history.state, "", url);
  diveStateBag = next;
  notifyDiveState();
}

export function useDiveState<T>(
  key: string,
  initialValue: T,
): [T, (value: T | undefined | ((prev: T) => T | undefined)) => void] {
  const stored = useSyncExternalStore(
    subscribeDiveState,
    () => diveStateBag[key],
    () => undefined,
  );
  const value = stored === undefined ? initialValue : (stored as T);

  const initialRef = useRef(initialValue);
  initialRef.current = initialValue;

  const setValue = useCallback(
    (update: T | undefined | ((prev: T) => T | undefined)) => {
      const current = diveStateBag[key];
      const prev = current === undefined ? initialRef.current : (current as T);
      const next = typeof update === "function"
        ? (update as (p: T) => T | undefined)(prev)
        : update;
      if (next === undefined) {
        if (!(key in diveStateBag)) return;
        const { [key]: _removed, ...rest } = diveStateBag;
        writeDiveStateBag(rest);
        return;
      }
      assertJsonValue(next, key);
      writeDiveStateBag({ ...diveStateBag, [key]: next });
    },
    [key],
  );

  return [value, setValue];
}

// ── useConnection / useConnectionStatus ────────────────────────────

export function useConnection(): MDConnection | null {
  const { state } = useSDKContext();
  return state.status === "connected" ? state.connection : null;
}

export function useConnectionStatus() {
  const { state } = useSDKContext();
  return {
    isConnected: state.status === "connected",
    isConnecting: state.status === "connecting",
    error: state.status === "error" ? state.error : null,
  };
}

// ── useRunFlight / useFlightRun ────────────────────────────────────
// Same contract as the production hooks: the SDK builds every statement, run errors stay
// with the caller, and useFlightRun polls fast at first, then slower, for up to an hour.

export type RunFlightConfig = Readonly<Record<string, string>>;
export type FlightRun = { runId: string; runNumber: number };
export type RunFlightStatus = "idle" | "pending" | "success" | "error";

export type UseRunFlightOptions = {
  onSuccess?: (run: FlightRun, config: RunFlightConfig | undefined) => void;
  onError?: (error: Error, config: RunFlightConfig | undefined) => void;
  onSettled?: (run: FlightRun | undefined, error: Error | null, config: RunFlightConfig | undefined) => void;
};

export type UseRunFlightResult = {
  run: (config?: RunFlightConfig) => void;
  runAsync: (config?: RunFlightConfig) => Promise<FlightRun>;
  mutate: (config?: RunFlightConfig) => void;
  mutateAsync: (config?: RunFlightConfig) => Promise<FlightRun>;
  status: RunFlightStatus;
  isIdle: boolean;
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  data: FlightRun | undefined;
  error: Error | null;
  reset: () => void;
};

export type FlightRunStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type FlightRunState = {
  status: FlightRunStatus;
  exitCode: number | null;
  startedAt: Date | null;
  endedAt: Date | null;
};
export type UseFlightRunOptions = { onFinished?: (run: FlightRunState) => void };
export type UseFlightRunResult = {
  status: FlightRunStatus | undefined;
  isFinished: boolean;
  exitCode: number | null;
  startedAt: Date | null;
  endedAt: Date | null;
  isChecking: boolean;
  error: Error | null;
  check: () => void;
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const FLIGHT_RUN_STATUSES = new Set<string>(["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]);
const FINISHED_STATUSES = new Set<string>(["SUCCEEDED", "FAILED", "CANCELLED"]);
const MAX_CHECK_FAILURES = 3;
const MAX_CHECKING_MS = 60 * 60_000;
const LATE_EXIT_CODE_CHECK_MS = 3_000;

function toError(err: unknown) {
  return err instanceof Error ? err : new Error(String(err));
}

function callSafely(callback: () => void) {
  try {
    callback();
  } catch (err) {
    console.error(err);
  }
}

function pollDelayMs(elapsedMs: number) {
  if (elapsedMs < 30_000) return 2_000;
  if (elapsedMs < 5 * 60_000) return 5_000;
  return 30_000;
}

function buildRunFlightSql(flightId: string, config: RunFlightConfig = {}) {
  if (!UUID_RE.test(flightId)) {
    throw new Error(`useRunFlight: the Flight id must be a UUID, got ${JSON.stringify(flightId)}.`);
  }
  if (config === null || typeof config !== "object" || Array.isArray(config)) {
    throw new Error("useRunFlight: config must be an object of strings.");
  }
  const entries = Object.entries(config);
  for (const [key, value] of entries) {
    if (typeof value !== "string") {
      throw new Error(`useRunFlight: config value for '${key}' must be a string; convert it before passing it.`);
    }
  }
  const args = [`flight_id := ${sqlString(flightId.toLowerCase())}::UUID`];
  if (entries.length > 0) {
    const keys = entries.map(([key]) => sqlString(key)).join(", ");
    const values = entries.map(([, value]) => sqlString(value)).join(", ");
    args.push(`config := system.main.map(system.main.list_value(${keys}), system.main.list_value(${values}))`);
  }
  return `CALL system.main.MD_RUN_FLIGHT(${args.join(", ")})`;
}

function buildFlightRunSql(flightId: string, runNumber: number) {
  if (!UUID_RE.test(flightId)) {
    throw new Error(`useFlightRun: the Flight id must be a UUID, got ${JSON.stringify(flightId)}.`);
  }
  if (!Number.isSafeInteger(runNumber) || runNumber < 0) {
    throw new Error(`useFlightRun: the run number must be a whole number, got ${JSON.stringify(runNumber)}.`);
  }
  const epochMs = (column: string) => `CAST(system.main.epoch_ms(${column}) AS DOUBLE) AS ${column}`;
  return `SELECT status, exit_code, ${epochMs("started_at")}, ${epochMs("ended_at")}, ${epochMs("cancelled_at")} `
    + `FROM system.main.MD_GET_FLIGHT_RUN(flight_id := ${sqlString(flightId.toLowerCase())}::UUID, run_number := ${runNumber})`;
}

function assertFlightAllowed(allowed: AllowedFlights, flightId: string) {
  if (allowed === "none") throw new Error("This Dive can't run Flights.");
  if (allowed !== "any" && !allowed.some((id) => id.toLowerCase() === flightId.toLowerCase())) {
    throw new Error(`This Dive can't run Flight ${flightId}.`);
  }
}

const IDLE_RUN = { status: "idle" as RunFlightStatus, data: undefined as FlightRun | undefined, error: null as Error | null };

export function useRunFlight(flightId: string, options?: UseRunFlightOptions): UseRunFlightResult {
  const { state: connectionState, allowedFlights } = useSDKContext();
  const [state, setState] = useState(IDLE_RUN);
  const latestRef = useRef({ connectionState, flightId, allowedFlights, options });
  latestRef.current = { connectionState, flightId, allowedFlights, options };
  const latestCallRef = useRef(0);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const runAsync = useCallback(async (config?: RunFlightConfig): Promise<FlightRun> => {
    const latest = latestRef.current;
    const callId = ++latestCallRef.current;
    const isCurrent = () => mountedRef.current && callId === latestCallRef.current;
    setState({ status: "pending", data: undefined, error: null });
    let run: FlightRun;
    try {
      const sql = buildRunFlightSql(latest.flightId, config);
      assertFlightAllowed(latest.allowedFlights, latest.flightId);
      if (latest.connectionState.status !== "connected") {
        throw new Error("Can't run a Flight before the Dive is connected to MotherDuck.");
      }
      const result = await latest.connectionState.connection.safeEvaluateQuery(sql);
      if (result.status === "error") throw result.err;
      const [row] = result.result.data.toRows();
      if (!row) throw new Error("MD_RUN_FLIGHT returned no run.");
      run = { runId: String(row.run_id), runNumber: Number(row.run_number) };
    } catch (err) {
      const error = toError(err);
      if (isCurrent()) setState({ status: "error", data: undefined, error });
      callSafely(() => latest.options?.onError?.(error, config));
      callSafely(() => latest.options?.onSettled?.(undefined, error, config));
      throw error;
    }
    // The run has started on the server: a throwing callback must not turn it into a failure.
    if (isCurrent()) setState({ status: "success", data: run, error: null });
    callSafely(() => latest.options?.onSuccess?.(run, config));
    callSafely(() => latest.options?.onSettled?.(run, null, config));
    return run;
  }, []);

  const run = useCallback((config?: RunFlightConfig) => {
    runAsync(config).catch(() => {
      // Already in state and passed to onError.
    });
  }, [runAsync]);

  const reset = useCallback(() => {
    latestCallRef.current++;
    setState(IDLE_RUN);
  }, []);

  return useMemo(() => ({
    run, runAsync, mutate: run, mutateAsync: runAsync,
    status: state.status,
    isIdle: state.status === "idle",
    isPending: state.status === "pending",
    isSuccess: state.status === "success",
    isError: state.status === "error",
    data: state.data, error: state.error, reset,
  }), [run, runAsync, reset, state]);
}

type FollowState = {
  /** The run this state describes, so a new run never shows the previous one's status. */
  key: string | null;
  run: (Omit<FlightRunState, "status"> & { status: FlightRunStatus | undefined }) | undefined;
  checking: boolean;
  error: Error | null;
};

export function useFlightRun(
  flightId: string,
  runNumber: number | undefined,
  options?: UseFlightRunOptions,
): UseFlightRunResult {
  const { state: connectionState } = useSDKContext();
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const [follow, setFollow] = useState<FollowState>({ key: null, run: undefined, checking: false, error: null });
  const [checkToken, setCheckToken] = useState(0);
  // onFinished fires once per run, even when check() reads a finished run again.
  const reportedRef = useRef(new Set<string>());
  const inputError = useMemo(() => {
    if (runNumber === undefined) return null;
    try {
      buildFlightRunSql(flightId, runNumber);
      return null;
    } catch (err) {
      return toError(err);
    }
  }, [flightId, runNumber]);
  const connection = connectionState.status === "connected" ? connectionState.connection : null;

  useEffect(() => {
    if (runNumber === undefined || inputError) {
      setFollow({ key: null, run: undefined, checking: false, error: null });
      return;
    }
    const runKey = `${flightId}#${runNumber}`;
    const forRun = (prev: FollowState): FollowState =>
      prev.key === runKey ? prev : { key: runKey, run: undefined, checking: false, error: null };
    if (connectionState.status === "error") {
      setFollow((prev) => ({ ...forRun(prev), checking: false, error: connectionState.error }));
      return;
    }
    setFollow((prev) => ({ ...forRun(prev), checking: true, error: null }));
    if (!connection) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let lateExitCodeChecked = false;
    const startedAt = Date.now();
    const sql = buildFlightRunSql(flightId, runNumber);

    const check = async () => {
      try {
        const result = await connection.safeEvaluateQuery(sql);
        if (result.status === "error") throw result.err;
        const [row] = result.result.data.toRows();
        if (!row) throw new Error(`Run ${runNumber} of Flight ${flightId} wasn't found.`);
        if (stopped) return;
        failures = 0;
        const status = String(row.status);
        const toDate = (value: unknown) => (value == null ? null : new Date(Number(value)));
        const run = {
          status: FLIGHT_RUN_STATUSES.has(status) ? (status as FlightRunStatus) : undefined,
          exitCode: row.exit_code == null ? null : Number(row.exit_code),
          startedAt: toDate(row.started_at),
          endedAt: toDate(row.ended_at) ?? toDate(row.cancelled_at),
        };
        const finished = run.status !== undefined && FINISHED_STATUSES.has(run.status);
        setFollow({ key: runKey, run, checking: !finished, error: null });
        if (finished && !reportedRef.current.has(runKey)) {
          reportedRef.current.add(runKey);
          callSafely(() => optionsRef.current?.onFinished?.(run as FlightRunState));
        }
        if (finished) {
          // The exit code can land just after the final status.
          if (run.exitCode === null && !lateExitCodeChecked) {
            lateExitCodeChecked = true;
            timer = setTimeout(check, LATE_EXIT_CODE_CHECK_MS);
          }
          return;
        }
      } catch (err) {
        if (stopped) return;
        const error = toError(err);
        failures += 1;
        if (/not.?found|does not exist|permission denied/i.test(error.message) || failures >= MAX_CHECK_FAILURES) {
          setFollow((prev) => ({ ...prev, checking: false, error }));
          return;
        }
      }
      const elapsed = Date.now() - startedAt;
      if (elapsed >= MAX_CHECKING_MS) {
        setFollow((prev) => ({ ...prev, checking: false }));
        return;
      }
      timer = setTimeout(check, pollDelayMs(elapsed));
    };
    check();
    return () => {
      stopped = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [flightId, runNumber, inputError, connection, connectionState, checkToken]);

  const check = useCallback(() => setCheckToken((value) => value + 1), []);
  return useMemo(() => ({
    status: follow.run?.status,
    isFinished: follow.run?.status !== undefined && FINISHED_STATUSES.has(follow.run.status),
    exitCode: follow.run?.exitCode ?? null,
    startedAt: follow.run?.startedAt ?? null,
    endedAt: follow.run?.endedAt ?? null,
    isChecking: follow.checking,
    error: inputError ?? follow.error,
    check,
  }), [follow, inputError, check]);
}
