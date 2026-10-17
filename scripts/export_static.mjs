import { copyFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const clientDir = path.join(rootDir, "dist", "client");

async function main() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("export", `${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );

  if (response.status !== 200) {
    throw new Error(`SSR pre-render failed with status ${response.status}`);
  }

  const html = await response.text();
  await mkdir(path.join(clientDir, "data"), { recursive: true });
  await writeFile(path.join(clientDir, "index.html"), html, "utf8");
  await copyFile(
    path.join(rootDir, "public", "data", "dashboard.json"),
    path.join(clientDir, "data", "dashboard.json"),
  );
  console.log(`[export_static] Wrote dist/client/index.html (${html.length} bytes) & synced dist/client/data/dashboard.json`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
