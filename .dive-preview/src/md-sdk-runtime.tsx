/**
 * Local Vite preview runtime behind the @motherduck/react-sql-query shim (md-sdk.tsx).
 * Dives see only what md-sdk.tsx re-exports, the production v1 API. The preview host
 * (main.tsx) also uses MotherDuckSDKProvider and useConnectionStatus from this file.
 */
import { MDConnection } from "@motherduck/wasm-client";
import type { DuckDBRow } from "@motherduck/wasm-client";
import {
  createContext, useContext, useEffect, useMemo, useRef, useState,
  useCallback, useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";

// ── Types ──────────────────────────────────────────────────────────

type QueryStatus = "idle" | "loading" | "success" | "error";

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
  isLoading: boolean;
  isSuccess: boolean;
  isError: boolean;
  isPlaceholderData: boolean;
  error: Error | null;
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
  initialData?: TData;
  placeholderData?: TData | ((prev: TData | undefined) => TData | undefined);
};

// ── QueryObserver (external store for useSyncExternalStore) ────────

interface QueryObserverState {
  status: QueryStatus;
  data: readonly DuckDBRow[] | undefined;
  error: Error | undefined;
  hasHadData: boolean;
  lastData: readonly DuckDBRow[] | undefined;
}

class QueryObserver {
  private state: QueryObserverState = {
    status: "idle", data: undefined, error: undefined,
    hasHadData: false, lastData: undefined,
  };
  private listeners = new Set<() => void>();
  private abortController: AbortController | null = null;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  getSnapshot = () => this.state;
  getStatus() { return this.state.status; }

  private setState(updates: Partial<QueryObserverState>) {
    this.state = { ...this.state, ...updates };
    this.listeners.forEach((l) => l());
  }

  async execute(connection: MDConnection, sql: string) {
    this.abortController?.abort();
    this.abortController = new AbortController();
    const { signal } = this.abortController;
    this.setState({ status: "loading", data: undefined, error: undefined });
    try {
      const result = await connection.safeEvaluateQuery(sql);
      if (signal.aborted) return;
      if (result.status === "error") {
        this.setState({ status: "error", error: result.err, data: undefined });
        return;
      }
      const data = result.result.data.toRows();
      this.setState({
        status: "success", data, error: undefined,
        hasHadData: true, lastData: data,
      });
    } catch (err) {
      if (signal.aborted) return;
      this.setState({
        status: "error",
        error: err instanceof Error ? err : new Error(String(err)),
        data: undefined,
      });
    }
  }

  reset() {
    this.abortController?.abort();
    this.abortController = null;
    this.setState({ status: "idle", data: undefined, error: undefined });
  }
  cancel() {
    this.abortController?.abort();
    this.abortController = null;
  }
}

// ── Provider ───────────────────────────────────────────────────────

/** Which Flights the host lets the Dive run. Production allows "any" for the Dive's owner, else "none". */
export type AllowedFlights = "none" | "any" | readonly string[];

type ContextValue = { state: ConnectionState; allowedFlights: AllowedFlights };
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

  const result = await connection.safeEvaluateQuery(
    `SELECT url FROM MD_LIST_DATABASE_SHARES() WHERE name = ${sqlString(database.shareName)}`,
  );
  if (result.status === "error") throw result.err;
  if (result.result.data.rowCount !== 1) {
    throw new Error(`Could not resolve share ${database.shareName}`);
  }
  const url = result.result.data.singleValue();
  if (typeof url !== "string" || !url) {
    throw new Error(`Share ${database.shareName} did not return a valid URL`);
  }
  return url;
}

async function attachRequiredDatabases(
  connection: MDConnection,
  requiredDatabases: readonly RequiredDatabase[],
) {
  for (const database of requiredDatabases) {
    const path = await resolveDatabasePath(connection, database);
    const result = await connection.safeEvaluateQuery(
      `ATTACH IF NOT EXISTS ${sqlString(path)} AS ${sqlIdentifier(database.alias)}`,
    );
    if (result.status === "error") throw result.err;
  }
}

function useSDKContext() {
  const ctx = useContext(SDKContext);
  if (!ctx) throw new Error("Must be used within MotherDuckSDKProvider");
  return ctx;
}

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

  useEffect(() => {
    if (!token) { setState({ status: "idle" }); return; }
    let cancelled = false;
    let conn: MDConnection | null = null;
    (async () => {
      setState({ status: "connecting" });
      try {
        conn = MDConnection.create({ mdToken: token, useDuckDBWasmCOI: false });
        await conn.isInitialized();
        await attachRequiredDatabases(conn, requiredDatabases);
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

  const value = useMemo(() => ({ state, allowedFlights }), [state, allowedFlights]);
  return <SDKContext.Provider value={value}>{children}</SDKContext.Provider>;
}

// ── useSQLQuery ────────────────────────────────────────────────────

export function useSQLQuery<TData = readonly DuckDBRow[]>(
  sql: string,
  options?: UseSQLQueryOptions<TData>,
): UseSQLQueryResult<TData> {
  const { state: connState } = useSDKContext();
  const observerRef = useRef<QueryObserver | null>(null);
  if (!observerRef.current) observerRef.current = new QueryObserver();
  const observer = observerRef.current;

  const snap = useSyncExternalStore(
    observer.subscribe, observer.getSnapshot, observer.getSnapshot,
  );
  const enabled = options?.enabled !== false;

  useEffect(() => {
    if (!enabled || connState.status !== "connected") {
      if (observer.getStatus() !== "idle") observer.reset();
      return;
    }
    observer.execute(connState.connection, sql);
    return () => observer.cancel();
  }, [sql, enabled, connState, observer]);

  const refetch = useCallback(() => {
    if (connState.status === "connected" && enabled) {
      observer.execute(connState.connection, sql);
    }
  }, [observer, connState, enabled, sql]);

  const exportAs = useCallback(async (exportOptions: ExportQueryOptions) => {
    if (connState.status !== "connected") {
      throw new Error("Cannot export before the MotherDuck connection is ready.");
    }
    await simulateLocalExport(sql, exportOptions);
  }, [connState.status, sql]);

  const isLoading = snap.status === "loading" || connState.status === "connecting";
  const rawData = snap.data ?? snap.lastData;

  const transformed = useMemo(() => {
    if (rawData === undefined) return undefined;
    return options?.select
      ? options.select(rawData)
      : (rawData as unknown as TData);
  }, [rawData, options?.select]);

  const { data, isPlaceholderData } = useMemo(() => {
    if (transformed !== undefined)
      return { data: transformed, isPlaceholderData: false };
    if (!snap.hasHadData && options?.initialData !== undefined)
      return { data: options.initialData, isPlaceholderData: false };
    if (isLoading && options?.placeholderData !== undefined) {
      const ph = typeof options.placeholderData === "function"
        ? (options.placeholderData as (p: TData | undefined) => TData | undefined)(transformed)
        : options.placeholderData;
      if (ph !== undefined) return { data: ph, isPlaceholderData: true };
    }
    return { data: undefined, isPlaceholderData: false };
  }, [transformed, snap.hasHadData, options?.initialData, options?.placeholderData, isLoading]);

  return {
    data, isLoading,
    isSuccess: snap.status === "success",
    isError: snap.status === "error",
    isPlaceholderData,
    error: snap.error ?? null,
    refetch, exportAs, status: snap.status,
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

function readDiveStateBag(): DiveStateBag {
  const raw = new URLSearchParams(window.location.search).get(DIVE_STATE_PARAM);
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
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
    const encoded = JSON.stringify(next);
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
