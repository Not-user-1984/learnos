/** Копирует ассеты pdf.js (воркер, cmaps для кириллицы, стандартные шрифты)
 *  в public/pdfjs/ — вызывается перед dev/build, в git не попадает. */

import { cpSync, mkdirSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const src = join(root, "node_modules", "pdfjs-dist");
const dst = join(root, "public", "pdfjs");

rmSync(dst, { recursive: true, force: true });
if (!existsSync(src)) {
  console.error("pdfjs-dist не установлен: npm install");
  process.exit(1);
}
mkdirSync(dst, { recursive: true });
cpSync(join(src, "build", "pdf.worker.min.mjs"), join(dst, "pdf.worker.min.mjs"));
cpSync(join(src, "cmaps"), join(dst, "cmaps"), { recursive: true });
cpSync(join(src, "standard_fonts"), join(dst, "standard_fonts"), { recursive: true });
console.log("pdfjs assets → public/pdfjs (воркер, cmaps, standard_fonts)");
