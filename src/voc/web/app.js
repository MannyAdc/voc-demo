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
function pct(x) { return typeof x === "number" ? (x * 100).toFixed(1) + "%" : "not available"; }
function num(x) { return typeof x === "number" ? x.toLocaleString("en-AU") : "not available"; }
function dec(x) { return typeof x === "number" ? x.toFixed(3) : "not available"; }
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
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December"];
function day(text) {
  // "2026-07-01" becomes "1 July 2026", the same on every machine.
  const [y, m, d] = text.split("-").map(Number);
  return d + " " + MONTHS[m - 1] + " " + y;
}

async function get(path) {
  const response = await fetch(path);
  if (!response.ok) return null;
  return response.json();
}

const VERDICT_WORDS = { beats: "the LLM beats TF-IDF", inconclusive: "inconclusive",
                        does_not_beat: "the LLM does not beat TF-IDF" };

function headToHead(f) {
  put("llm-acc", pct(f.llm.reweighted_accuracy)); put("tf-acc", pct(f.tfidf.reweighted_accuracy));
  put("llm-prec", pct(f.llm.precision)); put("tf-prec", pct(f.tfidf.precision));
  put("llm-cov", pct(f.llm.coverage)); put("tf-cov", pct(f.tfidf.coverage));
  put("llm-f1", dec(f.llm.macro_f1)); put("tf-f1", dec(f.tfidf.macro_f1));
  const [low, high] = f.interval.length === 2 ? f.interval : [null, null];
  // Review of #62: the verdict in words, as on the Overview, never the internal code.
  put("verdict", (f.set === "test" ? "Test verdict: " : "Development verdict: ") + (VERDICT_WORDS[f.verdict] || "none")
      + ". " + num(f.complaints) + " complaints, " + num(f.resamples) + " paired bootstrap resamples.");
  if ([f.difference, low, high].every((v) => typeof v === "number")) drawInterval(f.difference, low, high);
  const who = $("who");
  const names = { both: "both right", only_llm: "only the LLM", only_tfidf: "only TF-IDF", neither: "neither" };
  for (const key of ["both", "only_llm", "only_tfidf", "neither"]) {
    const cell = document.createElement("div");
    const b = document.createElement("b"); b.textContent = num(f.who_was_right[key]);
    const s = document.createElement("span"); s.textContent = names[key];
    cell.append(b, s); who.appendChild(cell);
  }
  drawCurve(f.precision_coverage);
}

function developmentHeadToHead() {
  // Review of #62: with no logged test run, the heading, its tag, the banner and the note all say development set.
  const heading = $("h2h"); clear(heading);
  const tag = document.createElement("span"); tag.className = "tag"; tag.textContent = "tuning figure, development set";
  heading.append("Development head to head ", tag);
  put("banner", "No test run is logged yet, so the head to head below is from the development set: tuning figures, "
      + "not a verdict.");
  put("who-note", "Each development complaint, by which method labelled it correctly: both, only one of them, or "
      + "neither. TF-IDF counts as right only on the complaints it answered, its most confident ones. A held-back LLM "
      + "label counts as wrong.");
}

function speedFigures(f) {
  // The Speed panel stays a development figure: its labelling run is the development run.
  put("llm-cost", f.llm.cost_per_1000_usd ? "$" + f.llm.cost_per_1000_usd : "not available");
  put("tf-cost", "$0 (no API call)");
  if (typeof f.llm.seconds_per_1000_complaints === "number") {
    put("llm-time", f.llm.seconds_per_1000_complaints + " seconds");
  } else {
    put("llm-time", "not measured", true);
    put("speed-note", "LLM time per 1,000 is given only for a finished run where every call was live. "
        + "This run: " + (f.llm.no_time_per_1000_because || "no reason given") + ".");
  }
  put("tf-time", typeof f.tfidf.seconds_per_1000_complaints === "number"
      ? f.tfidf.seconds_per_1000_complaints + " seconds" : "not available");
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

function points(v) { return typeof v === "number" ? (v >= 0 ? "+" : "") + (v * 100).toFixed(1) : "not available"; }
function round3(v) { return typeof v === "number" ? Math.round(v * 1000) : null; }

function noVerdict(text) {
  // No logged test run: a neutral card, with no figures and no claim that a run exists.
  const card = $("verdict-h").closest("section");
  card.classList.remove("has-verdict");
  $("verdict-body").hidden = true; $("per-product-block").hidden = true;
  for (const tile of ["tile-complaints", "tile-accuracy", "tile-cost"]) put(tile, "not yet");
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
  put("t-llm-cost", t.llm.cost_per_1000_usd ? "$" + t.llm.cost_per_1000_usd : "not available");
  put("t-tf-cost", "$0 (no API call)");
  put("t-llm-time", typeof t.llm.seconds_per_1000_complaints === "number"
      ? t.llm.seconds_per_1000_complaints + " seconds (one call at a time)" : "not measured");
  put("t-tf-time", typeof t.tfidf.seconds_per_1000_complaints === "number"
      ? t.tfidf.seconds_per_1000_complaints + " seconds (labelling only)" : "not available");
  if ([t.difference, low, high].every((v) => typeof v === "number")) drawInterval(t.difference, low, high, "test-interval");
  const r = t.run || {};
  const reasons = Object.entries(r.quarantine_reasons || {}).map(([k, n]) => (REASONS[k] || REASONS.other) + ": " + n)
    .join(", ");
  put("test-run", num(r.accepted) + " accepted, " + num(r.quarantined) + " quarantined"
      + (reasons ? " (" + reasons + ")" : "") + ". " + num(r.input_tokens) + " input and " + num(r.output_tokens)
      + " output tokens, " + (r.live_cost_usd ? "$" + r.live_cost_usd : "cost not available") + ", " + (typeof r.run_seconds === "number" ? r.run_seconds + " seconds" : "time not available") + ".");
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
  put("tile-complaints", num(t.complaints));
  put("tile-accuracy", pct(t.llm.reweighted_accuracy));
  put("tile-cost", t.llm.cost_per_1000_usd ? "$" + t.llm.cost_per_1000_usd : "not available");
  productBars(rows);
}

function productBars(rows) {
  // One bar per product: its test complaints, with the F1 of the LLM and of TF-IDF. A "!" marks a product where
  // TF-IDF does better at 3 decimals, so the analyst checks those labels before reporting them.
  const list = $("product-bars"); clear(list);
  const most = Math.max(1, ...rows.map(([, c]) => c.complaints));
  for (const [name, c] of rows) {
    const item = document.createElement("li");
    const label = document.createElement("span"); label.className = "bar-name"; label.textContent = name;
    const track = document.createElement("span"); track.className = "bar-track";
    const bar = document.createElement("span"); bar.className = "bar"; bar.style.width = (100 * c.complaints / most) + "%";
    track.appendChild(bar);
    const count = document.createElement("span"); count.className = "bar-count"; count.textContent = num(c.complaints);
    const f1 = document.createElement("span"); f1.className = "bar-f1";
    if (c.too_few_to_judge) {
      f1.textContent = "too few to judge";
    } else {
      const a = round3(c.llm_f1), b = round3(c.tfidf_f1);
      f1.textContent = "LLM " + dec(c.llm_f1) + " / TF-IDF " + dec(c.tfidf_f1);
      if (a !== null && b !== null && b > a) {
        const flag = document.createElement("span"); flag.className = "flag"; flag.textContent = " !";
        flag.title = "TF-IDF does better here: check before you report";
        f1.appendChild(flag);
        item.classList.add("weak");
      }
    }
    item.append(label, track, count, f1);
    list.appendChild(item);
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
    const reasons = Object.entries(run.quarantine_reasons || {}).map(([r, n]) => (REASONS[r] || REASONS.other) + ": " + n)
      .join(", ");
    put("quarantined", num(run.quarantined) + (reasons ? " (" + reasons + ")" : ""));
    const calls = Object.entries(run.calls_by_source || {}).map(([s, n]) => n + " " + s).join(", ");
    put("run-time", (typeof run.run_seconds === "number" ? run.run_seconds + " seconds" : "time not available") + ", " + calls);
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
  put("sets", [d.sets.train, d.sets.dev, d.sets.test].map(num).join(" / "));
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

// The analyst screens (docs/USER.md tasks 2 and 3, docs/WIREFRAMES.md screens 2 and 3).
// The route is in the address after "#", so the browser's Back button works.

let version = "v1";
const REASONS = { quote_not_in_text: "the quoted sentence is not in the text", invalid_label: "the AI named a product not in the list",
  unparseable: "the AI's answer could not be read", quote_too_short: "the quote is too short to show anything",
  quote_empty: "the AI gave no quote", quote_redaction_only: "the quote is only redaction marks",
  no_narrative: "the complaint has no text", boundary_in_text: "the text holds the marker that fences it off from the instructions",
  model_error: "the model call failed", not_run_budget: "not run, because the spend cap was reached", other: "another reason" };
const DECISIONS = { ai_right: "the AI's label is right", word_model_right: "the word-based model is right",
  other_product: "another product fits better", no_product: "it fits no product clearly", correction: "a correction" };
const listState = { product: null, show: "all", page: 1, loaded: null, keepFocus: false };
// Review of #51: each fetch takes a ticket. An answer that arrives after a newer request is dropped, so two quick
// clicks never put one complaint's facts under another's heading.
const latest = { list: 0, complaint: 0, review: 0 };
let reviewLoaded = false;
let currentTab = null;

function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
function link(href, text) { const a = document.createElement("a"); a.href = href; a.textContent = text; return a; }
function status(id, text, kind) {
  const el = $(id); el.textContent = text || ""; el.className = "status" + (kind ? " " + kind : "");
}
const TABS = ["overview", "browse", "review", "measured"];

function showTab(name, withDetail) {
  // One tab at a time. The complaint pane sits beside the Browse or Review list when a complaint is open.
  currentTab = name;
  for (const tab of TABS) $("tab-" + tab).hidden = tab !== name;
  for (const a of document.querySelectorAll("nav.tabs a")) {
    if (a.dataset.tab === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  const detail = $("view-complaint");
  if (withDetail && (name === "browse" || name === "review")) $("tab-" + name).appendChild(detail);
  detail.hidden = !withDetail;
  $("tab-" + name).classList.toggle("with-detail", !!withDetail);
}

function toggleTerm(button) {
  // A (?) note opens in place and closes again. It works with a mouse, the keyboard and a screen reader.
  const note = $(button.getAttribute("aria-controls"));
  const open = button.getAttribute("aria-expanded") !== "true";
  button.setAttribute("aria-expanded", open ? "true" : "false");
  note.hidden = !open;
}
async function fetchJson(path, options) {
  // Returns [data, null] or [null, a short message]. Never shows a raw error to the analyst.
  try {
    const response = await fetch(path, options);
    if (!response.ok) return [null, response.status === 404 ? "not found" : "could not be loaded"];
    return [await response.json(), null];
  } catch (e) { return [null, "could not be loaded"]; }
}

async function reviewCount() {
  const [q] = await fetchJson("/api/review/" + version + "/queue");
  put("tile-waiting", q ? num(q.total - q.reviewed) : "not available");
  $("tab-review-link").textContent = q ? "Review (" + (q.total - q.reviewed) + ")" : "Review";
}

async function listView(product, openId) {
  // The list is fetched again only when the product, the filter or the page changes. Opening a complaint beside
  // it keeps the analyst's place. Paging keeps the focus on the pager.
  if (listState.product !== product) { listState.product = product; listState.page = 1; }
  const keepFocus = listState.keepFocus; listState.keepFocus = false;
  showTab("browse", !!openId);
  if (openId) complaintView(openId);
  const body = $("list-rows");
  $("browse-product").value = product || "";
  if (!product) {
    $("list-h").textContent = "Browse the development complaints";
    clear(body); put("list-note", ""); put("list-page", ""); listState.loaded = null;
    status("list-status", "Choose a product above to see its complaints.");
    $("list-prev").disabled = true; $("list-next").disabled = true;
    $("list-h").focus();
    return;
  }
  $("list-h").textContent = product + ": development complaints";
  if (!openId && !keepFocus) $("list-h").focus();
  const key = [product, listState.show, listState.page].join("|");
  if (listState.loaded === key) return;
  clear(body);
  status("list-status", "Loading...");
  const ticket = ++latest.list;
  const q = new URLSearchParams({ product, show: listState.show, page: listState.page });
  const [d, err] = await fetchJson("/api/review/" + version + "/complaints?" + q);
  if (ticket !== latest.list) return;
  if (!d) { status("list-status", "The complaints " + err + ". Go back and try again.", "error"); return; }
  listState.loaded = key;
  status("list-status", d.total ? "" : "No complaints here for the filter \"" + listState.show + "\".");
  const notes = [];
  if (!d.local) notes.push("The consumer's own choice and the text are available only on the analyst's own machine, so this list groups by the AI's label and the right or wrong filter is empty.");
  if (d.held_back_for_review) notes.push(d.held_back_for_review + " quarantined complaints, across all products, are not listed by product until they are reviewed, so their consumer's own choice stays hidden. They are in the review queue.");
  put("list-note", notes.join(" "));
  for (const r of d.rows) {
    const tr = body.insertRow();
    tr.insertCell().appendChild(link("#/product/" + encodeURIComponent(product) + "/" + encodeURIComponent(r.complaint_id),
                                      r.complaint_id));
    tr.insertCell().textContent = r.ai_label || "(waiting for a person)";
    tr.insertCell().textContent = r.consumer_choice || (d.local ? "hidden until reviewed" : "only on the analyst's machine");
    tr.insertCell().textContent = r.decision === "accepted" ? "found" : (REASONS[r.reason] || "not accepted");
  }
  $("list-page").textContent = "Page " + d.page + " of " + d.pages + ", " + d.total + (d.total === 1 ? " complaint" : " complaints");
  $("list-prev").disabled = d.page <= 1; $("list-next").disabled = d.page >= d.pages;
}

async function complaintView(id) {
  const ticket = ++latest.complaint;
  $("view-complaint").hidden = false;
  $("complaint-h").textContent = "Complaint " + id;
  $("complaint-h").focus();
  for (const k of ["c-ai", "c-check", "c-tfidf", "c-consumer", "c-text-note"]) put(k, "");
  // Review of #61: the box stays hidden while the complaint loads, or if it fails to load.
  clear($("c-text")); $("c-text").hidden = true; $("decision").hidden = true; status("d-status", "");
  status("complaint-status", "Loading...");
  const [c, err] = await fetchJson("/api/review/" + version + "/complaint/" + encodeURIComponent(id));
  if (ticket !== latest.complaint) return;
  if (!c) { status("complaint-status", "This complaint " + err + ".", "error"); return; }
  status("complaint-status", "");
  put("c-ai", c.ai_label || (c.proposed_label ? "proposed " + c.proposed_label + ", not accepted" : "none"));
  put("c-check", c.decision === "accepted" ? "the quoted sentence was found in the text" : (REASONS[c.reason] || "not accepted"));
  put("c-tfidf", c.tfidf_label || "none");
  put("c-consumer", c.hidden ? "hidden while you decide" : (c.consumer_choice || "only on the analyst's own machine"));
  // Where no text can be shown, the empty grey box is hidden, and the note says why.
  const box = $("c-text");
  box.hidden = c.text === null;
  let textNote;
  if (c.text === null) {
    textNote = c.local && !c.with_text
      ? "The text is not shown: the app was started without --with-text."
      : "The text is shown only on the analyst's own machine, with the local data.";
  } else {
    textNote = (c.quote ? "The AI's quoted sentence is highlighted." : "There is no checked quote to highlight.")
      + (c.cut ? " The text is cut at 4,000 characters, as the AI saw it." : "");
    const q = c.quote;
    if (q) {
      const mark = document.createElement("mark"); mark.textContent = c.text.slice(q.start, q.end);
      box.append(document.createTextNode(c.text.slice(0, q.start)), mark, document.createTextNode(c.text.slice(q.end)));
    } else { box.textContent = c.text; }
  }
  put("c-text-note", textNote);
  if (c.decision === "quarantined" && c.can_review) decisionForm(c);
  else if (c.decision === "quarantined") {
    // The public copy (A13) stores no review, so it offers no form. Its note is added to the one on the text.
    status("d-status", "");
    put("c-text-note", textNote + " Reviews are made on the analyst's own machine. This public copy stores no review.");
  }
}

function decisionForm(c) {
  const form = $("decision"); form.hidden = false;
  const select = $("d-label"); clear(select);
  for (const name of c.labels) { const o = document.createElement("option"); o.value = name; o.textContent = name; select.appendChild(o); }
  const pick = { ai_right: c.proposed_label, word_model_right: c.tfidf_label };
  $("r-ai").disabled = !c.proposed_label; $("r-word").disabled = !c.tfidf_label;
  for (const r of form.querySelectorAll("input[name=reason]")) {
    r.checked = !!(c.review && c.review.reason === r.value);
    r.onchange = () => {
      select.disabled = r.value === "no_product";
      if (pick[r.value]) select.value = pick[r.value];
      select.disabled = select.disabled || r.value in pick;
    };
  }
  // Review of #46: a saved decision is locked. The form then sends a correction, a new entry.
  const locked = !!c.review;
  $("d-locked").hidden = !locked; $("d-reasons").hidden = locked;
  $("d-hidden-note").hidden = locked;  // once decided, the consumer's choice is no longer hidden
  $("d-save").textContent = locked ? "Save a correction" : "Save decision";
  if (locked) {
    select.disabled = false;
    select.value = c.review.label || c.labels[0];
    const first = c.review.first;
    status("d-status", "Decision: " + (first.label || "no product") + ", " + DECISIONS[first.reason] + "."
      + (c.review.reason === "correction" ? " Corrected to: " + (c.review.label || "no product") + "." : ""));
  }
  form.onsubmit = async (event) => {
    event.preventDefault();
    const chosen = locked ? { value: "correction" } : form.querySelector("input[name=reason]:checked");
    if (!chosen) { status("d-status", "Choose a reason first.", "error"); return; }
    const body = { label: chosen.value === "no_product" ? null : select.value, reason: chosen.value };
    status("d-status", "Saving...");
    const [saved] = await fetchJson("/api/review/" + version + "/decision/" + encodeURIComponent(c.complaint_id),
      { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "voc" }, body: JSON.stringify(body) });
    if (!saved) { status("d-status", "The decision could not be saved. Check the choice and try again.", "error"); return; }
    // The queue, the counts and the browse list change with a decision, so they are loaded again.
    reviewLoaded = false; listState.loaded = null;
    reviewCount();
    if (currentTab === "review") reviewView(c.complaint_id, true);
    await complaintView(c.complaint_id);
    status("d-status", "Saved: " + (saved.review.label || "no product") + ", "
      + (DECISIONS[saved.review.reason] || "a correction") + ". The decision is locked.", "ok");
  };
}

async function reviewView(openId, queueOnly) {
  // queueOnly reloads the list on the left after a decision, and leaves the open complaint alone.
  if (!queueOnly) {
    showTab("review", !!openId);
    if (openId) complaintView(openId); else $("review-h").focus();
    if (reviewLoaded) return;
  }
  const body = $("review-rows");
  if (!queueOnly) { clear(body); status("review-status", "Loading..."); }
  const ticket = ++latest.review;
  const [q, err] = await fetchJson("/api/review/" + version + "/queue");
  if (ticket !== latest.review) return;
  if (!q) { status("review-status", "The review queue " + err + ".", "error"); return; }
  clear(body); reviewLoaded = true;
  status("review-status", q.total ? "Reviewed " + q.reviewed + " of " + q.total + "." : "No complaint is waiting for review.");
  for (const r of q.rows) {
    const tr = body.insertRow();
    tr.insertCell().appendChild(link("#/review/" + encodeURIComponent(r.complaint_id), r.complaint_id));
    tr.insertCell().textContent = REASONS[r.reason] || "another reason";
    tr.insertCell().textContent = r.proposed_label || "none";
    tr.insertCell().textContent = r.tfidf_label || "none";
    tr.insertCell().textContent = r.review ? (r.review.label || "no product") + ", " + DECISIONS[r.review.reason] : "not yet";
  }
}

function productLinks() {
  // Browse (task 2): the product chooser holds the 11 products, from the "What is being labelled" list.
  const select = $("browse-product");
  for (const li of document.querySelectorAll("#product-list li")) {
    const option = document.createElement("option"); option.value = li.textContent; option.textContent = li.textContent;
    select.appendChild(option);
  }
}

function route() {
  let hash = "";
  try { hash = decodeURIComponent(location.hash.replace(/^#/, "")); } catch (e) { hash = ""; }
  const [, kind, first, second] = hash.split("/");
  // The old complaint address (before the tabs) opens the same complaint in the review queue.
  if (kind === "complaint" && first) { location.replace("#/review/" + encodeURIComponent(first)); return; }
  const before = currentTab;
  if (kind === "product" && first) listView(first, second);
  else if (kind === "browse") listView(null);
  else if (kind === "review") reviewView(first);
  else if (kind === "measured") { showTab("measured", false); }
  else showTab("overview", false);
  reviewCount();
  if (currentTab !== before) window.scrollTo(0, 0);
}

function refreshList() {
  // Paging and the filter go through the address, so the address and the screen stay in step: an open complaint
  // closes, and its link opens it again.
  if (!listState.product) return;
  listState.keepFocus = true;
  const target = "#/product/" + encodeURIComponent(listState.product);
  if (location.hash !== target) location.hash = target; else route();
}

function wire() {
  for (const r of document.querySelectorAll("input[name=show]")) {
    r.onchange = () => { listState.show = r.value; listState.page = 1; refreshList(); };
  }
  $("list-prev").onclick = () => { listState.page -= 1; refreshList(); };
  $("list-next").onclick = () => { listState.page += 1; refreshList(); };
  $("browse-product").onchange = (event) => {
    if (event.target.value) location.hash = "#/product/" + encodeURIComponent(event.target.value);
  };
  for (const button of document.querySelectorAll("button.term")) button.onclick = () => toggleTerm(button);
  window.addEventListener("hashchange", route);
}

async function freshness() {
  // A14: the "Data as of" strip, from committed files only. A fact the files do not hold is said to be missing.
  const [f, s] = await Promise.all([get("/api/freshness"), get("/api/data")]);
  if (!f) { put("fresh-data", "The data facts could not be loaded.", true); return; }
  const d = f.data;
  // Review of #54: both narrative counts on the page, and how one becomes the other (docs/DATA.md).
  const copies = s && s.copies_removed && typeof s.copies_removed.exact === "number" && typeof s.copies_removed.near === "number"
    ? s.copies_removed.exact + s.copies_removed.near : null;
  const pool = s && typeof s.pool === "number" && copies !== null
    ? " " + num(d.narratives) + " have the consumer's own description, and " + num(s.pool) + " of them form the pool after "
      + num(copies) + " copies were removed."
    : " " + num(d.narratives) + " have the consumer's own description.";
  put("fresh-data", d.from && d.to
    ? "Data: the CFPB export from " + day(d.from) + " to " + day(d.to) + ", " + num(d.complaints) + " complaints." + pool
    : "Data: the export's dates are not recorded.", !(d.from && d.to));
  const t = f.test_run;
  // The test run's row is written in the owner's local time, just before the scoring starts.
  put("fresh-test", t
    ? "Test set: " + (t.runs === 1 ? "one scored run, logged on " : t.runs + " scored runs, the last logged on ")
      + day(t.date.slice(0, 10)) + " at " + t.date.slice(11) + " Australian Eastern Daylight Time (AEDT), as it started: "
      + num(t.complaints) + " complaints, prompt " + t.prompt_version + " on " + t.model + "."
    : "No test run is logged yet.", !t);
  put("fresh-schedule", f.schedule_utc
    ? "Pipeline check: the whole pipeline runs by itself every day at " + f.schedule_utc
      + " Coordinated Universal Time (UTC), on made-up complaints with a stand-in model."
    : "Pipeline check: the schedule is not recorded.", !f.schedule_utc);
}

async function main() {
  wire();
  const versions = (await get("/api/versions")) || [];
  versionsTable(versions);
  const dev = versions.filter((r) => r.Set === "dev");
  const latest = dev.length ? dev[dev.length - 1].Prompt : "v1";
  version = latest;
  productLinks();
  route();
  freshness();
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
  // Owner's review of 1 November: the head to head shows the final test run, like the Overview. Without a logged
  // test run it falls back to the development figures, and its heading says so.
  if (tested) headToHead(tested);
  else if (figures) { headToHead(figures); developmentHeadToHead(); }
  if (figures) speedFigures(figures);
  safety(run, audit, queue);
  if (data) scale(data);
}

main();
