import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import * as arrow from "apache-arrow";

const require = createRequire(import.meta.url);
const version = (name) => JSON.parse(readFileSync(join(dirname(require.resolve(name)), "package.json"), "utf8")).version;
assert.equal(version("@motherduck/wasm-client"), "0.8.1", "Review the compatibility override when changing the SDK");
assert.equal(version("apache-arrow"), "21.2.0", "Review compatibility before changing Arrow");
const sdkRequire = createRequire(require.resolve("@motherduck/wasm-client"));
assert.equal(sdkRequire.resolve("apache-arrow"), require.resolve("apache-arrow"), "The SDK must use the tested Arrow instance");

// The pinned SDK references Worker during import. This check never starts WASM,
// authenticates, or queries an account. It injects the IPC transport into the
// SDK's constructor, which is private in TypeScript but accessible in JavaScript.
globalThis.Worker = class { constructor() { throw new Error("Unexpected worker initialization"); } };
const { MDConnection } = await import("@motherduck/wasm-client");
const fixture = JSON.parse(readFileSync(new URL("./arrow17-results.json", import.meta.url), "utf8"));
const ipc = Buffer.from(fixture.ipc, "base64");

function normalize(value) {
  if (typeof value === "bigint") return { $bigint: String(value) };
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(normalize);
  if (ArrayBuffer.isView(value)) return Array.from(value, normalize);
  return {
    display: String(value),
    fields: Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalize(item)])),
  };
}

function canonical(data) {
  return {
    columns: data.columnNames(),
    types: Array.from({ length: data.columnCount }, (_, i) => String(data.columnType(i))),
    rows: data.toRows().map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, normalize(value)]))),
  };
}

const client = new MDConnection({}, Promise.resolve({
  send: async () => arrow.RecordBatchReader.from((async function* () {
    // Split the IPC across arbitrary boundaries, as a worker stream can do.
    for (let i = 0; i < ipc.length; i += 127) yield ipc.subarray(i, i + 127);
  })()),
}));
const materialized = await client.safeEvaluateQuery("fixture");
if (materialized.status === "error") throw materialized.err;
assert.equal(materialized.result.data.rowCount, 5);
assert.deepEqual(canonical(materialized.result.data), fixture.expected);

const streaming = await client.safeEvaluateStreamingQuery("fixture");
if (streaming.status === "error") throw streaming.err;
await streaming.result.dataReader.readAll();
assert.deepEqual(canonical(streaming.result.dataReader), fixture.expected);

const scalar = new MDConnection({}, Promise.resolve({
  send: async () => arrow.RecordBatchReader.from(arrow.tableToIPC(arrow.tableFromArrays({ value: ["single-value"] }), "stream")),
}));
const single = await scalar.safeEvaluateQuery("fixture");
if (single.status === "error") throw single.err;
assert.equal(single.result.data.singleValue(), "single-value");

const empty = new MDConnection({}, Promise.resolve({
  send: async () => arrow.RecordBatchReader.from(arrow.tableToIPC(new arrow.Table({ value: arrow.vectorFromArray([], new arrow.Utf8()) }), "stream")),
}));
const noRows = await empty.safeEvaluateQuery("fixture");
if (noRows.status === "error") throw noRows.err;
assert.equal(noRows.result.data.rowCount, 0);
assert.deepEqual(noRows.result.data.toRows(), []);
console.log("Arrow 21 compatibility passed: 14 types, lossless fields, two batches, streaming, scalar and empty reads");
