# Agent Memory — Wheel Tracker Project

> Last updated: 2026-03-02  
> Purpose: Context file for any AI agent picking up this project. Read this first.

---

## 1. What This Project Is

**Wheel Tracker** is a personal options-trading dashboard for tracking the [Wheel Strategy](https://www.investopedia.com/terms/w/wheel-strategy.asp) and a PMCC (Poor Man's Covered Call / "Futuristic Wheel") strategy. Data is sourced from Interactive Brokers (IBKR) Flex Reports. The live site is at **https://wheel-tracker.win**.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite), React Router, Recharts |
| Backend | Python 3.11, FastAPI, APScheduler |
| Database | AWS DynamoDB (eu-central-1) |
| Auth | Google OAuth2 (ID token verified server-side) |
| Infra | Docker Compose, Nginx (reverse proxy + TLS) |
| Hosting | AWS EC2 (Amazon Linux), single instance |
| Live Market Data | Alpha Vantage REST API |

---

## 3. Repository & Branch

- **GitHub:** `https://github.com/Cloud956/wheel-tracker`
- **Active branch:** `towards_the_finish_line`
- The `main` branch is not used for development.

---

## 4. Deployment

### Server details
| Field | Value |
|---|---|
| Cloud | AWS EC2 (eu-central-1) |
| IP | `18.198.2.105` |
| OS user | `ec2-user` |
| SSH key file | `wheel-key-v2.pem` (in repo root — **gitignored**) |
| App dir on server | `/home/ec2-user/wheel-tracker` |
| Domain | `wheel-tracker.win` (HTTPS via Nginx + certs in `./certs/`) |

### Full deploy command (from local machine)
```bash
# 1. Push code to GitHub
git add <files>
git commit -m "your message"
git push

# 2. SSH in and pull + rebuild
ssh -i wheel-key-v2.pem -o StrictHostKeyChecking=no ec2-user@18.198.2.105 \
  "cd /home/ec2-user/wheel-tracker && git pull && docker compose -f docker-compose.prod.yml up -d --build 2>&1"
```

### Docker Compose services (prod)
| Container | Role | Internal port |
|---|---|---|
| `wheel-tracker-backend` | FastAPI app | 8000 |
| `wheel-tracker-frontend` | Node/Express static server | 3000 |
| `wheel-tracker-nginx` | Reverse proxy, TLS termination | 80 / 443 |

Nginx routes:
- `https://wheel-tracker.win/api/*` → backend:8000
- `https://wheel-tracker.win/*` → frontend:3000

### Useful SSH commands on server
```bash
# View running containers
docker ps

# Tail backend logs
docker logs -f wheel-tracker-backend

# Restart without rebuild
docker compose -f docker-compose.prod.yml restart
```

---

## 5. Environment Variables

Stored in `.env` (repo root — **gitignored**, never commit this).

```dotenv
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=eu-central-1
DYNAMODB_USER_TABLE_NAME=wheel_tracker_users
DYNAMODB_WHEEL_TABLE_NAME=Wheels
ALPHA_VANTAGE_API_KEY=OSM5S1XLFP21EZMB    # Free tier — 25 req/day
```

The `.env` file is loaded by `docker-compose.prod.yml` via `env_file: - .env` and injected into the backend container.

---

## 6. AWS DynamoDB Tables

All tables in **eu-central-1**. Primary key is always `username` (user's Google email).

| Table env var | Default name | Contents |
|---|---|---|
| `DYNAMODB_USER_TABLE_NAME` | `wheel_tracker_users` | Per-user config: IBKR token, query_id, LEAP deltas, auto-sync flag |
| `DYNAMODB_WHEEL_TABLE_NAME` | `Wheels` | Full wheel objects (trades, positions, P&L) |
| `DYNAMODB_SNAKE_TABLE_NAME` | `snake_highscores` | Snake game leaderboard |
| `DYNAMODB_DAILY_PNL_TABLE_NAME` | `daily_pnl` | Daily/cumulative P&L snapshots per user |
| `DYNAMODB_PMCC_SHORT_CALLS_TABLE` | `pmcc_short_calls` | PMCC short call history per user |
| `DYNAMODB_PMCC_LEAP_SNAPSHOTS_TABLE` | `pmcc_leap_snapshots` | Daily LEAP position snapshots |

---

## 7. Authentication

- Frontend sends a **Google ID token** in the `Authorization: Bearer <token>` header.
- Backend (`auth.py`) verifies the token against Google's servers using `google.oauth2.id_token`.
- Google Client ID (hardcoded fallback in `auth.py`): `992920333249-jl7q5rghgbb09g3r2mjdqgorho0bnjkb.apps.googleusercontent.com`
- No passwords or JWTs — pure Google OAuth2.

---

## 8. Backend Structure (`backend/`)

```
main.py               # FastAPI app, scheduler, all non-router endpoints
auth.py               # verify_token dependency, format_currency helper
database.py           # All DynamoDB read/write functions
models.py             # Pydantic models: Trade, Wheel, CategorizedTrade, etc.
trade_categorizer.py  # Fetches IBKR Flex report XML, parses trades + positions
wheel_analyzer.py     # Wheel lifecycle logic: identify, merge, process, enrich
pmcc_analyzer.py      # PMCC/LEAP logic: parse_leap_positions, build_pmcc_short_calls
routers/
  account.py          # GET/PUT /account — user config (IBKR credentials etc.)
  futuristic_wheel.py # All /futuristic-wheel/* endpoints
```

### Main API endpoints (`main.py`)
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check (no auth) |
| GET | `/sync` | Fetch IBKR Flex report, categorise trades, save/update wheels |
| GET | `/wheel-summary` | All wheels with full trade history |
| GET | `/history` | Flat trade history across all wheels |
| GET | `/analytics` | Aggregate stats (win rate, P&L by symbol/month, etc.) |
| GET | `/pnl` | Daily P&L time-series records |
| GET | `/clear-data` | Delete all wheel data for the user |
| POST | `/snake/highscore` | Submit snake game score (no auth) |
| GET | `/snake/highscores` | Top 10 snake scores (no auth) |

### Futuristic Wheel endpoints (`routers/futuristic_wheel.py`)
| Method | Path | Description |
|---|---|---|
| GET | `/futuristic-wheel` | All PMCC data: current LEAPs, short call history, P&L series |
| POST | `/futuristic-wheel/sync` | Fetch Flex report and update LEAP snapshots + short calls |
| PUT | `/futuristic-wheel/delta` | Save manual per-contract delta for a symbol |
| PUT | `/futuristic-wheel/auto-sync` | Toggle nightly auto-sync for this user |
| DELETE | `/futuristic-wheel/purge-calls` | Delete all PMCC short call records |
| GET | `/futuristic-wheel/market-data` | **Fetch live price + greeks from Alpha Vantage (manual button)** |

### Nightly Scheduler
- Runs at **02:00 Europe/Berlin** via APScheduler.
- For every user with IBKR credentials:
  1. Fetches Flex report once.
  2. If `pmcc_auto_sync` enabled: runs PMCC sync.
  3. Refreshes wheel positions, computes and saves daily P&L snapshot.

---

## 9. Frontend Structure (`frontend/src/`)

```
App.jsx               # Router: /, /dashboard, /analytics, /pnl, /futuristic-wheel, /account, /snake
components/
  Home.jsx            # Landing page with Google Sign-In
  Dashboard.jsx       # Main wheel dashboard (sync button, wheel summary table)
  AnalyticsPage.jsx   # Analytics charts and stats
  PnlPage.jsx         # Daily P&L chart
  FuturisticWheel.jsx # PMCC/LEAP tracker (see section 10)
  AccountSettings.jsx # IBKR token/query_id configuration
  SnakeGame.jsx       # Easter egg snake game with leaderboard
  WheelSummaryTable.jsx
  TradeHistoryTable.jsx
  Table.jsx
  logins/login.jsx    # Google OAuth button
  logins/logout.jsx
```

Authentication state is stored in a `token` **cookie** (set on login, read by all API calls with `Cookies.get('token')`).

---

## 10. Futuristic Wheel (PMCC) Feature — Detailed

This is the most complex feature. It tracks a **Poor Man's Covered Call** strategy:
- Long-dated CALL LEAPs (deep ITM, acts like stock exposure)
- Short-dated short calls sold against them

### Data flow
1. User clicks **Sync** → `POST /futuristic-wheel/sync` → fetches IBKR Flex report → saves LEAP snapshot to `pmcc_leap_snapshots`, short calls to `pmcc_short_calls`.
2. `GET /futuristic-wheel` returns current LEAP state, per-symbol stored deltas, short call history, P&L series.
3. Per-symbol delta (Δ) and gamma (Γ) can be:
   - **Manual:** User types a delta value into the input box and clicks Save → `PUT /futuristic-wheel/delta`.
   - **Live (Alpha Vantage):** User clicks **📡 Live Data** → `GET /futuristic-wheel/market-data` → fetches underlying price via `GLOBAL_QUOTE` and greeks via `REALTIME_OPTIONS`, matched by strike + expiry. **This is intentionally manual to stay within the 25 req/day free tier.**

### LEAP expiry format
IBKR delivers expiry as `YYYYMMDD` (e.g. `20270115`). The backend normalises to `YYYY-MM-DD` before matching against Alpha Vantage. Frontend has a `normalizeExpiry()` helper for the same purpose.

### Key files for PMCC
- Backend: `backend/routers/futuristic_wheel.py`, `backend/pmcc_analyzer.py`
- Frontend: `frontend/src/components/FuturisticWheel.jsx`, `frontend/src/components/FuturisticWheel.css`

### P&L series start date
`START_DATE = '2026-02-20'` in `futuristic_wheel.py` — the daily cumulative P&L chart starts from this date.

---

## 11. IBKR Integration

- Users configure their **IBKR Flex token** and **Flex query ID** in Account Settings (stored in DynamoDB `wheel_tracker_users` table).
- `trade_categorizer.py` → `fetch_flex_report(token, query_id)` calls the IBKR Flex Web Service and returns XML.
- `parse_trades_from_xml()` and `parse_positions_from_xml()` parse the XML into `Trade` objects and position dicts respectively.

---

## 12. What NOT to Do

- **Do not commit `.env`** — it contains AWS credentials and the Alpha Vantage API key.
- **Do not commit `wheel-key-v2.pem`** — it is the EC2 SSH key.
- Both are already in `.gitignore`.
- Do not call `GET /futuristic-wheel/market-data` in any automated/scheduled way — Alpha Vantage free tier is 25 requests/day.

---

## 13. Local Development

```bash
# Backend (from backend/)
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (from frontend/)
npm install
npm run dev    # Vite dev server on :5173, proxies /api → localhost:8000
```

Dev Docker files are `Dockerfile.dev` (backend) and `Dockerfile.dev` (frontend) — not used in production.
