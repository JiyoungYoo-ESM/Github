import { createReadStream, createWriteStream } from "node:fs";
import { readFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import { finished } from "node:stream/promises";

import { createExcelStream } from "../lib/server/order-v3-excel.ts";

const [metadataPath, rowsPath, outputPath] = process.argv.slice(2);
if (!metadataPath || !rowsPath || !outputPath) throw new Error("V3 Excel worker paths are required.");

const metadata = JSON.parse(await readFile(metadataPath, "utf8"));
const options = metadata?.options;
if (!options?.result?.scenarios?.[options.scenario] || !Array.isArray(options.skus) || !Array.isArray(options.attentionSkus)) {
  throw new Error("V3 Excel worker metadata is invalid.");
}

const rows = [];
const input = createReadStream(rowsPath, { encoding: "utf8" });
const lines = createInterface({ input, crlfDelay: Infinity });
for await (const line of lines) {
  if (line) rows.push(JSON.parse(line));
}
options.result.scenarios[options.scenario].rows = rows;

const output = createWriteStream(outputPath, { mode: 0o600 });
const generated = createExcelStream(options, new AbortController().signal);
generated.stream.pipe(output);
try {
  await Promise.all([generated.done, finished(output)]);
} catch (error) {
  output.destroy();
  throw error;
}
