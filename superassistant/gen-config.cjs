// gen-config.cjs - generates .generated-config.json from config.template.json.
// Secrets come from env vars (never CLI args, which are visible in the process list):
//   GEN_GITHUB_PAT, GEN_CONNECTOR_KEY
// INCLUDE_VERCEL_CONNECTOR=1 keeps the vercel-connector server (off by default, because
// the Vercel deployment may sit behind Vercel Authentication -> 401 kills the proxy).
const fs = require("fs");
const path = require("path");
const dir = __dirname;

let out = fs.readFileSync(path.join(dir, "config.template.json"), "utf8")
  .split("__GITHUB_PAT__").join(process.env.GEN_GITHUB_PAT || "")
  .split("__CONNECTOR_API_KEY__").join(process.env.GEN_CONNECTOR_KEY || "");

const cfg = JSON.parse(out); // validate
if (process.env.INCLUDE_VERCEL_CONNECTOR !== "1") delete cfg.mcpServers["vercel-connector"];
out = JSON.stringify(cfg, null, 2);
fs.writeFileSync(path.join(dir, ".generated-config.json"), out);
JSON.parse(out); // re-validate what was written
console.log("Config OK. Servers: " + Object.keys(cfg.mcpServers).join(", "));
