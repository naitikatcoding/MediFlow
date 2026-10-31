# MediFlow

**Multi-facility medicine inventory intelligence, redistribution, and QR traceability platform.**

MediFlow coordinates medicine inventory across fictional hospitals, diagnostic centres, and pharmacies. It forecasts demand from historical consumption, detects stockout and expiry risk, finds safe same-product surplus-to-need matches, facilitates source and destination human approvals, reserves stock, tracks dispatch and receipt through platform QR labels, and records an auditable inventory ledger.

---

## 🛠 Technology Stack

- **Frontend:** Next.js (App Router, JavaScript `.js` / `.jsx` only — no TypeScript), Tailwind CSS, Recharts, Lucide Icons, html5-qrcode.
- **Backend:** Python 3.10+ FastAPI, Pydantic V2, SQLAlchemy, Alembic.
- **Database:** YugabyteDB YSQL (PostgreSQL-compatible) with SQLite development fallback.
- **AI Stack:** LangGraph agent workflow, Google Gemini structured reasoning, MEKO shared operational knowledge and memory (with automated fallback when keys are absent).
- **Testing:** Pytest for backend and Next.js/ESLint tooling for frontend.

---

## 📁 Repository Structure

```text
MediFlow/
├── Frontend/                 # Next.js App Router (JavaScript only)
│   ├── app/                  # Application routes, layout, and views
│   ├── components/           # UI components (Navbar with Health indicator, Sidebar, badges)
│   ├── hooks/                # Custom React hooks (useApiHealth)
│   ├── lib/                  # API client (lib/api.js targeting /api/v1)
│   ├── public/               # Static assets & SVG icons
│   └── styles/               # Global CSS styles
├── Backend/                  # Python FastAPI Backend
│   ├── app/
│   │   ├── api/routes/       # Versioned API routes (/api/v1/*)
│   │   ├── core/             # Configuration, database, and security
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic V2 domain validation schemas
│   │   ├── repositories/     # Data access layer
│   │   ├── services/         # Deterministic business logic & workflows
│   │   ├── agents/           # LangGraph multi-agent coordination
│   │   └── integrations/     # Gemini and MEKO adapters with fallbacks
│   ├── alembic/              # Alembic database migrations
│   ├── migrations/           # Database migration wrapper
│   └── tests/                # Pytest suite
├── data/
│   └── seed/                 # Synthetic baseline seed fixtures
├── scripts/                  # Cross-platform development & run scripts
├── docs/                     # Engineering documentation & architecture
├── infra/                    # Docker & deployment configurations
├── .env.example              # Central configuration template
└── README.md
```

---

## 🚀 Quick Start & Installation

### Prerequisites
- **Node.js:** v18.0.0 or later (v20+ recommended)
- **Python:** 3.10, 3.11, or 3.12+

---

### 1. Setup Backend

1. Navigate to the `Backend` directory:
   ```bash
   cd Backend
   ```
2. Create and activate a Python virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   When starting the backend with `run.py` or the repository scripts, a repository-root `.env` is loaded first when present; `Backend/.env` remains the fallback. Values already exported in the process environment take precedence.

---

### 2. Setup Frontend

1. Navigate to the `Frontend` directory:
   ```bash
   cd Frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Configure environment variables:
   ```bash
   cp .env.example .env.local
   ```

---

## 🏃 Running the Applications

### Option A: Run Services Independently

**Terminal 1 — Backend (FastAPI on Port 8000):**
```bash
# From repository root (Windows):
scripts\run_backend.bat

# Or directly:
cd Backend
python run.py
```
Backend API will be available at: `http://127.0.0.1:8000`  
Interactive OpenAPI documentation: `http://127.0.0.1:8000/docs`

**Terminal 2 — Frontend (Next.js on Port 3000):**
```bash
# From repository root (Windows):
scripts\run_frontend.bat

# Or directly:
cd Frontend
npm run dev
```
Frontend web application will be available at: `http://localhost:3000`

---

### Option B: Run via Root Scripts

Using the cross-platform launcher in `scripts/dev.py` or root `package.json`:

```bash
# Run both concurrently:
python scripts/dev.py all
# Or with npm:
npm run dev

# Run backend only:
python scripts/dev.py backend
# Or with npm:
npm run dev:backend

# Run frontend only:
python scripts/dev.py frontend
# Or with npm:
npm run dev:frontend
```

---

## 🩺 System Health & Connectivity

- **Health Endpoints:**
  - `GET http://127.0.0.1:8000/health`
  - `GET http://127.0.0.1:8000/api/v1/health`
- **Frontend Indicator:**  
  The top navigation bar features a real-time connectivity status pill (`API Online` / `Connecting...` / `API Offline`). Hovering displays database dialect (`PostgreSQL/YugabyteDB` or `SQLite dev fallback`), adapter status, and service latency.

---

### YugabyteDB connection budget and fallback

- Each backend process uses one SQLAlchemy engine with a bounded YSQL pool: **2 pooled connections + at most 1 overflow connection**. Pool pre-ping is enabled, connections recycle after 15 minutes, and new connections time out after 5 seconds.
- The maximum application pool use is **3 × worker processes × backend replicas**. The supplied launch scripts, Docker image, and Compose service run one worker by default, so one instance uses at most **3** application connections. For a free-tier/demo cluster, keep one worker and one backend replica unless you have confirmed a larger cluster connection budget.
- Request dependencies close their sessions in `finally`; synchronous agent workflows reuse the request session and release its transaction before calling Gemini. No autonomous or scheduled agent workers open database sessions.
- In development/test, a failed YSQL startup probe or runtime connection/pool failure switches future requests in that worker process to `Backend/mediflow.db` and logs the switch. Each worker has independent failover state. The request that encountered the failure is **not retried**, because retrying writes could duplicate operations.
- SQLite is a local, separate database; fallback data does not replicate back to YugabyteDB. In `APP_ENV=production`, fallback is disabled by default and the service fails closed. Set `DB_SQLITE_FALLBACK=true` only when that data divergence is explicitly acceptable.
- The demo reset API refuses to drop tables on YugabyteDB. The seed script also refuses a remote destructive reset unless `--allow-remote-reset` is explicitly supplied. Tests force a local SQLite URL before importing the app.

## 🧪 Running Tests

### Backend Tests (Pytest)
```bash
# Run all tests:
pytest Backend/tests

# Or from root via npm:
npm run test:backend
```

### Frontend Build Validation
```bash
cd Frontend
npm run build
```

---

## 🔒 Configuration & Environment Variables

| Variable | Description | Default / Example |
|---|---|---|
| `APP_ENV` | Application environment | `development` |
| `DB_POOL_SIZE` | Maximum persistent YSQL connections per process (capped at 2) | `2` |
| `DB_MAX_OVERFLOW` | Maximum temporary YSQL overflow connections per process (capped at 1) | `1` |
| `DB_SQLITE_FALLBACK` | Override the environment-based SQLite fallback policy | `false` in production by default |
| `DATABASE_URL` | Operational DB connection | `sqlite:///./mediflow.db` or `postgresql://yugabyte:yugabyte@localhost:5433/mediflow` |
| `GEMINI_API_KEY` | Google Gemini API key (optional for fallback) | `your_gemini_api_key_here` |
| `GEMINI_MODEL` | Gemini model variant | `gemini-2.5-flash` |
| `MEKO_API_KEY` | MEKO shared memory API key (optional for fallback) | `your_meko_api_key_here` |
| `MEKO_BASE_URL` | MEKO API base URL | `https://api.mekodata.ai/v1` |
| `NEXT_PUBLIC_API_URL` | Frontend client target URL | `http://127.0.0.1:8000` |
| `CORS_ORIGINS` | Permitted browser origins | `http://localhost:3000,http://127.0.0.1:3000` |

---

## 🛡 Disclaimer
MediFlow is a prototype demonstration platform. All facilities, stock records, batch numbers, and consumption histories are synthetic simulations. Real clinical or medical decisions should not be based on this prototype.
