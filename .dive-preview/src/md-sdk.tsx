/**
 * Simplified @motherduck/react-sql-query shim for local Vite preview.
 * Same API as the production dive runtime — useSQLQuery (with exportAs), useExport, useDiveState,
 * useConnection, useConnectionStatus, and MotherDuckSDKProvider.
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

type ContextValue = { state: ConnectionState };
const SDKContext = createContext<ContextValue | null>(null);

function sqlString(value: string) {
  return `'${value.replaceAll("'", "''")}'`;
}

function sqlIdentifier(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

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
    children,
  }: {
    token: string;
    requiredDatabases: readonly RequiredDatabase[];
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

  const value = useMemo(() => ({ state }), [state]);
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
