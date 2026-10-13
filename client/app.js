const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const searchButton = document.querySelector("#search-button");
const resultsElement = document.querySelector("#results");
const resultCount = document.querySelector("#result-count");
const summaryElement = document.querySelector("#search-summary");
const inspector = document.querySelector("#inspector");
const indexStatus = document.querySelector("#index-status");

let candidates = [];
let selectedEntityId = null;
let activeRequest = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function score(value) {
  return Number(value ?? 0).toFixed(3);
}

function price(value) {
  if (value === null || value === undefined) return "Price unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function safeRetailerUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function renderLoading() {
  resultsElement.className = "results";
  resultsElement.innerHTML = `
    <div class="loading-state" role="status">
      <div class="loading-bars" aria-hidden="true"><span></span><span></span><span></span></div>
      <p>Comparing catalog identities…</p>
    </div>`;
  resultCount.textContent = "Retrieving lexical and vector candidates.";
  summaryElement.hidden = true;
}

function renderError(message) {
  resultsElement.className = "results";
  resultsElement.innerHTML = `
    <div class="error-state" role="alert">
      <h3>Search could not finish.</h3>
      <p>${escapeHtml(message)} Check that the SQLite index is built, then try again.</p>
    </div>`;
  resultCount.textContent = "No results loaded.";
  summaryElement.hidden = true;
}

function formatDuration(milliseconds) {
  if (!Number.isFinite(milliseconds)) return "—";
  if (milliseconds < 1000) {
    return `${milliseconds < 100 ? milliseconds.toFixed(1) : Math.round(milliseconds)} ms`;
  }
  return `${(milliseconds / 1000).toFixed(2)} s`;
}

function renderSummary(report, totalMs) {
  const comparison = report.comparison;
  const retrieval = report.retrieval;
  const engineMs = report.timing?.engine_ms;
  const margin = comparison.score_margin;
  summaryElement.hidden = false;
  summaryElement.innerHTML = `
    <div class="summary-best">
      <span>Best candidate · ${score(comparison.best_score)}</span>
      <strong>${escapeHtml(comparison.best_name ?? "No match")}</strong>
    </div>
    <div class="summary-margin">Margin ${margin === null ? "—" : score(margin)}</div>
    <div class="summary-runner">
      <span>Runner-up · ${score(comparison.runner_up_score)}</span>
      <strong>${escapeHtml(comparison.runner_up_name ?? "None")}</strong>
    </div>
    <div class="summary-counts">
      ${retrieval.fts_count} FTS5 + ${retrieval.vector_count} vector → ${retrieval.union_count} unique candidates
      <span class="summary-timing">Engine ${formatDuration(engineMs)} · total ${formatDuration(totalMs)}</span>
    </div>`;
}

function resultMarkup(candidate, index) {
  const identity = [candidate.grade, candidate.scale].filter(Boolean).join(" · ");
  const paths = candidate.retrieved_by.join(" + ");
  const relation = candidate.relationship === "VARIANT_OF" ? "Variant" : "Canonical";
  return `
    <button
      class="result-row${candidate.rejected ? " is-rejected" : ""}"
      type="button"
      data-entity-id="${escapeHtml(candidate.entity_id)}"
      aria-pressed="${candidate.entity_id === selectedEntityId}"
      style="--row-index: ${index}"
    >
      <span class="result-rank">${String(index + 1).padStart(2, "0")}</span>
      <span>
        <span class="result-name">${escapeHtml(candidate.canonical_name)}</span>
        <span class="result-meta">
          <span>${escapeHtml(identity || "Unspecified grade")}</span>
          <span>${relation}</span>
          ${candidate.listings.length ? `<span>${candidate.listings.length} retailer listing${candidate.listings.length === 1 ? "" : "s"}</span>` : ""}
        </span>
      </span>
      <span class="retrieval-path">Retrieved by<br><strong>${escapeHtml(paths)}</strong></span>
      <span class="confidence"><strong>${score(candidate.final_score)}</strong><span>${candidate.rejected ? "rejected" : "score"}</span></span>
    </button>`;
}

function renderResults(report) {
  document.body.classList.add("has-results");
  candidates = report.candidates;
  selectedEntityId = candidates[0]?.entity_id ?? null;
  resultCount.textContent = `${candidates.length} ranked candidate${candidates.length === 1 ? "" : "s"}.`;

  if (!candidates.length) {
    resultsElement.className = "results";
    resultsElement.innerHTML = `
      <div class="empty-state">
        <h3>No canonical candidates found.</h3>
        <p>Try fewer filters, a model code, or another part of the kit name.</p>
      </div>`;
    renderInspector(null);
    return;
  }

  resultsElement.className = "results is-fresh";
  resultsElement.innerHTML = candidates.map(resultMarkup).join("");
  window.setTimeout(() => resultsElement.classList.remove("is-fresh"), 900);
  renderInspector(candidates[0]);
}

function signalMarkup(label, value) {
  return `<div class="signal-row"><span>${escapeHtml(label)}</span><span>${escapeHtml(value)}</span></div>`;
}

function renderInspector(candidate) {
  if (!candidate) {
    inspector.innerHTML = `
      <div class="inspector-empty">
        <p class="inspector-code">INSPECTION SHEET</p>
        <h2 id="inspector-heading">No candidate selected</h2>
        <p>Adjust the query or filters and search again.</p>
      </div>`;
    return;
  }

  const tags = [candidate.grade, candidate.scale, candidate.relationship]
    .filter(Boolean)
    .map((tag) => `<li>${escapeHtml(tag)}</li>`)
    .join("");
  const reasons = candidate.match_reasons.length
    ? candidate.match_reasons.map((reason) => {
        const className = reason.startsWith("rejected")
          ? "is-rejection"
          : reason.startsWith("penalty")
            ? "is-penalty"
            : "";
        return `<li class="${className}">${escapeHtml(reason)}</li>`;
      }).join("")
    : "<li>No structured bonus or penalty applied.</li>";
  const retailers = candidate.listings.length
    ? candidate.listings.map((listing) => {
        const url = safeRetailerUrl(listing.product_url);
        const content = `
          <span><strong>${escapeHtml(listing.retailer)}</strong><br>${escapeHtml(listing.availability || "Availability unknown")}</span>
          <strong>${escapeHtml(price(listing.price_usd))}</strong>`;
        return url
          ? `<li><a class="retailer-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${content}</a></li>`
          : `<li><div class="retailer-link">${content}</div></li>`;
      }).join("")
    : "<li><p>No indexed retailer listing for this canonical entity.</p></li>";

  inspector.innerHTML = `
    <div class="inspector-head">
      <p class="inspector-code">${escapeHtml(candidate.entity_id)}</p>
      <div class="inspector-title-row">
        <div>
          <h2 id="inspector-heading">${escapeHtml(candidate.canonical_name)}</h2>
          <p>${candidate.rejected ? "Rejected by identity constraints" : "Canonical candidate"}</p>
        </div>
        <div class="score-stamp" aria-label="Final score ${score(candidate.final_score)}">${score(candidate.final_score)}</div>
      </div>
      <ul class="identity-tags">${tags}</ul>
    </div>
    <section class="inspection-block">
      <h3>Retrieval signals</h3>
      ${signalMarkup("Retrieved by", candidate.retrieved_by.join(" + "))}
      ${candidate.fts_rank_position ? signalMarkup("FTS5 rank", `#${candidate.fts_rank_position}`) : ""}
      ${candidate.fts_bm25 !== null ? signalMarkup("BM25", score(candidate.fts_bm25)) : ""}
      ${candidate.vector_rank_position ? signalMarkup("Vector rank", `#${candidate.vector_rank_position}`) : ""}
      ${candidate.vector_score !== null ? signalMarkup("Cosine", score(candidate.vector_score)) : ""}
      ${signalMarkup("Lexical", score(candidate.lexical_score))}
      ${signalMarkup("Domain adjustment", `${candidate.domain_adjustment >= 0 ? "+" : ""}${score(candidate.domain_adjustment)}`)}
    </section>
    <section class="inspection-block">
      <h3>Why it ranked here</h3>
      <ul class="reason-list">${reasons}</ul>
    </section>
    <section class="inspection-block">
      <h3>Retailer listings</h3>
      <ul class="retailer-list">${retailers}</ul>
    </section>`;
}

async function runSearch() {
  const formData = new FormData(form);
  const query = String(formData.get("q") ?? "").trim();
  if (!query) {
    queryInput.focus();
    return;
  }

  activeRequest?.abort();
  activeRequest = new AbortController();
  searchButton.disabled = true;
  searchButton.querySelector("span").textContent = "Searching…";
  renderLoading();

  const parameters = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    if (String(value).trim()) parameters.set(key, String(value));
  }
  window.history.replaceState({}, "", `/?${parameters.toString()}`);

  try {
    const startedAt = performance.now();
    const response = await fetch(`/api/search?${parameters}`, {
      signal: activeRequest.signal,
      headers: { Accept: "application/json" },
    });
    const report = await response.json();
    const totalMs = performance.now() - startedAt;
    if (!response.ok) throw new Error(report.error || "The search service returned an error.");
    renderSummary(report, totalMs);
    renderResults(report);
  } catch (error) {
    if (error.name !== "AbortError") renderError(error.message);
  } finally {
    searchButton.disabled = false;
    searchButton.querySelector("span").textContent = "Search kits";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

resultsElement.addEventListener("click", (event) => {
  const example = event.target.closest("[data-query]");
  if (example) {
    queryInput.value = example.dataset.query;
    runSearch();
    return;
  }

  const row = event.target.closest("[data-entity-id]");
  if (!row) return;
  selectedEntityId = row.dataset.entityId;
  resultsElement.querySelectorAll("[data-entity-id]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.entityId === selectedEntityId));
  });
  renderInspector(candidates.find((candidate) => candidate.entity_id === selectedEntityId));
  if (window.matchMedia("(max-width: 980px)").matches) {
    inspector.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error();
    const health = await response.json();
    indexStatus.className = "index-status is-ready";
    indexStatus.innerHTML = `<span class="status-light" aria-hidden="true"></span>${health.entities.toLocaleString()} entities ready`;
  } catch {
    indexStatus.className = "index-status is-error";
    indexStatus.innerHTML = `<span class="status-light" aria-hidden="true"></span>Index unavailable`;
  }
}

const initialParameters = new URLSearchParams(window.location.search);
for (const field of ["q", "grade", "scale", "availability"]) {
  const value = initialParameters.get(field);
  if (value && form.elements[field]) form.elements[field].value = value;
}

checkHealth();
if (initialParameters.get("q")) runSearch();
