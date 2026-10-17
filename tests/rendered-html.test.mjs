import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the STMA quant dashboard shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>STMA Macro Signal Observatory<\/title>/i);
  assert.match(html, /Macro Signal Observatory/);
  assert.match(html, /กำลังอ่าน local snapshot/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("generated snapshot has canonical dashboard sections", async () => {
  const raw = await readFile(new URL("../public/data/dashboard.json", import.meta.url), "utf8");
  const data = JSON.parse(raw);
  assert.equal(data.meta.integrity_check, "ok");
  assert.equal(data.meta.dataset_status, "ok");
  assert.equal(data.observations.length, data.meta.canonical_observations);
  assert.equal(data.theme_summary.length, 10);
  assert.equal(data.correlations.length, 100);
  assert.equal("portfolio_signals" in data, false);
  assert.equal("portfolio_signal_count" in data.meta, false);
  assert.match(data.methodology.missing_policy, /never converted to zero/);
  assert.match(data.methodology.api_policy, /no AI/i);
});

test("dashboard source keeps sparse-data visual guardrails", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /มอง sentiment เป็น time-series/);
  assert.match(page, /rollingObserved/);
  assert.match(page, /rollingMentionCoverage/);
  assert.match(page, /dates\.length>45\?"weekly":"daily"/);
  assert.match(page, /Coverage %/);
  assert.match(page, /Evidence\/obs/);
});
