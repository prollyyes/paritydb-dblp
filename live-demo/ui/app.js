const descriptions = {
  q1_all_decades: ["Publication volume by decade", "A broad grouped aggregation across the complete selected period."],
  q1_db_yearly: ["Database publication trends", "Yearly aggregation restricted to the database research category."],
  q1_ai_yearly: ["AI publication trends", "Yearly aggregation restricted to the artificial-intelligence category."],
  q2_db_min3: ["Productive database authors", "Authors meeting a publication threshold with distinct co-author counts."],
  q2_db_min5: ["Highly productive database authors", "The same collaboration aggregation with a stricter publication threshold."],
  q3_direct_depth2: ["Direct collaboration reachability", "Bounded traversal from a high-degree seed author."],
  q3_pvldb_distance3_depth4: ["Deep PVLDB collaboration path", "A four-hop bounded shortest-path search from a frozen PVLDB seed."],
  q3_pvldb_distance3_depth2: ["Shallow PVLDB collaboration path", "A two-hop bounded shortest-path search from the same graph region."],
  q3_pvldb_out_of_reach: ["Unreachable PVLDB target", "A bounded traversal that must prove no path exists within the limit."],
  q4_moderate_min1: ["Indirect collaborators", "Exact two-hop collaboration discovery with direct neighbors excluded."],
  q4_moderate_min2: ["Repeated indirect collaborators", "The same two-hop pattern with a stronger shared-work threshold."],
  q5_dm_min1: ["Cross-area data-management authors", "Hierarchy-aware author discovery across declared research categories."],
  q5_ai_min2: ["Cross-area AI authors", "Hierarchy-aware discovery with a minimum publication threshold."],
};

const state = { summaries: [], advisors: [], selected: null };

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"' && quoted && text[index + 1] === '"') { field += '"'; index += 1; }
    else if (character === '"') quoted = !quoted;
    else if (character === "," && !quoted) { row.push(field); field = ""; }
    else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(field); field = "";
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
    } else field += character;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [headers, ...values] = rows;
  return values.map((items) => Object.fromEntries(headers.map((header, index) => [header, items[index]])));
}

async function loadCsv(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return parseCsv(await response.text());
}

function formatMs(value) {
  const number = Number(value);
  return number >= 1000 ? `${(number / 1000).toFixed(number >= 10000 ? 1 : 2)} s` : `${number.toFixed(1)} ms`;
}

function selectedRows() {
  return state.summaries.filter((row) => row.instance_id === state.selected);
}

function renderEvidence() {
  const rows = selectedRows();
  if (rows.length !== 2) return;
  const byBackend = Object.fromEntries(rows.map((row) => [row.backend, row]));
  const postgres = byBackend.postgresql;
  const fuseki = byBackend.fuseki;
  const winner = Number(postgres.median_ms) < Number(fuseki.median_ms) ? "postgresql" : "fuseki";
  const maximum = Math.max(Number(postgres.median_ms), Number(fuseki.median_ms));
  const [title, description] = descriptions[state.selected] || [state.selected, "Frozen paired benchmark instance."];

  document.querySelector("#family-pill").textContent = postgres.query_family;
  document.querySelector("#query-title").textContent = title;
  document.querySelector("#query-description").textContent = description;
  document.querySelector("#correctness").textContent = rows.every((row) => row.correctness_passed === "true") ? "✓ correctness passed" : "correctness failed";
  document.querySelector("#bars").innerHTML = [postgres, fuseki].map((row) => `
    <div class="bar-item">
      <div class="bar-head"><span class="backend-name">${row.backend === "postgresql" ? "PostgreSQL" : "Fuseki"}${row.backend === winner ? " · winner" : ""}</span><span class="median">${formatMs(row.median_ms)}</span></div>
      <div class="bar-track"><div class="bar-fill ${row.backend}" style="width:${Math.max(2, Number(row.median_ms) / maximum * 100)}%"></div></div>
      <span class="range">range ${formatMs(row.min_ms)} – ${formatMs(row.max_ms)} · n=${row.runs}</span>
    </div>`).join("");

  const advisor = state.advisors.find((row) => row.instance_id === state.selected);
  if (!advisor) return;
  document.querySelector("#recommendation").textContent = advisor.recommendation;
  document.querySelector("#reason").textContent = advisor.reason;
  document.querySelector("#measured-winner").textContent = advisor.measured_winner;
  const matched = advisor.match === "True";
  const outcome = document.querySelector("#advisor-outcome");
  outcome.className = `outcome${matched ? "" : " mismatch"}`;
  outcome.textContent = matched ? "Rule matched the measured winner" : `Rule missed · ${formatMs(advisor.latency_regret_ms)} latency regret`;
}

async function refreshLive() {
  const target = document.querySelector("#live-result");
  const button = document.querySelector("#refresh-live");
  button.disabled = true;
  button.textContent = "Checking…";
  try {
    const rows = await loadCsv("runs/latest-comparison.csv");
    const row = rows.find((item) => item.instance_id === "q5_ai_min2") || rows[0];
    if (!row) throw new Error("latest comparison is empty");
    const flipped = row.winner_flip === "True";
    target.innerHTML = `
      <div class="live-row"><span>Live PostgreSQL median</span><strong>${formatMs(row.live_postgresql_median_ms)}</strong></div>
      <div class="live-row"><span>Live Fuseki median</span><strong>${formatMs(row.live_fuseki_median_ms)}</strong></div>
      <div class="live-row"><span>Result signatures</span><strong>identical ✓</strong></div>
      <div class="live-verdict${flipped ? " flip" : ""}">${flipped ? `Winner changed: ${row.accepted_winner} → ${row.live_winner}` : `Winner stable: ${row.live_winner}`}</div>`;
  } catch (error) {
    target.innerHTML = `<p>No live replication loaded yet.</p><code>live-demo/demo.sh 1</code>`;
  } finally {
    button.disabled = false;
    button.textContent = "Refresh live result";
  }
}

async function initialize() {
  try {
    [state.summaries, state.advisors] = await Promise.all([
      loadCsv("data/summary.csv"),
      loadCsv("data/advisor_evaluation.csv"),
    ]);
    const instances = [...new Set(state.summaries.map((row) => row.instance_id))];
    const select = document.querySelector("#instance-select");
    select.innerHTML = instances.map((id) => `<option value="${id}">${state.summaries.find((row) => row.instance_id === id).query_family} · ${(descriptions[id] || [id])[0]}</option>`).join("");
    state.selected = instances[0];
    select.addEventListener("change", (event) => { state.selected = event.target.value; renderEvidence(); });
    renderEvidence();
    await refreshLive();
  } catch (error) {
    document.querySelector("#query-title").textContent = "Evidence could not be loaded";
    document.querySelector("#query-description").textContent = error.message;
  }
}

document.querySelector("#refresh-live").addEventListener("click", refreshLive);
initialize();
