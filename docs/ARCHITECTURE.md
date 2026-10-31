# MediFlow Architecture Overview

## Application Foundation

MediFlow is built as a modular monolith providing multi-facility medicine inventory intelligence, redistribution, and QR verification.

### Tech Stack
- **Frontend:** Next.js (App Router, JavaScript `.js`/`.jsx` only, Tailwind CSS, Recharts)
- **Backend:** Python FastAPI, Pydantic V2, SQLAlchemy, Alembic
- **Database:** YugabyteDB YSQL (PostgreSQL-compatible) with SQLite development fallback
- **AI Stack:** LangGraph agent workflow, Google Gemini structured reasoning, MEKO shared operational memory
- **Traceability:** Platform-issued HMAC-signed serialized QR verification tokens

### Layer Structure
- `frontend/app/`: Next.js pages, layouts, and views
- `frontend/components/`: Reusable UI components (Navbar with Health indicator, Sidebar, badges, metric cards)
- `frontend/hooks/`: React hooks including `useApiHealth`
- `frontend/lib/`: API client (`api.js`) targeting `/api/v1`
- `backend/app/api/`: Versioned route controllers (`/api/v1/`)
- `backend/app/core/`: Configuration, security, database connection pooling
- `backend/app/models/`: SQLAlchemy ORM entity definitions
- `backend/app/schemas/`: Pydantic request/response validation schemas
- `backend/app/repositories/`: Data access layer
- `backend/app/services/`: Deterministic business logic (inventory, forecasts, risks, matching, QR)
- `backend/app/agents/`: LangGraph multi-agent coordination
- `backend/app/integrations/`: Gemini and MEKO client adapters with graceful fallbacks
