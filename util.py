from enum import Enum

css = """
:root {
  --tf-bg: #0f172a;
  --tf-bg-panel: #111827;
  --tf-card: #1e293b;
  --tf-border: #334155;
  --tf-text: #e2e8f0;
  --tf-muted: #94a3b8;
  --tf-accent: #38bdf8;
  --tf-positive: #22c55e;
  --tf-negative: #ef4444;
  --tf-warn: #f59e0b;
}

.gradio-container {
  max-width: 1400px !important;
  margin: 0 auto !important;
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
}

.tf-hero {
  text-align: center;
  padding: 32px 16px 16px;
}
.tf-hero h1 {
  font-size: 42px;
  font-weight: 700;
  margin: 0 0 8px;
  letter-spacing: -0.02em;
}
.tf-hero p {
  font-size: 16px;
  color: var(--tf-muted);
  max-width: 640px;
  margin: 0 auto;
  line-height: 1.5;
}

.tf-card {
  background: var(--tf-card);
  border: 1px solid var(--tf-border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 18px rgba(0,0,0,0.18);
}

.tf-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--tf-card);
  border: 1px solid var(--tf-border);
  border-radius: 12px;
  margin-bottom: 16px;
}
.tf-toolbar .tf-meta {
  margin-left: auto;
  color: var(--tf-muted);
  font-size: 13px;
}

.tf-status {
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.4);
  color: var(--tf-accent);
  font-size: 13px;
  display: inline-block;
}
.tf-status.idle { background: transparent; border-color: var(--tf-border); color: var(--tf-muted); }
.tf-status.running { background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.5); color: var(--tf-warn); }
.tf-status.error { background: rgba(239, 68, 68, 0.12); border-color: rgba(239, 68, 68, 0.5); color: var(--tf-negative); }

.tf-trader-title {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 8px;
}
.tf-trader-meta {
  color: var(--tf-muted);
  font-size: 13px;
  margin-bottom: 12px;
}

.tf-portfolio {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 12px;
}
.tf-portfolio.positive { background: rgba(34, 197, 94, 0.16); }
.tf-portfolio.negative { background: rgba(239, 68, 68, 0.16); }
.tf-portfolio .value { font-size: 28px; font-weight: 700; }
.tf-portfolio .pnl { font-size: 15px; }
.tf-portfolio .pnl.positive { color: var(--tf-positive); }
.tf-portfolio .pnl.negative { color: var(--tf-negative); }

.tf-log {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid var(--tf-border);
  border-radius: 6px;
  padding: 10px 12px;
  max-height: 220px;
  overflow-y: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11.5px;
  line-height: 1.5;
}

.positive-pnl { color: var(--tf-positive) !important; font-weight: bold; }
.negative-pnl { color: var(--tf-negative) !important; font-weight: bold; }
.positive-bg { background-color: var(--tf-positive) !important; font-weight: bold; }
.negative-bg { background-color: var(--tf-negative) !important; font-weight: bold; }

.dataframe-fix-small .table-wrap { min-height: 150px; max-height: 150px; }
.dataframe-fix .table-wrap { min-height: 200px; max-height: 200px; }

.tf-credit {
  color: var(--tf-muted);
  font-size: 12px;
  line-height: 1.4;
  margin: 24px 0 8px;
  text-align: center;
}

footer { display: none !important; }
"""


js = """
function refresh() {
    const url = new URL(window.location);
    if (url.searchParams.get('__theme') !== 'dark') {
        url.searchParams.set('__theme', 'dark');
        window.location.href = url.href;
    }
}
"""


class Color(Enum):
    RED = "#f87171"
    GREEN = "#4ade80"
    YELLOW = "#facc15"
    BLUE = "#60a5fa"
    MAGENTA = "#c084fc"
    CYAN = "#22d3ee"
    WHITE = "#cbd5e1"
