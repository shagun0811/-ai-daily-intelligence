const state = { data: null, selectedDate: "", archiveOpen: false, bound: false };

async function main() {
  const toggle = document.getElementById("theme-toggle");
  setTheme(document.documentElement.dataset.theme || localStorage.getItem("theme") || "light");
  toggle.addEventListener("click", () => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
  document.getElementById("brand-home").addEventListener("click", (event) => {
    event.preventDefault();
    state.archiveOpen = false;
    selectDate(todayKey());
  });
  document.getElementById("open-archive").addEventListener("click", () => {
    state.archiveOpen = !state.archiveOpen;
    renderChrome();
    syncHash();
  });
  applyHash();
  window.addEventListener("hashchange", () => {
    applyHash();
    render();
  });
  window.addEventListener("keydown", (event) => {
    const tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") return;
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
    box.textContent = "Today’s briefing isn’t available yet. Please try again shortly.";
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
  if (!raw) return;
  if (raw === "archive") {
    state.archiveOpen = true;
    return;
  }
  if (raw === "today") {
    state.selectedDate = "";
    return;
  }
  const date = raw.startsWith("archive/") ? raw.split("/")[1] : raw;
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) state.selectedDate = date;
}

function syncHash() {
  const today = todayKey();
  const selected = state.selectedDate;
  let next = "";
  if (state.archiveOpen && selected && selected === today) next = "#archive";
  else if (selected && selected !== today) next = `#${selected}`;
  const current = location.hash || "";
  if (current !== next) history.replaceState(null, "", next || `${location.pathname}${location.search}`);
}

function render() {
  if (!state.data) return;
  const dates = reportDates();
  const today = todayKey();
  if (!state.selectedDate || !dates.includes(state.selectedDate)) {
    state.selectedDate = dates.includes(today) ? today : dates[dates.length - 1] || "";
  }
  if (!state.bound) {
    document.getElementById("report-date").addEventListener("change", (event) => selectDate(event.target.value));
    document.getElementById("prev-day").addEventListener("click", () => stepDay(-1));
    document.getElementById("next-day").addEventListener("click", () => stepDay(1));
    state.bound = true;
  }
  renderChrome();
  renderBriefing();
  syncHash();
}

function renderChrome() {
  const dates = reportDates();
  const today = todayKey();
  const selected = state.selectedDate;
  const report = (state.data.reports || []).find((row) => row.report_date === selected);
  const index = dates.indexOf(selected);
  const isToday = selected === today;
  document.getElementById("prev-day").disabled = index <= 0;
  document.getElementById("next-day").disabled = index < 0 || index >= dates.length - 1;
  const layout = briefingHasContent(report?.briefing) ? layoutBriefing(report.briefing, selected) : { hero: [] };
  const lead = layout.hero[0];
  document.getElementById("issue-kicker").textContent = isToday ? "Today’s briefing" : "From the archive";
  document.getElementById("issue-date").textContent = selected ? formatLongDate(selected) : "Pick a day";
  const leadEl = document.getElementById("lead-headline");
  if (leadEl) {
    leadEl.textContent = lead?.title || "";
    leadEl.hidden = !lead?.title;
  }
  document.getElementById("issue-dek").textContent = lead
    ? clip(lead.why_it_matters || lead.summary || dekFor(report, isToday), 200)
    : dekFor(report, isToday);
  renderRankStrip(layout.hero);
  document.getElementById("open-archive").setAttribute("aria-expanded", String(state.archiveOpen));
  const panel = document.getElementById("archive-panel");
  panel.classList.toggle("hidden", !state.archiveOpen);
  panel.hidden = !state.archiveOpen;
  setupDateInput(dates);
  renderDateStrip(dates, selected, today);
  renderArchiveGrid(dates, selected, today);
  document.title = selected
    ? `${isToday ? "Today" : formatLongDate(selected)} · AI Daily Intelligence`
    : "AI Daily Intelligence";
}

function dekFor(report, isToday) {
  const briefing = report?.briefing || {};
  const titles = uniqueHero(briefing.executive || []).map((item) => clip(item.title || "", 56));
  if (titles.length >= 3) return `${titles[0]}; ${titles[1]}; and ${titles[2]}`;
  if (titles.length === 2) return `${titles[0]}, and ${titles[1]}`;
  if (titles.length === 1) return titles[0];
  if (briefing.lede) return briefing.lede;
  return isToday
    ? "What moved in AI today, ranked by why it matters."
    : "Open a day to read that morning’s briefing.";
}

function setupDateInput(dates) {
  const input = document.getElementById("report-date");
  const start = state.data.archive_start || dates[0] || "2026-08-17";
  input.min = start;
  input.max = dates[dates.length - 1] || todayKey();
  input.value = state.selectedDate || "";
}

function selectDate(dateKey) {
  if (!dateKey) return;
  state.selectedDate = dateKey;
  state.archiveOpen = false;
  render();
  const heading = document.getElementById("issue-date");
  if (heading && typeof heading.scrollIntoView === "function") {
    heading.scrollIntoView({ block: "start", behavior: "smooth" });
  }
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
    active.scrollIntoView({ inline: "center", block: "nearest", behavior: "auto" });
  }
}

function renderArchiveGrid(dates, selected, today) {
  const grid = document.getElementById("archive-grid");
  grid.innerHTML = dates.slice().reverse().map((value) => {
    const parts = chipParts(value);
    const classes = ["archive-day"];
    if (value === selected) classes.push("selected");
    const label = value === today ? "Today" : `${parts.weekday} ${parts.day} ${parts.month}`;
    return `<button type="button" class="${classes.join(" ")}" data-date="${escapeHtml(value)}"><strong>${escapeHtml(label)}</strong>${escapeHtml(value)}</button>`;
  }).join("") || `<p class="muted">No briefings in the archive yet.</p>`;
  grid.querySelectorAll(".archive-day").forEach((button) => {
    button.addEventListener("click", () => selectDate(button.dataset.date));
  });
}

function renderBriefing() {
  const root = document.getElementById("briefing");
  const dates = reportDates();
  const selected = state.selectedDate;
  const report = (state.data.reports || []).find((row) => row.report_date === selected);
  if (!dates.length) {
    root.innerHTML = emptyDay("No briefings yet.", "The next daily run will publish the first edition here.");
    return;
  }
  if (!report) {
    root.innerHTML = emptyDay(
      `No briefing for ${selected ? formatLongDate(selected) : "this day"}.`,
      "Use the date strip to open a published morning.",
    );
    return;
  }
  const briefing = report.briefing;
  if (briefingHasContent(briefing)) {
    root.innerHTML = renderEdition(report, layoutBriefing(briefing, selected));
    return;
  }
  root.innerHTML = `${editionMeta(report)}<p class="muted">Opening this day’s briefing…</p>`;
  loadReportBody(report).then((parsed) => {
    if (state.selectedDate !== selected) return;
    if (briefingHasContent(parsed)) {
      root.innerHTML = renderEdition(report, layoutBriefing(parsed, selected));
      return;
    }
    if (typeof parsed === "string" && parsed.trim()) {
      root.innerHTML = `${editionMeta(report)}<div class="section">${parsed}</div>${renderGallery(report)}${renderSave(report)}`;
      return;
    }
    root.innerHTML = emptyDay("This day’s files could not be loaded.", "Try Save this briefing below, or pick another date.");
  });
}

function briefingHasContent(briefing) {
  if (!briefing || typeof briefing !== "object") return false;
  return Boolean((briefing.executive || []).length || (briefing.sections || []).length || (briefing.watch || []).length);
}

function layoutBriefing(briefing, reportDate) {
  const raw = uniqueHero(briefing.executive || [], 8);
  const hero = [];
  const demoted = [];
  raw.forEach((item) => {
    if (isStaleForHero(item, reportDate)) demoted.push(item);
    else hero.push(item);
  });
  const shown = hero.slice(0, 5);
  const heroKeys = new Set(shown.map((item) => titleKey(item.title)));
  const more = [...demoted, ...hero.slice(5)];
  const research = [];
  (briefing.sections || []).forEach((section) => {
    const heading = section.heading || "";
    const researchSection = /research/i.test(heading);
    (section.items || []).forEach((item) => {
      if (!item || !item.title) return;
      if (heroKeys.has(titleKey(item.title)) || isNearDuplicate(item, shown)) return;
      if (researchSection || isPaper(item)) research.push(item);
      else more.push(item);
    });
  });
  return {
    hero: shown,
    more,
    research,
    watch: (briefing.watch || []).filter(usefulWatch),
  };
}

function isStaleForHero(item, reportDate) {
  const published = String(item.published_at || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(published) || !/^\d{4}-\d{2}-\d{2}$/.test(reportDate || "")) return false;
  const age = (Date.parse(`${reportDate}T00:00:00Z`) - Date.parse(`${published}T00:00:00Z`)) / 86400000;
  return age > 4;
}

function renderRankStrip(hero) {
  const strip = document.getElementById("rank-strip");
  if (!strip) return;
  if (!hero.length) {
    strip.hidden = true;
    strip.innerHTML = "";
    return;
  }
  strip.hidden = false;
  strip.innerHTML = hero.slice(0, 3).map((item, index) => (
    `<li><span class="rank">${index + 1}</span><span class="rank-title">${escapeHtml(clip(item.title || "", 78))}</span></li>`
  )).join("");
}

function uniqueHero(items, max = 5) {
  const out = [];
  items.forEach((item) => {
    if (!item?.title) return;
    if (isNearDuplicate(item, out)) return;
    out.push(item);
  });
  return out.slice(0, max);
}

function isNearDuplicate(item, list) {
  const generic = new Set(["openai", "google", "microsoft", "amazon", "meta", "anthropic", "nvidia", "intel", "apple", "deepmind"]);
  const words = significantWords(item.title || "");
  return list.some((other) => {
    const shared = significantWords(other.title || "").filter((word) => words.includes(word));
    const distinctive = shared.filter((word) => !generic.has(word));
    return distinctive.some((word) => word.length >= 8) || distinctive.length >= 2;
  });
}

function isPaper(item) {
  const source = `${item.source_name || ""} ${item.source_url || ""}`.toLowerCase();
  return source.includes("arxiv");
}

function usefulWatch(item) {
  const text = String(item || "").trim();
  if (text.length < 8) return false;
  if (/^category\s/i.test(text)) return false;
  if (/selected topics/i.test(text)) return false;
  if (/follow-through/i.test(text)) return false;
  return true;
}

function renderEdition(report, layout) {
  const parts = [editionMeta(report)];
  if (layout.hero.length) {
    parts.push(`<section class="hero-grid">${layout.hero.map((item, index) => heroCard(item, index)).join("")}</section>`);
  }
  if (layout.more.length) {
    parts.push(`<section class="section"><h2>Also today</h2><div class="story-list">${layout.more.map(storyRow).join("")}</div></section>`);
  }
  if (layout.research.length) {
    parts.push(`<section class="section research"><h2>Research</h2><p class="lede-note">Papers worth a scan, after the news.</p><div class="story-list">${layout.research.map((item) => storyRow(item, true)).join("")}</div></section>`);
  }
  if (layout.watch.length) {
    parts.push(`<section class="section"><h2>What to watch</h2><ul class="watch-list">${layout.watch.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>`);
  }
  if (!layout.hero.length && !layout.more.length && !layout.research.length) {
    parts.push(`<p class="muted">This day’s briefing has no readable stories yet.</p>`);
  }
  parts.push(renderGallery(report));
  parts.push(renderSave(report));
  return parts.join("");
}

function editionMeta(report) {
  const selected = report.stats?.selected;
  const isToday = report.report_date === todayKey();
  const count = selected != null ? `${selected} ranked stories` : "Ranked stories";
  const read = readMinutes(report);
  return `<p class="edition-meta">${isToday ? "Today’s edition" : "Archive edition"} · ${escapeHtml(count)}${read ? ` · ${read} min read` : ""}</p>`;
}

function heroCard(item, index) {
  const rank = String(index + 1);
  const why = clip(item.why_it_matters || item.summary || item.body || "", index === 0 ? 340 : 220);
  return `<article class="hero-card${index === 0 ? " lead" : ""}">
    <div class="hero-index" aria-hidden="true">${rank}</div>
    <p class="hero-kicker">${index === 0 ? "Lead story" : `Story ${rank}`}</p>
    <h2>${escapeHtml(item.title || "")}</h2>
    <p class="hero-source">${sourceInner(item)}</p>
    ${why ? `<p class="hero-why"><span class="why-label">Why it matters</span>${escapeHtml(why)}</p>` : ""}
  </article>`;
}

function storyRow(item, research) {
  const why = clip(item.why_it_matters || item.body || item.summary || item.problem || "", research ? 160 : 200);
  return `<article class="story-row">
    <h3>${escapeHtml(item.title || "")}</h3>
    ${why ? `<p>${escapeHtml(why)}</p>` : ""}
    <p class="story-meta">${sourceInner(item, research ? "Read paper" : "")}</p>
  </article>`;
}

function sourceInner(item, verb) {
  if (!item || (!item.source_name && !item.source_url)) return "";
  const label = escapeHtml(prettySource(item.source_name || "Source"));
  const href = item.source_url
    ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">${label}</a>`
    : label;
  const published = item.published_at ? ` · ${escapeHtml(String(item.published_at).slice(0, 10))}` : "";
  const extra = verb && item.source_url
    ? ` · <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">${escapeHtml(verb)}</a>`
    : "";
  return `${href}${published}${extra}`;
}

function prettySource(name) {
  return String(name || "").replace(/\s*cs\.AI\s*\/\s*cs\.LG\s*\/\s*cs\.CL/i, "").replace(/\s+/g, " ").trim() || name;
}

function renderGallery(report) {
  const files = report.files || {};
  const images = [];
  if (files.infographic) images.push([files.infographic, `Visual recap for ${report.report_date}`]);
  if (files.video) images.push([files.video, `Briefing animation for ${report.report_date}`]);
  const cards = files.cards || [];
  if (!images.length && !cards.length) return "";
  return `<section class="gallery">
    <h2>Visual recap</h2>
    <p class="lede-note">Illustrated from this edition — supporting the text, not replacing it.</p>
    <div class="gallery-grid">
      ${images.map(([href, alt]) => `<img src="./${escapeHtml(href)}" alt="${escapeHtml(alt)}">`).join("")}
      ${cards.length ? `<div class="cards-row">${cards.slice(0, 5).map((href, index) => `<img src="./${escapeHtml(href)}" alt="Story card ${index + 1}">`).join("")}</div>` : ""}
    </div>
  </section>`;
}

function renderSave(report) {
  const files = report.files || {};
  const links = [
    ["PDF", files.pdf],
    ["Markdown", files.markdown],
    ["HTML", files.html],
    ["Download all", files.zip],
  ].filter((entry) => entry[1]);
  if (!links.length) return "";
  return `<details class="save"><summary>Save this briefing</summary><div class="save-links">${links.map(([label, href]) => downloadAnchor(label, href)).join("")}</div></details>`;
}

function readMinutes(report) {
  const briefing = report.briefing || {};
  const chunks = [];
  (briefing.executive || []).forEach((item) => chunks.push(item.title, item.summary));
  (briefing.sections || []).forEach((section) => {
    (section.items || []).forEach((item) => chunks.push(item.title, item.body, item.why_it_matters, item.problem));
  });
  const words = chunks.join(" ").split(/\s+/).filter(Boolean).length;
  if (words < 80) return 0;
  return Math.max(2, Math.round(words / 220));
}

async function loadReportBody(report) {
  const files = report.files || {};
  if (files.markdown) {
    try {
      const response = await fetch(`./${files.markdown}`, { cache: "no-store" });
      if (response.ok) {
        const markdown = await response.text();
        const parsed = parseBriefingMarkdown(markdown);
        if (briefingHasContent(parsed)) return parsed;
        if (markdown.trim()) return renderMarkdownLite(markdown);
      }
    } catch (error) {
      // Fall through.
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
      // Fall through.
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
            const entry = { title: match[1], summary: match[2], why_it_matters: match[2], source_name: "", source_url: "", published_at: "" };
            const next = lines[index + 1] ? lines[index + 1].trim() : "";
            const source = next.match(/Source:\s+\[(.+?)\]\((.+?)\)(?:\s*[·•—–-]\s*(\d{4}-\d{2}-\d{2}))?/);
            if (source) {
              entry.source_name = source[1];
              entry.source_url = source[2];
              entry.published_at = source[3] || "";
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
  return { title, stats_line: statsLine, executive, sections, watch, sources, lede: "" };
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
        html.push("<ol>");
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

function downloadAnchor(label, href) {
  const filename = (href || "").split("/").pop() || "download";
  return `<a class="save-link" href="./${escapeHtml(href)}" download="${escapeHtml(filename)}">${escapeHtml(label)}</a>`;
}

function clip(value, limit) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || text.length <= limit) return text;
  const cut = text.slice(0, limit).replace(/\s+\S*$/, "");
  return `${(cut || text.slice(0, limit)).replace(/[,:;.–-]+$/, "")}…`;
}

function titleKey(title) {
  return String(title || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function significantWords(title) {
  return titleKey(title).split(" ").filter((word) => word.length > 4);
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
