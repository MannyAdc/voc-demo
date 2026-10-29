// The dashboard (specs/002-results-api-dashboard, A7). It reads only this app's own API.
// Data goes into the page with textContent only, never as HTML.
"use strict";

const SVG = "http://www.w3.org/2000/svg";  // the SVG namespace name, not a resource that is loaded

function $(id) { return document.getElementById(id); }
function put(id, text, missing) {
  const el = $(id);
  el.textContent = text;
  if (missing) el.classList.add("missing");
}
function pct(x) { return typeof x === "number" ? (x * 100).toFixed(1) + "%" : "n/a"; }
function num(x) { return typeof x === "number" ? x.toLocaleString("en-AU") : "n/a"; }
function svgEl(name, attrs) {
  const el = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}
function label(svg, x, y, text, anchor) {
  const t = svgEl("text", { x, y, "text-anchor": anchor || "middle" });
  t.textContent = text;
  svg.appendChild(t);
}
async function get(path) {
  const response = await fetch(path);
  if (!response.ok) return null;
  return response.json();
}

function headToHead(f) {
  put("llm-acc", pct(f.llm.reweighted_accuracy)); put("tf-acc", pct(f.tfidf.reweighted_accuracy));
  put("llm-prec", pct(f.llm.precision)); put("tf-prec", pct(f.tfidf.precision));
  put("llm-cov", pct(f.llm.coverage)); put("tf-cov", pct(f.tfidf.coverage));
  put("llm-f1", (f.llm.macro_f1 ?? 0).toFixed(3)); put("tf-f1", (f.tfidf.macro_f1 ?? 0).toFixed(3));
  const [low, high] = f.interval;
  put("verdict", "Development verdict: " + (f.verdict || "none") + ". " + f.complaints + " complaints, "
      + f.resamples + " paired bootstrap resamples.");
  drawInterval(f.difference, low, high);
  const who = $("who");
  const names = { both: "both right", only_llm: "only the LLM", only_tfidf: "only TF-IDF", neither: "neither" };
  for (const key of ["both", "only_llm", "only_tfidf", "neither"]) {
    const cell = document.createElement("div");
    const b = document.createElement("b"); b.textContent = num(f.who_was_right[key]);
    const s = document.createElement("span"); s.textContent = names[key];
    cell.append(b, s); who.appendChild(cell);
  }
  drawCurve(f.precision_coverage);
  put("llm-cost", f.llm.cost_per_1000_usd ? "$" + f.llm.cost_per_1000_usd : "n/a");
  put("tf-cost", "$0 (no API call)");
  if (typeof f.llm.seconds_per_1000_complaints === "number") {
    put("llm-time", f.llm.seconds_per_1000_complaints + " s");
  } else {
    put("llm-time", "not measured", true);
    put("speed-note", "LLM time per 1,000 is given only for a finished run where every call was live. "
        + "This run: " + (f.llm.no_time_per_1000_because || "no reason given") + ".");
  }
  put("tf-time", typeof f.tfidf.seconds_per_1000_complaints === "number"
      ? f.tfidf.seconds_per_1000_complaints + " s" : "n/a");
}

function drawInterval(diff, low, high) {
  // The 95 percent interval of the difference, in points, with zero marked. The claim needs it all above zero.
  const svg = $("interval");
  const span = Math.max(Math.abs(low), Math.abs(high), 0.01) * 1.25;
  const x = (v) => 160 + (v / span) * 145;
  const pts = (v) => (v >= 0 ? "+" : "") + (v * 100).toFixed(1);
  svg.appendChild(svgEl("line", { x1: 10, y1: 45, x2: 310, y2: 45, class: "axis" }));
  svg.appendChild(svgEl("line", { x1: x(0), y1: 25, x2: x(0), y2: 65, class: "zero" }));
  svg.appendChild(svgEl("line", { x1: x(low), y1: 45, x2: x(high), y2: 45, class: "ci" }));
  svg.appendChild(svgEl("circle", { cx: x(diff), cy: 45, r: 6, class: "llm" }));
  label(svg, x(diff), 18, pts(diff) + " points");
  label(svg, x(low), 82, pts(low)); label(svg, x(high), 82, pts(high));
  label(svg, x(0), 82, "0");
}

function drawCurve(pc) {
  const svg = $("curve");
  // The precision axis starts at 50 percent, and says so, so the two methods can be told apart.
  const floor = 0.5;
  const x = (c) => 34 + c * 276, y = (p) => 180 - ((Math.max(p, floor) - floor) / (1 - floor)) * 165;
  svg.appendChild(svgEl("line", { x1: 34, y1: 180, x2: 310, y2: 180, class: "axis" }));
  svg.appendChild(svgEl("line", { x1: 34, y1: 15, x2: 34, y2: 180, class: "axis" }));
  for (const v of [0, 0.5, 1]) label(svg, x(v), 194, pct(v));
  for (const v of [0.5, 0.75, 1]) label(svg, 28, y(v) + 3, pct(v), "end");
  const points = (pc.tfidf || []).filter((p) => p[0] !== null && p[1] !== null);
  if (points.length) {
    svg.appendChild(svgEl("polyline", { points: points.map((p) => x(p[0]) + "," + y(p[1])).join(" "), class: "tf" }));
    for (const p of points) svg.appendChild(svgEl("circle", { cx: x(p[0]), cy: y(p[1]), r: 2.5, class: "tfdot" }));
  }
  if (pc.llm && pc.llm.length === 2) {
    svg.appendChild(svgEl("circle", { cx: x(pc.llm[0]), cy: y(pc.llm[1]), r: 6, class: "llm" }));
  }
  label(svg, 172, 12, "coverage across, precision up");
}

function safety(run, audit, queue) {
  if (run) {
    put("accepted", num(run.accepted) + " of " + num(run.complaints));
    const reasons = Object.entries(run.quarantine_reasons || {}).map(([r, n]) => r + " " + n).join(", ");
    put("quarantined", num(run.quarantined) + (reasons ? " (" + reasons + ")" : ""));
    const calls = Object.entries(run.calls_by_source || {}).map(([s, n]) => n + " " + s).join(", ");
    put("run-time", (run.run_seconds ?? "n/a") + " s, " + calls);
  }
  if (audit) {
    put("audit-verified", num(audit.verified) + " of " + num(audit.accepted));
    put("audit-exact", num(audit.word_for_word) + " of " + num(audit.verified));
  } else {
    put("audit-verified", "not committed yet", true); put("audit-exact", "not committed yet", true);
  }
  const body = $("queue");
  for (const row of queue || []) {
    const tr = document.createElement("tr");
    for (const key of ["complaint_id", "reason", "proposed_label", "tfidf_label"]) {
      const td = document.createElement("td"); td.textContent = row[key] || ""; tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

function scale(d) {
  put("july", num(d.july_complaints) + " complaints");
  put("pool", num(d.pool) + " narratives");
  put("copies", num(d.copies_removed.exact) + " exact, " + num(d.copies_removed.near) + " near");
  put("categories", num(d.categories));
  put("sets", [d.sets.dev, d.sets.test, d.sets.train].map(num).join(" / "));
}

function versionsTable(rows) {
  const table = $("versions-table");
  if (!rows.length) return;
  const keep = ["Date", "Prompt", "What changed", "Complaints", "LLM accuracy", "TF-IDF accuracy", "Interval",
                "Live cost"];
  const cols = keep.filter((c) => c in rows[0]);
  const head = table.createTHead().insertRow();
  for (const c of cols) { const th = document.createElement("th"); th.textContent = c; head.appendChild(th); }
  const body = table.createTBody();
  for (const r of rows) {
    const tr = body.insertRow();
    for (const c of cols) tr.insertCell().textContent = r[c] ?? "";
  }
}

async function main() {
  const versions = (await get("/api/versions")) || [];
  versionsTable(versions);
  const latest = versions.length ? versions[versions.length - 1].Prompt : "v1";
  const [figures, run, audit, queue, data] = await Promise.all([
    get("/api/eval/" + latest), get("/api/run/" + latest), get("/api/audit/" + latest),
    get("/api/eval/" + latest + "/quarantine"), get("/api/data")]);
  if (figures) headToHead(figures);
  safety(run, audit, queue);
  if (data) scale(data);
}

main();
