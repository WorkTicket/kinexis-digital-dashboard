/**
 * Minimal foundation smoke: stage glossary + shell nav constants load.
 * Full Playwright walk lives in scripts/walk-app.mjs (needs running app).
 *
 * Run: node scripts/smoke-stages.cjs
 */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const required = [
  "frontend/lib/glossary.ts",
  "frontend/components/ClientWorkspace.tsx",
  "frontend/components/LoopStepper.tsx",
  "frontend/components/shell/OfflineBanner.tsx",
  "frontend/public/logo.svg",
];

let failed = 0;
for (const rel of required) {
  const p = path.join(root, rel);
  if (!fs.existsSync(p)) {
    console.error("MISSING", rel);
    failed += 1;
    continue;
  }
  const text = fs.readFileSync(p, "utf8");
  if (rel.endsWith("logo.svg") && /#0[Bb]6[Ee]5[Ff]|#1[Aa]8[Ff]7[Aa]/.test(text)) {
    console.error("FAIL logo still teal", rel);
    failed += 1;
  }
  if (rel.includes("OfflineBanner") && !text.includes("onBackendUnavailable")) {
    console.error("FAIL offline banner missing backend IPC", rel);
    failed += 1;
  }
  if (rel.includes("glossary") && text.includes("Surface what's really happening")) {
    console.error("FAIL glossary still has long essays", rel);
    failed += 1;
  }
  console.log("ok", rel);
}

const componentsDir = path.join(root, "frontend", "components");
function walk(dir) {
  if (!fs.existsSync(dir)) {
    console.warn("skip missing dir", path.relative(root, dir));
    return;
  }
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) walk(p);
    else if (/\.(tsx|ts|css)$/.test(name)) {
      const t = fs.readFileSync(p, "utf8");
      if (/text-\[(?:9|10)px\]/.test(t)) {
        console.error("FAIL micro-type", path.relative(root, p));
        failed += 1;
      }
    }
  }
}
walk(componentsDir);

if (failed) {
  console.error(`\nSmoke failed: ${failed} issue(s)`);
  process.exit(1);
}
console.log("\nFoundation smoke checks passed.");
