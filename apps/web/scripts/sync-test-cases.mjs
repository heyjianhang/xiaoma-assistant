import { mkdir, readFile, writeFile } from "node:fs/promises";

// The acceptance catalog is the single source for UI and manual/CLI testing.
const source = new URL("../../../tests/acceptance/cases.json", import.meta.url);
const directory = new URL("../src/generated/", import.meta.url);
const destination = new URL("test-cases.json", directory);
const contents = await readFile(source, "utf8");
const catalog = JSON.parse(contents);
if (catalog.schema_version !== 2 || !Array.isArray(catalog.cases)) {
  throw new Error("Unsupported acceptance catalog");
}
await mkdir(directory, { recursive: true });
const previous = await readFile(destination, "utf8").catch(error => {
  if (error.code !== "ENOENT") throw error;
  return null;
});
if (contents !== previous) await writeFile(destination, contents);
