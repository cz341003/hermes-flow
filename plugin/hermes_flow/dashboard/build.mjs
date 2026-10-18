import { build } from "esbuild";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname);
const shims = resolve(root, "src/shims");

await build({
  entryPoints: [resolve(root, "src/index.js")],
  outfile: resolve(root, "dist/index.js"),
  bundle: true,
  minify: true,
  format: "iife",
  platform: "browser",
  target: "es2018",
  define: { "process.env.NODE_ENV": '"production"' },
  alias: {
    "react": resolve(shims, "react.js"),
    "react/jsx-runtime": resolve(shims, "jsx-runtime.js"),
    "react-dom": resolve(shims, "react-dom.js"),
  },
  logLevel: "info",
});

const base = await readFile(resolve(root, "dist/style.v1.css"), "utf8");
const extra = await readFile(resolve(root, "src/extra.css"), "utf8");
const xyflow = await readFile(resolve(root, "node_modules/@xyflow/react/dist/style.css"), "utf8");
await writeFile(resolve(root, "dist/style.css"), base + "\n" + xyflow + "\n" + extra, "utf8");
console.log("dashboard bundle built");
