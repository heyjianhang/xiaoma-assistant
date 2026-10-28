import { cpSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const packageRoot = dirname(require.resolve("pdfjs-dist/package.json"));
const output = fileURLToPath(new URL("../public/pdfjs/", import.meta.url));
mkdirSync(output, { recursive: true });
cpSync(join(packageRoot, "build/pdf.worker.min.mjs"), join(output, "pdf.worker.min.mjs"));
for (const directory of ["cmaps", "standard_fonts", "wasm"]) {
  cpSync(join(packageRoot, directory), join(output, directory), { recursive: true });
}
