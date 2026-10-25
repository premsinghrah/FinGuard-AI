# FinGuard AI

<p align="center">
  <img src="https://img.shields.io/badge/ERPNext-v14%2Fv15-orange?style=flat-square&logo=frappe" alt="ERPNext v14/v15">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/ML-Isolation%20Forest-blueviolet?style=flat-square" alt="Isolation Forest">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/CI-GitHub%20Actions-brightgreen?style=flat-square&logo=githubactions" alt="CI">
</p>

<p align="center">
  <a href="https://codespaces.new/premsinghrah/FinGuard-AI">
    <img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces">
  </a>
</p>

<p align="center">
  <strong>Detect anomalies. Explain risks. Protect financial integrity.</strong>
</p>

<p align="center">
  An AI-powered financial anomaly detection and investigation system built as a custom ERPNext/Frappe application.<br>
  🌐 <strong>Live GitHub Pages Demo</strong>: <a href="https://premsinghrah.github.io/FinGuard-AI/">https://premsinghrah.github.io/FinGuard-AI/</a>
</p>

---

## Overview

**FinGuard AI** (`finance_ai`) is a production-grade ERPNext custom application that monitors your financial transactions in real time, identifies unusual activity using machine learning and rule-based checks, and guides your finance team through a structured investigation workflow.

It integrates directly into ERPNext's **Accounts** module — no separate dashboard tool, no CSV exports, no manual trawling through journals. Anomalies surface as actionable alerts inside the system your team already uses.

> ⚠️ **Important Disclaimer:** FinGuard AI identifies *potential* anomalies and financial risks that warrant human investigation. All alerts require review by qualified finance professionals. This system does **not** confirm fraud or criminal activity.

---

## Deployment Architecture: Static Demo vs Production Backend

FinGuard AI is designed with clean architectural separation between client-side evaluation and server-side production processing:

| Dimension | 🌐 Static Demo Mode (GitHub Pages) | 🚀 Production / Full ML Backend |
|---|---|---|
| **Hosting** | GitHub Pages (`index.html`, `demo_dashboard.html`) | Python Server (`run_demo.py`), Docker, Frappe Bench, or Codespaces |
| **Authentication** | Explicit Public Sandbox Access with prominent Demo Banner | Server-side ERPNext/Frappe credential validation & role enforcement |
| **Network Error Handling** | Clear notice instructing user to start backend or use Demo Sandbox | Strict 401/403 rejection; never creates sessions on network errors |
| **Anomaly Engine** | Client-side simulated anomaly scoring and chart visualization | Scikit-learn Isolation Forest ML, statistical Z-Score, RapidFuzz |
| **ERP Integration** | Mock ledger fixtures | Live Frappe REST API sync with `GL Entry`, `Journal Entry`, `Payment Entry` |
| **LLM Diagnostics** | Pre-rendered forensic audit briefs | Live Google Gemini API inference for ad-hoc audit brief synthesis |

---

## Key Features

| Feature | Description |
|---|---|
| 🤖 **ML Anomaly Detection** | Isolation Forest trained on your own GL data — no labelled fraud data required |
| 📏 **10 Rule-Based Checks** | Round amounts, off-hours postings, weekend entries, zero/negative amounts, high velocity, self-transfers, and more |
| 🔍 **Fuzzy Duplicate Detection** | RapidFuzz token-sort matching catches near-duplicate invoices and double payments |
| 💬 **Explainable Alerts** | Every alert includes a plain-English summary, bullet-point reasons, and a recommended action |
| 🧠 **Gemini LLM Forensic Briefs** | LLM-synthesized fraud hypotheses, auditor cross-examination probes, and internal control recommendations powered by Google Gemini |
| 🎯 **Composite Risk Scoring** | Configurable weighted score combining ML (40%) + Rules (35%) + Duplicates (25%) |
| 🔄 **Investigation Workflow** | Open → In Progress → Escalated → Closed with full audit trail |
| 📊 **Live Risk Dashboard** | Animated KPI cards, interactive trend charts, top-alerts table, party risk map |
| ⚡ **Real-Time Hooks** | `on_submit` hooks on Journal Entry and Payment Entry for instant rule-based screening |
| 📅 **Scheduled Scans** | Daily full ML scan + hourly delta scan, fully automated via Frappe scheduler |
| ⚙️ **Configurable Settings** | All thresholds, weights, and notification preferences in a single Settings doctype |

---

## Architecture

```
ERPNext GL / Journal Entry / Payment Entry
          │
          ▼  (on_submit hook — real-time)
  ┌───────────────────────────────────────────────────────────────┐
  │                    FinGuard AI Pipeline                       │
  │                                                               │
  │  1. Feature Engineering   ──▶  pandas DataFrame              │
  │     • Amount, velocity, temporal, account-type features      │
  │                                                               │
  │  2. Isolation Forest      ──▶  ML anomaly score [0–1]        │
  │     • Trained on 90-day rolling window of your own data      │
  │                                                               │
  │  3. Rule Engine           ──▶  rule score + triggered codes  │
  │     • 10 deterministic checks, weighted severity             │
  │                                                               │
  │  4. Duplicate Detector    ──▶  duplicate flag + similarity   │
  │     • RapidFuzz token-sort on (party + amount + date + narr) │
  │                                                               │
  │  5. Composite Scorer      ──▶  weighted risk score [0–1]     │
  │     • ML×40% + Rules×35% + Duplicate×25%                    │
  │                                                               │
  │  6. Explainer             ──▶  plain-English explanation     │
  │     • Summary, reasons list, recommended action              │
  └───────────────────────────────────────────────────────────────┘
          │
          ▼
  Financial Anomaly Alert (Frappe DocType)
          │
          ▼
  Investigation Workflow ──▶ Close / Escalate / False Positive
          │
          ▼
  FinGuard AI Risk Dashboard (Live ERPNext Page)
```

---

## ML Pipeline Detail

| Stage | Technology | Output |
|---|---|---|
| Feature Engineering | pandas + numpy | 14-column numeric DataFrame per transaction |
| Anomaly Scoring | scikit-learn IsolationForest (`n_estimators=200`) | Float score in \[0, 1\] |
| Rule Checks | Pure Python deterministic rules | List of triggered rule codes |
| Duplicate Detection | RapidFuzz `token_sort_ratio` | Boolean flag + similarity % |
| Explainability | Template-based NLG | Plain-English summary + reasons |
| Composite Score | Configurable weighted average | Final risk score in \[0, 1\] |

---

## Anomaly Detection Rules

| Rule Code | Description | Default Severity |
|---|---|---|
| `ROUND_AMOUNT` | Amount divisible by 1,000 | Medium |
| `LARGE_AMOUNT` | Amount > ₹5,00,000 (configurable) | High |
| `OFF_HOURS_POSTING` | Posted before 08:00 or after 20:00 | Medium-High |
| `WEEKEND_POSTING` | Posted on Saturday or Sunday | Medium |
| `ZERO_AMOUNT` | Amount is exactly zero | High |
| `NEGATIVE_AMOUNT` | Amount is negative | High |
| `HIGH_VELOCITY_3D` | >5 transactions from same party in 3 days | High |
| `SELF_TRANSFER` | Debit and credit parties appear identical | Critical |
| `MISSING_NARRATION` | No description/narration provided | Low |
| `UNUSUAL_ACCOUNT_COMBINATION` | Debit and credit accounts share the same type | Medium |

---

## Screenshots

> 📸 **Dashboard Preview** — FinGuard AI Risk Dashboard showing animated KPI cards, risk trend line chart, top alerts table, and party risk heat map.

*Screenshots available after deployment. See [Docker Quick Start](#docker-quick-start) to run locally.*

---

## Installation

### Prerequisites

- ERPNext v14 or v15 (Frappe Framework)
- Python 3.10+
- Redis
- MariaDB 10.6+

### Via Bench (Recommended)

```bash
# 1. Get the app
bench get-app finance_ai https://github.com/premsinghrahangdale/finguard-ai-erpnext

# 2. Install on your site
bench --site your-site.local install-app finance_ai

# 3. Migrate database
bench --site your-site.local migrate

# 4. Restart
bench restart
```

After installation, FinGuard AI creates default settings automatically and adds a **FinGuard AI** workspace to your ERPNext home screen.

---

## Docker Quick Start

Get a full ERPNext + FinGuard AI environment running in minutes:

```bash
# 1. Clone the repository
git clone https://github.com/premsinghrahangdale/finguard-ai-erpnext.git
cd finguard-ai-erpnext

# 2. Start all services (MariaDB, Redis, ERPNext, Worker, Scheduler)
docker compose up -d

# 3. Watch the setup logs (first run takes 3–5 minutes)
docker compose logs -f frappe-web

# 4. Once you see "Serving on http://0.0.0.0:8000" open:
#    http://localhost:8000
#    Login: Administrator / admin

# 5. Navigate to FinGuard AI workspace and run a manual scan
```

To stop:
```bash
docker compose down
```

To reset everything (wipe data):
```bash
docker compose down -v
```

---

## Configuration

Navigate to **FinGuard AI → FinGuard Settings** in ERPNext to configure:

### Scoring Weights
| Setting | Default | Description |
|---|---|---|
| ML Weight | 40% | Isolation Forest contribution |
| Rule Weight | 35% | Rule engine contribution |
| Duplicate Weight | 25% | Duplicate detection contribution |

> ⚠️ Weights must sum to exactly 100.

### Thresholds
| Setting | Default | Description |
|---|---|---|
| High Risk Threshold | 0.80 | Composite score above this = High Risk |
| Medium Risk Threshold | 0.50 | Composite score above this = Medium Risk |
| Large Amount Threshold | ₹5,00,000 | Triggers `LARGE_AMOUNT` rule |
| Lookback Days | 90 | ML training window for full scan |
| IForest Contamination | 0.05 | Expected anomaly fraction (5%) |

### Duplicate Detection
| Setting | Default | Description |
|---|---|---|
| Similarity Threshold | 85% | Narration fuzzy-match threshold |
| Date Window | 3 days | How close dates must be |

---

## Usage

### Automatic Scanning

After installation, scanning happens automatically:
- **Hourly delta scan** — checks transactions from the last 24 hours using rules only (fast)
- **Daily full scan** — retrains the Isolation Forest model and scans all transactions in the lookback window

### Manual Scan from Dashboard

1. Navigate to **FinGuard AI → Risk Dashboard**
2. Set company and date range filters
3. Click **Run Manual Scan**
4. Wait for completion — alert counts update live

### Investigating an Alert

1. Open any **Financial Anomaly Alert** record
2. Read the AI-generated summary and reasons
3. Click **Escalate** to create an **Anomaly Investigation** record
4. Add investigation notes and evidence links
5. Close as **Confirmed Anomaly** or **False Positive**

### Resolving Alerts

- **False Positive** — marks the alert as a known-good transaction
- **Resolved** — confirms the issue has been addressed
- Both statuses are excluded from the open alerts count on the dashboard

---

## Development

### Setup (Local, No Frappe)

```bash
# 1. Clone
git clone https://github.com/premsinghrahangdale/finguard-ai-erpnext.git
cd finguard-ai-erpnext

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run unit tests
pytest tests/unit/ -v --tb=short
```

### Project Structure

```
finguard-ai-erpnext/
├── finance_ai/                        # Frappe app package
│   ├── hooks.py                       # Lifecycle hooks (events, scheduler)
│   ├── install.py                     # Post-install setup
│   ├── anomaly_engine/                # Pure-Python ML pipeline
│   │   ├── features.py                # Feature engineering (14 features)
│   │   ├── isolation_forest.py        # IForest model wrapper
│   │   ├── rule_engine.py             # 10 deterministic rules
│   │   ├── duplicate_detector.py      # Fuzzy duplicate detection
│   │   ├── explainer.py               # Plain-English explanations
│   │   ├── scorer.py                  # Composite risk scorer
│   │   └── scanner.py                 # Frappe integration layer
│   ├── finance_ai/
│   │   ├── doctype/
│   │   │   ├── financial_anomaly_alert/   # Main alert record
│   │   │   ├── anomaly_investigation/     # Investigation workflow
│   │   │   ├── anomaly_model_log/         # Scan run log
│   │   │   ├── finguard_settings/         # Global config (singleton)
│   │   │   └── investigation_evidence_item/ # Child: evidence links
│   │   ├── page/finguard_dashboard/       # Interactive risk dashboard
│   │   └── report/
│   │       ├── anomaly_summary_report/    # Detailed alert report
│   │       └── risk_score_trend/          # Daily trend report
│   ├── api/
│   │   ├── dashboard.py               # Dashboard REST endpoints
│   │   └── investigation.py           # Investigation endpoints
│   ├── public/
│   │   ├── css/finguard.css           # Animated dashboard styles
│   │   └── js/finguard.js             # Shared JS utilities
│   └── scheduled_tasks/
│       └── run_anomaly_scan.py        # Full scan + delta scan
├── tests/
│   ├── conftest.py                    # 20 realistic test transactions
│   └── unit/                         # pytest unit tests (no Frappe)
│       ├── test_features.py           # 13 tests
│       ├── test_rule_engine.py        # 14 tests
│       ├── test_duplicate_detector.py # 10 tests
│       ├── test_scorer.py             # 10 tests
│       ├── test_explainer.py          # 7 tests
│       └── test_isolation_forest.py   # 11 tests
├── requirements.txt
├── setup.py
├── docker-compose.yml
└── .github/workflows/ci.yml
```

---

## API Reference

All endpoints are accessible at `/api/method/<endpoint>` with ERPNext session auth.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `finance_ai.api.dashboard.get_dashboard_summary` | GET | Accounts User | KPI summary for dashboard |
| `finance_ai.api.dashboard.get_risk_trend` | GET | Accounts User | Daily risk trend data for chart |
| `finance_ai.api.dashboard.get_top_alerts` | GET | Accounts User | Top N open alerts by score |
| `finance_ai.api.dashboard.get_rule_breakdown` | GET | Accounts User | Rule trigger frequency counts |
| `finance_ai.api.dashboard.get_party_risk_map` | GET | Accounts User | Top parties by alert count |
| `finance_ai.api.dashboard.run_manual_scan` | POST | Accounts Manager | Trigger a manual full scan |
| `finance_ai.api.investigation.get_alert_details` | GET | Accounts User | Full alert details + source doc |
| `finance_ai.api.investigation.get_source_document` | GET | Accounts User | Source JE / PE fields |
| `finance_ai.api.investigation.update_alert_status` | POST | Accounts User | Update alert status |
| `finance_ai.api.investigation.get_similar_transactions` | GET | Accounts User | Similar transactions in window |

---

## Testing

```bash
# Run all unit tests
pytest tests/unit/ -v

# With coverage report
pytest tests/unit/ --cov=finance_ai/anomaly_engine --cov-report=html
open htmlcov/index.html

# Run a specific test module
pytest tests/unit/test_rule_engine.py -v

# Run tests matching a pattern
pytest tests/unit/ -k "duplicate" -v
```

**Test coverage targets:**

| Module | Tests | Coverage Target |
|---|---|---|
| `features.py` | 13 | ≥ 90% |
| `rule_engine.py` | 14 | ≥ 95% |
| `duplicate_detector.py` | 10 | ≥ 90% |
| `scorer.py` | 10 | ≥ 95% |
| `explainer.py` | 7 | ≥ 85% |
| `isolation_forest.py` | 11 | ≥ 85% |

---

## Disclaimer

FinGuard AI is designed to assist finance professionals in identifying transactions that warrant further investigation. It uses statistical and machine learning methods to surface patterns that deviate from typical activity in your data.

**FinGuard AI does not:**
- Confirm or allege fraud, financial crime, or employee misconduct
- Replace human judgment or a formal financial audit
- Guarantee detection of all anomalies or risks

All alerts generated by FinGuard AI are *potential risk indicators* only. Investigation and final decisions rest entirely with qualified finance and compliance personnel.

---

## Contributing

Pull requests are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for new ML logic (no Frappe required for unit tests)
4. Run `pytest tests/unit/` and `flake8 finance_ai/ --max-line-length=120`
5. Submit a PR against `develop`

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

Built with:
- [Frappe Framework](https://frappeframework.com/) & [ERPNext](https://erpnext.com/)
- [scikit-learn](https://scikit-learn.org/) — Isolation Forest
- [RapidFuzz](https://github.com/maxbachmann/RapidFuzz) — Fuzzy string matching
- [pandas](https://pandas.pydata.org/) & [NumPy](https://numpy.org/) — Data processing
- [joblib](https://joblib.readthedocs.io/) — Model persistence

---

<p align="center">
  Made with ♥ by <strong>Premsingh Rahangdale</strong> · FinGuard AI
  <br>
  <em>Detect anomalies. Explain risks. Protect financial integrity.</em>
</p>
