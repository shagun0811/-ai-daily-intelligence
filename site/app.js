const state = { data: null, tab: "items" };

async function main() {
  const toggle = document.getElementById("theme-toggle");
  const saved = localStorage.getItem("theme") || "dark";
  setTheme(saved);
  toggle.addEventListener("click", () => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });

  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.tab = button.dataset.tab;
      document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el === button));
      document.getElementById("items").classList.toggle("hidden", state.tab !== "items");
      document.getElementById("reports").classList.toggle("hidden", state.tab !== "reports");
    });
  });

  try {
    const response = await fetch("./data/dashboard.json", { cache: "no-store" });
    if (!response.ok) throw new Error("dashboard.json missing");
    state.data = await response.json();
    render();
  } catch (error) {
    const box = document.getElementById("error");
    box.classList.remove("hidden");
    box.textContent = "No live data yet. In VS Code run: python scripts/export_site.py";
  }
}

function setTheme(mode) {
  document.documentElement.dataset.theme = mode;
  localStorage.setItem("theme", mode);
  document.getElementById("theme-toggle").textContent = mode === "dark" ? "Light" : "Dark";
}

function render() {
  const { stats, options, items, reports, generated_at } = state.data;
  document.getElementById("updated").textContent = generated_at
    ? `Last export: ${generated_at.replace("T", " ").slice(0, 16)} UTC`
    : "";
  document.getElementById("metrics").innerHTML = [
    metric("Articles", stats.articles),
    metric("Scored", stats.scored),
    metric("Relevant", stats.relevant),
    metric("Avg score", stats.average_score ?? "—"),
    metric("Reports", stats.reports, stats.latest_report_date || "none yet"),
  ].join("");

  fillSelect("source", options.sources || []);
  fillSelect("category", options.categories || []);
  fillReportDates(reports || []);
  document.getElementById("search").addEventListener("input", renderItems);
  document.getElementById("source").addEventListener("change", renderItems);
  document.getElementById("category").addEventListener("change", renderItems);
  document.getElementById("report-date").addEventListener("change", () => renderReports(reports || []));
  renderItems();
  renderReports(reports || []);
}

function metric(label, value, hint) {
  return `<div class="metric"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(String(value))}</div>${hint ? `<div class="muted">${escapeHtml(hint)}</div>` : ""}</div>`;
}

function fillSelect(id, values) {
  const select = document.getElementById(id);
  const current = select.value;
  select.innerHTML = `<option value="">All</option>` + values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  select.value = current;
}

function renderItems() {
  const query = document.getElementById("search").value.trim().toLowerCase();
  const source = document.getElementById("source").value;
  const category = document.getElementById("category").value;
  const rows = (state.data.items || []).filter((item) => {
    const hay = `${item.title} ${item.source} ${item.brief}`.toLowerCase();
    if (query && !hay.includes(query)) return false;
    if (source && item.source !== source) return false;
    if (category && item.category !== category) return false;
    return true;
  });
  document.getElementById("item-count").textContent = `${rows.length} matching items`;
  document.getElementById("item-list").innerHTML = rows.slice(0, 40).map((item) => `
    <article class="card">
      <div class="muted">${escapeHtml(item.source || "")} · ${escapeHtml(item.status || "")}${item.score != null ? ` · ${Number(item.score).toFixed(1)}` : ""}</div>
      <h3>${escapeHtml(item.title || "")}</h3>
      <div>${chip(item.category)}${item.relevant ? chip("relevant") : ""}</div>
      <p>${escapeHtml(item.brief || "No stored summary yet.")}</p>
      <a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noopener">Open source</a>
    </article>
  `).join("") || `<p class="muted">No items match these filters.</p>`;
}

function fillReportDates(reports) {
  const select = document.getElementById("report-date");
  const current = select.value;
  const dates = reports.map((report) => report.report_date).filter(Boolean);
  select.innerHTML = `<option value="">All dates</option>` + dates.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  select.value = dates.includes(current) ? current : "";
}

function renderReports(reports) {
  const selected = document.getElementById("report-date").value;
  const visible = selected ? reports.filter((report) => report.report_date === selected) : reports;
  const count = document.getElementById("report-count");
  const root = document.getElementById("report-list");
  const start = state.data.archive_start || "2026-08-17";
  count.textContent = reports.length
    ? `${reports.length} stored briefing${reports.length === 1 ? "" : "s"} from ${start} onward — newest first. Use Download all for the full packet.`
    : "No reports stored yet.";
  if (!visible.length) {
    root.innerHTML = `<p class="muted">No reports in the archive yet.</p>`;
    return;
  }
  root.innerHTML = visible.map((report, index) => {
    const files = report.files || {};
    const date = report.report_date || "report";
    const links = [
      ["Download all", files.zip, "primary"],
      ["Markdown", files.markdown, ""],
      ["HTML", files.html, ""],
      ["PDF", files.pdf, ""],
      ["Infographic", files.infographic, ""],
      ["Video", files.video, ""],
    ].filter((entry) => entry[1]);
    const cards = files.cards || [];
    const latest = !selected && index === 0;
    return `
      <article class="report">
        <div class="kicker">${latest ? "Latest briefing" : "Archive"}</div>
        <h2>${escapeHtml(date)}</h2>
        <p class="muted">${escapeHtml(report.title || "")} · selected ${escapeHtml(String(report.stats?.selected ?? "—"))} of ${escapeHtml(String(report.stats?.candidates ?? "—"))}</p>
        <div class="downloads">${links.map(([label, href, kind]) => downloadAnchor(label, href, kind)).join("")}</div>
        ${cards.length ? `<div class="downloads">${cards.map((href, cardIndex) => downloadAnchor(`Card ${cardIndex + 1}`, href, "")).join("")}</div>` : ""}
        ${files.infographic ? `<div class="visuals"><img src="./${files.infographic}" alt="Infographic"></div>` : ""}
        ${cards.length ? `<div class="visuals">${cards.slice(0, 4).map((href, index) => `<img src="./${href}" alt="Card ${index + 1}">`).join("")}</div>` : ""}
      </article>
    `;
  }).join("");
}

function downloadAnchor(label, href, kind) {
  const filename = (href || "").split("/").pop() || "download";
  const cls = kind === "primary" ? " class=\"download-all\"" : "";
  return `<a href="./${escapeHtml(href)}" download="${escapeHtml(filename)}"${cls}>${escapeHtml(label)}</a>`;
}

function chip(text) {
  return text ? `<span class="chip">${escapeHtml(text)}</span>` : "";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

main();
