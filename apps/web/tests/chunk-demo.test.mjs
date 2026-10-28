import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import { characterCount, defaultOptions, splitStructure, validateOptions } from "../src/features/project/chunk-demo.ts";

const reference = JSON.parse(readFileSync(new URL("./fixtures/chunking-reference.json", import.meta.url), "utf8"));
const runtime = JSON.parse(readFileSync(new URL("../src/features/project/fixtures/chunking-sample.json", import.meta.url), "utf8"));

test("browser sample matches the production-parsed source atoms", () => {
  assert.equal(runtime.chunker_version, reference.chunker_version);
  assert.deepEqual(runtime.blocks, reference.samples[0].blocks);
});

for (const sample of reference.samples) {
  for (const snapshot of sample.cases) {
    const { min_chars, target_chars, max_chars } = snapshot.options;
    test(`Python parity: ${sample.id}, min=${min_chars}, target=${target_chars}, max=${max_chars}`, () => {
      const actual = splitStructure(sample.blocks, snapshot.options).map(({ content, ...chunk }) => ({
        ...chunk,
        characters: characterCount(content),
        sha256: createHash("sha256").update(content).digest("hex"),
      }));
      assert.deepEqual(actual, snapshot.chunks);
    });
  }
}

test("table notes and equation explanations stay in their original atomic units", () => {
  const chunks = splitStructure(runtime.blocks, defaultOptions);
  const table = chunks.find(chunk => chunk.content.includes("| 原支付渠道 |"));
  assert.ok(table.content.includes("注1："));
  assert.ok(table.content.includes("注2："));
  assert.equal(table.oversized_atom, true);
  const formula = chunks.find(chunk => chunk.content.includes("\\frac"));
  assert.ok(formula.content.includes("式中，"));
  const ids = chunks.flatMap(chunk => chunk.block_ids);
  assert.deepEqual(ids, runtime.blocks.map(block => block.id));
});

test("parameter bounds agree with API constraints", () => {
  assert.equal(validateOptions(defaultOptions), null);
  assert.equal(validateOptions({ min_chars: 0, target_chars: 12000, max_chars: 20000 }), null);
  for (const options of [
    { min_chars: -1, target_chars: 100, max_chars: 100 },
    { min_chars: 12001, target_chars: 12000, max_chars: 20000 },
    { min_chars: 0, target_chars: 99, max_chars: 100 },
    { min_chars: 0, target_chars: 12001, max_chars: 20000 },
    { min_chars: 0, target_chars: 100, max_chars: 20001 },
    { min_chars: 101, target_chars: 100, max_chars: 100 },
    { min_chars: 0, target_chars: 101, max_chars: 100 },
    { min_chars: NaN, target_chars: 240, max_chars: 240 },
    { min_chars: 0, target_chars: 100.5, max_chars: 240 },
  ]) {
    assert.ok(validateOptions(options));
    assert.throws(() => splitStructure(runtime.blocks, options));
  }
});
