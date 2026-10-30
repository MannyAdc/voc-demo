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
function dec(x) { return typeof x === "number" ? x.toFixed(3) : "n/a"; }
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
  put("llm-f1", dec(f.llm.macro_f1)); put("tf-f1", dec(f.tfidf.macro_f1));
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

function drawInterval(diff, low, high, id) {
  // The 95 percent interval of the difference, in points, with zero marked. The claim needs it all above zero.
  const svg = $(id || "interval");
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

function points(v) { return typeof v === "number" ? (v >= 0 ? "+" : "") + (v * 100).toFixed(1) : "n/a"; }
function round3(v) { return typeof v === "number" ? Math.round(v * 1000) : null; }

function noVerdict(text) {
  // No logged test run: a neutral card, with no figures and no claim that a run exists.
  const card = $("verdict-h").closest("section");
  card.classList.remove("has-verdict");
  $("verdict-body").hidden = true; $("per-product-block").hidden = true;
  put("verdict-note", "");
  put("test-verdict", text, true);
}

function testVerdict(t) {
  // The claim's verdict, from the single logged test run. Not a tuning figure.
  const words = { beats: "The LLM beats TF-IDF", inconclusive: "Inconclusive", does_not_beat: "The LLM does not beat TF-IDF" };
  const [low, high] = t.interval.length === 2 ? t.interval : [null, null];
  const pts = points;
  $("verdict-h").closest("section").classList.add("has-verdict");
  put("verdict-note", "The test set was scored once, after its run was logged in runs/TEST_RUNS.md.");
  if (t.verdict !== "beats") $("test-verdict").classList.add("not-beats");
  put("test-verdict", (words[t.verdict] || "No verdict") + ": " + pts(t.difference) + " points, 95% interval "
      + pts(low) + " to " + pts(high) + " points, on " + num(t.complaints) + " test complaints.");
  put("t-llm-acc", pct(t.llm.reweighted_accuracy)); put("t-tf-acc", pct(t.tfidf.reweighted_accuracy));
  put("t-llm-prec", pct(t.llm.precision)); put("t-tf-prec", pct(t.tfidf.precision));
  put("t-llm-cov", pct(t.llm.coverage)); put("t-tf-cov", pct(t.tfidf.coverage));
  put("t-llm-cost", t.llm.cost_per_1000_usd ? "$" + t.llm.cost_per_1000_usd : "n/a");
  put("t-tf-cost", "$0 (no API call)");
  put("t-llm-time", typeof t.llm.seconds_per_1000_complaints === "number"
      ? t.llm.seconds_per_1000_complaints + " s (one call at a time)" : "not measured");
  put("t-tf-time", typeof t.tfidf.seconds_per_1000_complaints === "number"
      ? t.tfidf.seconds_per_1000_complaints + " s (labelling only)" : "n/a");
  if ([t.difference, low, high].every((v) => typeof v === "number")) drawInterval(t.difference, low, high, "test-interval");
  const r = t.run || {};
  const reasons = Object.entries(r.quarantine_reasons || {}).map(([k, n]) => k + " " + n).join(", ");
  put("test-run", num(r.accepted) + " accepted, " + num(r.quarantined) + " quarantined"
      + (reasons ? " (" + reasons + ")" : "") + ". " + num(r.input_tokens) + " input and " + num(r.output_tokens)
      + " output tokens, " + (r.live_cost_usd ? "$" + r.live_cost_usd : "cost n/a") + ", " + (r.run_seconds ?? "n/a") + " s.");
  put("per-note", "In this table " + t.per_category.note + ".");
  const body = $("per-product");
  const rows = Object.entries(t.per_category.categories).sort((a, b) => b[1].complaints - a[1].complaints);
  for (const [name, c] of rows) {
    const tr = body.insertRow();
    tr.insertCell().textContent = name;
    tr.insertCell().textContent = num(c.complaints);
    if (c.too_few_to_judge) {
      const td = tr.insertCell(); td.colSpan = 2; td.textContent = "too few to judge (under 30)";
    } else {
      const llm = tr.insertCell(), tf = tr.insertCell();
      llm.textContent = dec(c.llm_f1); tf.textContent = dec(c.tfidf_f1);
      // Compared as shown, at 3 decimals, so a tie on screen is not marked as a win (Mortgage: 0.910 and 0.910).
      // Only when both exist, so a missing figure is never marked as the better one.
      const a = round3(c.llm_f1), b = round3(c.tfidf_f1);
      if (a !== null && b !== null && a > b) llm.classList.add("better");
      if (a !== null && b !== null && b > a) tf.classList.add("better");
    }
  }
}

function drawCurve(pc) {
  const svg = $("curve");
  // The precision axis starts at 50 percent, so the two methods can be told apart. The legend says so.
  // A point below the axis is drawn on it as a hollow ring, never as if it were at 50 percent.
  const floor = 0.5;
  const x = (c) => 34 + c * 276, y = (p) => 180 - ((Math.max(p, floor) - floor) / (1 - floor)) * 165;
  const dot = (c, p, r, cls) => svgEl("circle", { cx: x(c), cy: y(p), r, class: p < floor ? "clip" : cls });
  svg.appendChild(svgEl("line", { x1: 34, y1: 180, x2: 310, y2: 180, class: "axis" }));
  svg.appendChild(svgEl("line", { x1: 34, y1: 15, x2: 34, y2: 180, class: "axis" }));
  for (const v of [0, 0.5, 1]) label(svg, x(v), 194, pct(v));
  for (const v of [0.5, 0.75, 1]) label(svg, 28, y(v) + 3, pct(v), "end");
  const points = (pc.tfidf || []).filter((p) => p[0] !== null && p[1] !== null);
  if (points.length) {
    svg.appendChild(svgEl("polyline", { points: points.map((p) => x(p[0]) + "," + y(p[1])).join(" "), class: "tf" }));
    for (const p of points) svg.appendChild(dot(p[0], p[1], 2.5, "tfdot"));
  }
  if (pc.llm && pc.llm.length === 2 && pc.llm[0] !== null && pc.llm[1] !== null) {
    svg.appendChild(dot(pc.llm[0], pc.llm[1], 6, "llm"));
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
  const dev = versions.filter((r) => r.Set === "dev");
  const latest = dev.length ? dev[dev.length - 1].Prompt : "v1";
  // Review of #44: the test card asks which version has a logged test run, not the last development row.
  const logged = ((await get("/api/tested")) || { versions: [] }).versions;
  const testVersion = logged.length ? logged[logged.length - 1] : null;
  const [figures, run, audit, queue, data, tested] = await Promise.all([
    get("/api/eval/" + latest), get("/api/run/" + latest), get("/api/audit/" + latest),
    get("/api/eval/" + latest + "/quarantine"), get("/api/data"),
    testVersion ? get("/api/test/" + testVersion) : Promise.resolve(null)]);
  if (tested) testVerdict(tested);
  else noVerdict(testVersion ? "The test results for prompt " + testVersion + " could not be loaded."
                             : "No test run is logged yet, so there is no verdict.");
  if (figures) headToHead(figures);
  safety(run, audit, queue);
  if (data) scale(data);
}

main();
