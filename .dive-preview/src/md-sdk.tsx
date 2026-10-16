/**
 * Local preview shim for @motherduck/react-sql-query. It exports exactly the production Dive
 * runtime's v1 API, so a Dive that imports anything else fails the preview build as it would
 * fail in MotherDuck.
 */
export {
  useSQLQuery,
  useExport,
  useDiveState,
  useRunFlight,
  useFlightRun,
  quoteSqlIdentifier,
  quoteSqlString,
} from "./md-sdk-runtime";
export type {
  ExportQueryOptions,
  UseSQLQueryResult,
  RunFlightConfig,
  FlightRun,
  RunFlightStatus,
  UseRunFlightOptions,
  UseRunFlightResult,
  FlightRunStatus,
  FlightRunState,
  UseFlightRunOptions,
  UseFlightRunResult,
} from "./md-sdk-runtime";
