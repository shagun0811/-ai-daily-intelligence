"""Light and dark visual themes for the Streamlit dashboard."""

from __future__ import annotations

FONTS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Source+Sans+3:wght@400;500;600;700&display=swap');
"""

DARK_VARS = """
:root {
  --bg: #0b1020;
  --bg2: #151b2e;
  --hero: linear-gradient(135deg, rgba(21, 27, 46, 0.92), rgba(17, 24, 42, 0.75));
  --glow-a: rgba(62, 224, 197, 0.12);
  --glow-b: rgba(109, 141, 255, 0.10);
  --card: rgba(21, 27, 46, 0.92);
  --panel: rgba(21, 27, 46, 0.72);
  --text: #e8edf7;
  --title: #f4f7ff;
  --muted: #8b97b3;
  --body: #c5cde0;
  --accent: #3ee0c5;
  --accent-text: #8af3e0;
  --gold: #e8c47c;
  --gold-text: #f0d59a;
  --border: rgba(232, 237, 247, 0.10);
  --header: rgba(11, 16, 32, 0.78);
  --chip-bg: rgba(62, 224, 197, 0.12);
  --chip-border: rgba(62, 224, 197, 0.25);
  --gold-bg: rgba(232, 196, 124, 0.12);
  --gold-border: rgba(232, 196, 124, 0.28);
  --report: linear-gradient(180deg, rgba(26, 34, 58, 0.95), rgba(17, 23, 40, 0.9));
  --input: #12182a;
  --shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
}
"""

LIGHT_VARS = """
:root {
  --bg: #f3efe4;
  --bg2: #fffaf1;
  --hero: linear-gradient(135deg, #fffdf8, #f4eee0);
  --glow-a: rgba(15, 122, 108, 0.10);
  --glow-b: rgba(59, 91, 204, 0.08);
  --card: #fffcf7;
  --panel: rgba(255, 252, 247, 0.92);
  --text: #1c2433;
  --title: #141b2a;
  --muted: #5c6578;
  --body: #334155;
  --accent: #0f7a6c;
  --accent-text: #0b5f54;
  --gold: #9a6700;
  --gold-text: #7a5200;
  --border: rgba(28, 36, 51, 0.12);
  --header: rgba(243, 239, 228, 0.88);
  --chip-bg: rgba(15, 122, 108, 0.10);
  --chip-border: rgba(15, 122, 108, 0.22);
  --gold-bg: rgba(154, 103, 0, 0.10);
  --gold-border: rgba(154, 103, 0, 0.22);
  --report: linear-gradient(180deg, #fffdf8, #f7f0e2);
  --input: #ffffff;
  --shadow: 0 14px 36px rgba(28, 36, 51, 0.08);
}
"""

SHARED = """
html, body, [class*="css"] {
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
}
.stApp {
  background:
    radial-gradient(1200px 500px at 10% -10%, var(--glow-a), transparent 50%),
    radial-gradient(900px 400px at 100% 0%, var(--glow-b), transparent 45%),
    var(--bg) !important;
  color: var(--text);
}
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
.stApp header {
  background: var(--header) !important;
  color: var(--text);
}
header[data-testid="stHeader"] { backdrop-filter: blur(10px); }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

.stApp p,
.stApp li,
.stApp label,
.stApp small,
.stApp span,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stMarkdownContainer"] span,
.stApp [data-testid="stMarkdownContainer"] strong,
.stApp [data-testid="stMarkdownContainer"] em,
.stApp [data-testid="stMarkdownContainer"] code,
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] p,
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stExpander"] p,
.stApp [data-testid="stExpander"] summary,
.stApp [data-testid="stExpander"] span,
.stApp [data-testid="stAlert"] p,
.stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricValue"],
.stApp [data-testid="stJson"],
.stApp .stMarkdown,
.stApp .stCaption,
.stApp .stRadio label,
.stApp .stCheckbox label,
.stApp .stSelectbox label,
.stApp .stSlider label,
.stApp button[data-baseweb="tab"] {
  color: var(--text) !important;
}
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp .stMarkdown h1, .stApp .stMarkdown h2, .stApp .stMarkdown h3 {
  color: var(--title) !important;
}
.hero-kicker { color: var(--accent) !important; }
.meta { color: var(--muted) !important; }
.meta a { color: var(--accent) !important; }
.item-card p { color: var(--body) !important; }
.metric-card .label { color: var(--muted) !important; }
.metric-card .hint { color: var(--accent) !important; }
.chip { color: var(--accent-text) !important; }
.chip.gold { color: var(--gold-text) !important; }
.score-pill { color: var(--accent) !important; }

div[data-testid="stDataFrame"],
div[data-testid="stDataFrame"] * {
  color: var(--text) !important;
}
div[data-baseweb="popover"],
div[data-baseweb="menu"],
ul[role="listbox"],
ul[role="listbox"] li {
  background-color: var(--card) !important;
  color: var(--text) !important;
}
.stDownloadButton button,
.stButton button {
  background-color: var(--card) !important;
  color: var(--title) !important;
  border: 1px solid var(--border) !important;
}
[data-testid="stExpander"] {
  background: var(--card) !important;
  border-color: var(--border) !important;
}
.stJson, [data-testid="stJson"] {
  background: var(--card) !important;
}

div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-baseweb="select"] > div,
div[data-baseweb="input"] {
  background-color: var(--input) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}
div[data-testid="stSlider"] { color: var(--text); }

.hero {
  padding: 1.4rem 1.6rem 1.2rem;
  margin-bottom: 0.4rem;
  border: 1px solid var(--border);
  border-radius: 22px;
  background: var(--hero);
  box-shadow: var(--shadow);
}
.hero-kicker {
  letter-spacing: 0.22em;
  text-transform: uppercase;
  font-size: 0.72rem;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 0.35rem;
}
.hero h1 {
  font-family: Fraunces, Georgia, serif;
  font-size: 2.35rem;
  line-height: 1.1;
  margin: 0 0 0.45rem 0;
  color: var(--title) !important;
}
.hero p {
  margin: 0;
  color: var(--muted);
  font-size: 1.02rem;
}

.metric-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.75rem; }
@media (max-width: 1100px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
.metric-card {
  padding: 0.95rem 1rem;
  border-radius: 16px;
  background: var(--card);
  border: 1px solid var(--border);
}
.metric-card .label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.metric-card .value {
  font-family: Fraunces, Georgia, serif;
  font-size: 1.7rem;
  color: var(--title);
}
.metric-card .hint { color: var(--accent); font-size: 0.8rem; margin-top: 0.15rem; }

.panel {
  padding: 1rem 1.1rem 0.4rem;
  border-radius: 18px;
  background: var(--panel);
  border: 1px solid var(--border);
  margin-bottom: 0.9rem;
}
.item-card {
  padding: 1rem 1.15rem;
  border-radius: 18px;
  background: var(--card);
  border: 1px solid var(--border);
  margin-bottom: 0.85rem;
}
.item-card h3 {
  font-family: Fraunces, Georgia, serif;
  font-size: 1.22rem;
  margin: 0.35rem 0 0.45rem;
  color: var(--title) !important;
}
.item-card p { color: var(--body) !important; margin: 0.2rem 0 0.55rem; }
.meta { color: var(--muted) !important; font-size: 0.86rem; }
.meta a { color: var(--accent) !important; }
.chip {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  margin: 0 0.28rem 0.28rem 0;
  border-radius: 999px;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  background: var(--chip-bg);
  color: var(--accent-text);
  border: 1px solid var(--chip-border);
}
.chip.gold {
  background: var(--gold-bg);
  color: var(--gold-text);
  border-color: var(--gold-border);
}
.score-pill {
  float: right;
  font-family: Fraunces, Georgia, serif;
  font-size: 1.15rem;
  color: var(--accent);
}
.report-card {
  padding: 1.15rem 1.2rem 1rem;
  border-radius: 20px;
  background: var(--report);
  border: 1px solid var(--chip-border);
  margin-bottom: 1rem;
}
.report-date {
  font-family: Fraunces, Georgia, serif;
  font-size: 1.55rem;
  color: var(--title);
  margin: 0.15rem 0 0.2rem;
}

div[data-testid="stTabs"] button { font-weight: 600; color: var(--text); }
div[data-testid="stMetric"] {
  background: var(--card);
  padding: 0.7rem 0.8rem;
  border-radius: 14px;
  border: 1px solid var(--border);
}
"""

CHART_COLORS = {
    "dark": {
        "status": "#3ee0c5",
        "category": "#8aa4ff",
        "score": "#e8c47c",
        "axis": "#c5cde0",
    },
    "light": {
        "status": "#0f7a6c",
        "category": "#3b5bcc",
        "score": "#9a6700",
        "axis": "#475569",
    },
}


def css_for(mode: str) -> str:
    variables = LIGHT_VARS if mode == "light" else DARK_VARS
    return FONTS + variables + SHARED
