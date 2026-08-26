const state = { data: null, tab: "items", selectedDate: "", bound: false };

async function main() {
  const toggle = document.getElementById("theme-toggle");
  const saved = localStorage.getItem("theme") || "dark";
  setTheme(saved);
  toggle.addEventListener("click", () => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });

  applyHash();
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  document.getElementById("open-today").addEventListener("click", () => {
    const today = todayKey();
    const dates = reportDates();
    selectDate(dates.includes(today) ? today : dates[dates.length - 1] || "");
    switchTab("reports");
  });
  window.addEventListener("hashchange", () => {
    applyHash();
    syncTabs();
    if (state.tab === "reports") renderArchive();
  });
  window.addEventListener("keydown", (event) => {
    if (state.tab !== "reports") return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepDay(-1);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      stepDay(1);
    }
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

function todayKey() {
  if (state.data && state.data.today) return state.data.today;
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

function reportDates() {
  return [...new Set((state.data?.reports || []).map((row) => row.report_date).filter(Boolean))].sort();
}

function applyHash() {
  const raw = (location.hash || "").replace(/^#/, "");
  if (raw.startsWith("archive")) {
    state.tab = "reports";
    const date = raw.split("/")[1] || "";
    if (date) state.selectedDate = date;
  }
}

function syncHash() {
  if (state.tab === "reports") {
    const next = state.selectedDate ? `#archive/${state.selectedDate}` : "#archive";
    if (location.hash !== next) history.replaceState(null, "", next);
    return;
  }
  if ((location.hash || "").startsWith("#archive")) {
    history.replaceState(null, "", `${location.pathname}${location.search}`);
  }
}

function switchTab(tab) {
  state.tab = tab;
  if (tab === "reports") {
    const dates = reportDates();
    const today = todayKey();
    if (!state.selectedDate || !dates.includes(state.selectedDate)) {
      state.selectedDate = dates.includes(today) ? today : dates[dates.length - 1] || "";
    }
    renderArchive();
  }
  syncTabs();
  syncHash();
}

function syncTabs() {
  document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.dataset.tab === state.tab));
  document.getElementById("items").classList.toggle("hidden", state.tab !== "items");
  document.getElementById("reports").classList.toggle("hidden", state.tab !== "reports");
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
  if (!state.bound) {
    document.getElementById("search").addEventListener("input", renderItems);
    document.getElementById("source").addEventListener("change", renderItems);
    document.getElementById("category").addEventListener("change", renderItems);
    document.getElementById("report-date").addEventListener("change", (event) => selectDate(event.target.value));
    document.getElementById("prev-day").addEventListener("click", () => stepDay(-1));
    document.getElementById("next-day").addEventListener("click", () => stepDay(1));
    state.bound = true;
  }
  renderItems();
  const dates = reportDates();
  const today = todayKey();
  if (!state.selectedDate) {
    state.selectedDate = dates.includes(today) ? today : dates[dates.length - 1] || "";
  }
  if (state.tab === "reports") renderArchive();
  else {
    setupDateInput(dates);
    syncTabs();
  }
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

function setupDateInput(dates) {
  const input = document.getElementById("report-date");
  const start = state.data.archive_start || dates[0] || "2026-08-17";
  input.min = start;
  input.max = dates[dates.length - 1] || todayKey();
  input.value = state.selectedDate || "";
}

function selectDate(dateKey) {
  state.selectedDate = dateKey || "";
  if (state.tab !== "reports") state.tab = "reports";
  renderArchive();
  syncTabs();
  syncHash();
}

function stepDay(delta) {
  const dates = reportDates();
  if (!dates.length) return;
  const current = state.selectedDate && dates.includes(state.selectedDate)
    ? state.selectedDate
    : dates[dates.length - 1];
  const index = dates.indexOf(current);
  const next = dates[index + delta];
  if (next) selectDate(next);
}

function renderArchive() {
  const reports = state.data.reports || [];
  const dates = reportDates();
  const today = todayKey();
  const selected = state.selectedDate;
  const report = reports.find((row) => row.report_date === selected);
  const index = dates.indexOf(selected);
  document.getElementById("prev-day").disabled = index <= 0;
  document.getElementById("next-day").disabled = index < 0 || index >= dates.length - 1;
  document.getElementById("archive-kicker").textContent = selected === today ? "Today's briefing" : "Archive briefing";
  document.getElementById("archive-title").textContent = selected ? formatLongDate(selected) : "Pick a day";
  document.getElementById("archive-sub").textContent = dates.length
    ? `${dates.length} day${dates.length === 1 ? "" : "s"} in the archive · ${today} is today`
    : "No reports stored yet.";
  setupDateInput(dates);
  renderDateStrip(dates, selected, today);
  const root = document.getElementById("report-reader");
  if (!dates.length) {
    root.innerHTML = emptyDay("No briefings in the archive yet.", "A daily run will add the first readable report here.");
    return;
  }
  if (!report) {
    root.innerHTML = emptyDay(
      `No briefing for ${selected ? formatLongDate(selected) : "this day"}.`,
      "That date is missing from the archive. Use Prev/Next or the date chips to open a published day.",
    );
    return;
  }
  root.innerHTML = renderReportChrome(report, selected === today);
  const body = document.getElementById("report-body");
  const briefing = report.briefing;
  if (briefingHasContent(briefing)) {
    body.innerHTML = renderBriefing(briefing);
    return;
  }
  body.innerHTML = `<p class="muted">Loading this day's briefing…</p>`;
  loadReportBody(report).then((html) => {
    if (state.selectedDate !== selected) return;
    body.innerHTML = html || `<p class="muted">This day's files could not be loaded. Use the download links above.</p>`;
  });
}

function renderDateStrip(dates, selected, today) {
  const strip = document.getElementById("date-strip");
  strip.innerHTML = dates.map((value) => {
    const parts = chipParts(value);
    const classes = ["date-chip"];
    if (value === selected) classes.push("selected");
    if (value === today) classes.push("today");
    return `<button type="button" class="${classes.join(" ")}" role="option" aria-selected="${value === selected}" data-date="${escapeHtml(value)}">
      <span class="dow">${value === today ? "Today" : escapeHtml(parts.weekday)}</span>
      <span class="num">${escapeHtml(parts.day)}</span>
      <span class="mon">${escapeHtml(parts.month)}</span>
    </button>`;
  }).join("");
  strip.querySelectorAll(".date-chip").forEach((button) => {
    button.addEventListener("click", () => selectDate(button.dataset.date));
  });
  const active = strip.querySelector(".date-chip.selected");
  if (active && typeof active.scrollIntoView === "function") {
    active.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }
}

function renderReportChrome(report, isToday) {
  const files = report.files || {};
  const date = report.report_date || "report";
  const stats = report.stats || {};
  const links = [
    ["Download all", files.zip, "primary"],
    ["Markdown", files.markdown, ""],
    ["HTML", files.html, ""],
    ["PDF", files.pdf, ""],
  ].filter((entry) => entry[1]);
  const selected = stats.selected != null ? stats.selected : "—";
  const candidates = stats.candidates != null ? stats.candidates : "—";
  const aside = [
    files.infographic ? `<img src="./${escapeHtml(files.infographic)}" alt="Infographic for ${escapeHtml(date)}">` : "",
    files.video ? `<img src="./${escapeHtml(files.video)}" alt="Briefing GIF for ${escapeHtml(date)}">` : "",
  ].filter(Boolean).join("");
  const cards = files.cards || [];
  return `
    <div class="report-chrome">
      <div>
        <div class="kicker">${isToday ? "Today" : "Archive"}</div>
        <h2>${escapeHtml(report.title || "AI Daily Intelligence")}${isToday ? '<span class="badge-today">Today</span>' : ""}</h2>
        <p class="muted">${escapeHtml(date)} · ${escapeHtml(String(selected))} stories selected from ${escapeHtml(String(candidates))} scored items</p>
      </div>
    </div>
    <div class="downloads secondary">${links.map(([label, href, kind]) => downloadAnchor(label, href, kind)).join("")}</div>
    <div class="report-layout">
      <div id="report-body" class="report-body"></div>
      <aside class="report-aside">
        ${aside || `<p class="muted">No infographic for this day.</p>`}
        ${cards.length ? `<div class="cards-row">${cards.slice(0, 5).map((href, index) => `<img src="./${escapeHtml(href)}" alt="Card ${index + 1}">`).join("")}</div>` : ""}
      </aside>
    </div>
  `;
}

function briefingHasContent(briefing) {
  if (!briefing || typeof briefing !== "object") return false;
  return Boolean((briefing.executive || []).length || (briefing.sections || []).length || (briefing.watch || []).length);
}

function renderBriefing(briefing) {
  const parts = [];
  if (briefing.stats_line) parts.push(`<p class="muted">${escapeHtml(briefing.stats_line)}</p>`);
  if ((briefing.executive || []).length) {
    parts.push("<h2>Executive Summary</h2><ol class=\"exec\">");
    briefing.executive.forEach((item) => {
      parts.push(`<li><strong>${escapeHtml(item.title || "")}</strong> — ${escapeHtml(item.summary || "")}${sourceLine(item)}</li>`);
    });
    parts.push("</ol>");
  }
  (briefing.sections || []).forEach((section) => {
    parts.push(`<h2>${escapeHtml(section.heading || "")}</h2>`);
    const items = section.items || [];
    if (!items.length) {
      parts.push(`<p class="muted">No items in this section.</p>`);
      return;
    }
    items.forEach((item) => {
      parts.push(`<article class="story"><h3>${escapeHtml(item.title || "")}</h3>`);
      if (item.body) parts.push(`<p>${escapeHtml(item.body)}</p>`);
      if (item.problem) parts.push(`<p><strong>Problem:</strong> ${escapeHtml(item.problem)}</p>`);
      if (item.key_contribution) parts.push(`<p><strong>Key contribution:</strong> ${escapeHtml(item.key_contribution)}</p>`);
      if (item.why_it_matters) parts.push(`<p><strong>Why it matters:</strong> ${escapeHtml(item.why_it_matters)}</p>`);
      parts.push(sourceLine(item, true));
      if (item.notes) parts.push(`<p class="muted">${escapeHtml(item.notes)}</p>`);
      parts.push("</article>");
    });
  });
  if ((briefing.watch || []).length) {
    parts.push("<h2>What to Watch</h2><ul>");
    briefing.watch.forEach((item) => parts.push(`<li>${escapeHtml(item)}</li>`));
    parts.push("</ul>");
  }
  if ((briefing.sources || []).length) {
    parts.push("<h2>Sources</h2><ul>");
    briefing.sources.forEach((item) => {
      const href = item.url || "#";
      parts.push(`<li><a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(item.name || href)}</a></li>`);
    });
    parts.push("</ul>");
  }
  return parts.join("") || `<p class="muted">This day's briefing has no readable text yet.</p>`;
}

function sourceLine(item, block) {
  if (!item || (!item.source_name && !item.source_url)) return "";
  const label = escapeHtml(item.source_name || "Source");
  const href = item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">${label}</a>` : label;
  const published = item.published_at ? ` — ${escapeHtml(item.published_at)}` : "";
  const inner = `Source: ${href}${published}`;
  return block ? `<p class="story-source">${inner}</p>` : `<div class="story-source">${inner}</div>`;
}

async function loadReportBody(report) {
  const files = report.files || {};
  if (files.markdown) {
    try {
      const response = await fetch(`./${files.markdown}`, { cache: "no-store" });
      if (response.ok) {
        const markdown = await response.text();
        const parsed = parseBriefingMarkdown(markdown);
        if (briefingHasContent(parsed)) return renderBriefing(parsed);
        if (markdown.trim()) return renderMarkdownLite(markdown);
      }
    } catch (error) {
      // Fall through to HTML / preview.
    }
  }
  if (files.html) {
    try {
      const response = await fetch(`./${files.html}`, { cache: "no-store" });
      if (response.ok) {
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, "text/html");
        const heading = doc.body.querySelector("h1");
        if (heading) heading.remove();
        const meta = doc.body.querySelector("p.meta");
        if (meta) meta.remove();
        return doc.body.innerHTML;
      }
    } catch (error) {
      // Fall through to preview.
    }
  }
  if (report.preview) return renderMarkdownLite(report.preview);
  return "";
}

function parseBriefingMarkdown(markdown) {
  const executive = [];
  const sections = [];
  const watch = [];
  const sources = [];
  let title = "AI Daily Intelligence";
  let statsLine = "";
  let heading = "";
  let section = null;
  let item = null;
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");

  const flushItem = () => {
    if (item && section) section.items.push(item);
    item = null;
  };
  const flushSection = () => {
    flushItem();
    if (section) sections.push(section);
    section = null;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const stripped = lines[index].trim();
    if (stripped.startsWith("# ") && !heading && !executive.length) {
      title = stripped.slice(2).trim() || title;
      continue;
    }
    if (stripped.startsWith("*") && stripped.endsWith("*") && /consider/i.test(stripped)) {
      statsLine = stripped.replace(/^\*|\*$/g, "").trim();
      continue;
    }
    if (stripped.startsWith("## ")) {
      flushSection();
      heading = stripped.slice(3).trim();
      if (heading === "Executive Summary") {
        index += 1;
        while (index < lines.length && !lines[index].startsWith("## ")) {
          const row = lines[index].trim();
          const match = row.match(/^\d+\.\s+\*\*(.+?)\*\*\s+[—–-]\s+(.*)$/);
          if (match) {
            const entry = { title: match[1], summary: match[2], source_name: "", source_url: "" };
            const next = lines[index + 1] ? lines[index + 1].trim() : "";
            const source = next.match(/Source:\s+\[(.+?)\]\((.+?)\)/);
            if (source) {
              entry.source_name = source[1];
              entry.source_url = source[2];
              index += 1;
            }
            executive.push(entry);
          }
          index += 1;
        }
        index -= 1;
        continue;
      }
      if (heading === "What to Watch") {
        index += 1;
        while (index < lines.length && !lines[index].startsWith("## ")) {
          const row = lines[index].trim();
          if (row.startsWith("- ")) watch.push(row.slice(2).trim());
          index += 1;
        }
        index -= 1;
        continue;
      }
      if (heading === "Sources") {
        index += 1;
        while (index < lines.length && !lines[index].startsWith("## ")) {
          const row = lines[index].trim();
          const link = row.match(/\[([^\]]+)\]\(([^)]+)\)/);
          if (row.startsWith("- ") && link) sources.push({ name: link[1], url: link[2] });
          index += 1;
        }
        index -= 1;
        continue;
      }
      section = { heading, items: [] };
      continue;
    }
    if (stripped.startsWith("### ") && section) {
      flushItem();
      item = { title: stripped.slice(4).trim(), body: "", problem: "", key_contribution: "", why_it_matters: "", source_name: "", source_url: "", published_at: "" };
      continue;
    }
    if (!item) continue;
    if (stripped.startsWith("**Problem:**")) item.problem = stripped.replace("**Problem:**", "").trim();
    else if (stripped.startsWith("**Key contribution:**")) item.key_contribution = stripped.replace("**Key contribution:**", "").trim();
    else if (stripped.startsWith("**Why it matters:**")) item.why_it_matters = stripped.replace("**Why it matters:**", "").trim();
    else if (stripped.startsWith("**Source:**")) {
      const link = stripped.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (link) {
        item.source_name = link[1];
        item.source_url = link[2];
      }
      if (stripped.includes("—")) item.published_at = stripped.split("—").pop().trim();
    } else if (stripped && !stripped.startsWith("No items")) {
      item.body = item.body ? `${item.body} ${stripped}` : stripped;
    }
  }
  flushSection();
  return { title, stats_line: statsLine, executive, sections, watch, sources };
}

function renderMarkdownLite(markdown) {
  const blocks = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let list = null;
  const closeList = () => {
    if (list) {
      html.push(list === "ol" ? "</ol>" : "</ul>");
      list = null;
    }
  };
  const inline = (value) => escapeHtml(value)
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  blocks.forEach((line) => {
    const stripped = line.trim();
    if (!stripped) {
      closeList();
      return;
    }
    if (stripped.startsWith("### ")) {
      closeList();
      html.push(`<h3>${inline(stripped.slice(4))}</h3>`);
      return;
    }
    if (stripped.startsWith("## ")) {
      closeList();
      html.push(`<h2>${inline(stripped.slice(3))}</h2>`);
      return;
    }
    if (stripped.startsWith("# ")) {
      closeList();
      html.push(`<h2>${inline(stripped.slice(2))}</h2>`);
      return;
    }
    const ordered = stripped.match(/^\d+\.\s+(.*)$/);
    if (ordered) {
      if (list !== "ol") {
        closeList();
        html.push("<ol class=\"exec\">");
        list = "ol";
      }
      html.push(`<li>${inline(ordered[1])}</li>`);
      return;
    }
    if (stripped.startsWith("- ")) {
      if (list !== "ul") {
        closeList();
        html.push("<ul>");
        list = "ul";
      }
      html.push(`<li>${inline(stripped.slice(2))}</li>`);
      return;
    }
    closeList();
    html.push(`<p>${inline(stripped)}</p>`);
  });
  closeList();
  return html.join("");
}

function emptyDay(title, detail) {
  return `<div class="empty-day"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(detail)}</p></div>`;
}

function chipParts(dateKey) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return {
    weekday: date.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" }),
    day: String(day),
    month: date.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" }),
  };
}

function formatLongDate(dateKey) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
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
