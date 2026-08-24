import { pathToFileURL } from "node:url";
import path from "node:path";

const ws = process.argv[2] || ".";
const { slugify } = await import(pathToFileURL(path.join(ws, "slugify.mjs")));

const cases = [
  ["Hello World", "hello-world"],
  ["  Already-Slugged  ", "already-slugged"],
  ["Crème Brûlée", "creme-brulee"],
  ["señor año", "senor-ano"],
  ["foo_bar_baz", "foo-bar-baz"],
  ["What?! Really...", "what-really"],
  ["a  --  b", "a-b"],
  ["--trim--", "trim"],
  ["100% Legit", "100-legit"],
  ["🎉🎉🎉", "n-a"],
  ["", "n-a"],
  ["Ünïted Stätes", "united-states"],
];

let failed = 0;
for (const [input, want] of cases) {
  const got = slugify(input);
  if (got !== want) {
    console.error(`FAIL slugify(${JSON.stringify(input)}) = ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
    failed++;
  }
}
if (failed > 0) process.exit(1);
console.log("PASS");
