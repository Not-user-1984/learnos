/** Снимок OpenAPI-схемы ядра: npm run gen:api (R-25 — упоминание было, скрипта не было).
 *
 * Кладёт актуальную схему в src/lib/api-schema.json — источник правды для ручных
 * типов src/lib/types.ts и для ревью рассинхрона REST ↔ веб.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const base = process.env.LEARNOS_API_URL ?? "http://localhost:8765";
const res = await fetch(`${base}/openapi.json`);
if (!res.ok) {
  console.error(`ядро недоступно (${res.status}) — подними сервер или задай LEARNOS_API_URL`);
  process.exit(1);
}
const schema = await res.json();
const out = resolve(dirname(fileURLToPath(import.meta.url)), "../src/lib/api-schema.json");
await mkdir(dirname(out), { recursive: true });
await writeFile(out, JSON.stringify(schema, null, 2) + "\n", "utf8");
console.log(`ok: ${Object.keys(schema.paths ?? {}).length} путей → src/lib/api-schema.json`);
