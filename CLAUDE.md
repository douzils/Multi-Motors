# CLAUDE.md — Multi-Motors AI

## Project Overview

Multi-Motors AI is a Python-based autonomous web scraping service that discovers, extracts, and catalogs FPV drone brushless motor specifications into a Google Sheets database. It runs continuously, scanning on a configurable interval (default: 60 minutes).

## Tech Stack

- **Language:** Python 3.10+
- **Web Scraping:** BeautifulSoup4, requests, lxml
- **Search:** duckduckgo-search (no API key required)
- **Database:** Google Sheets via gspread + google-auth
- **Scheduling:** schedule library
- **Config:** python-dotenv (.env files)

## Repository Structure

```
Multi-Motors/
├── CLAUDE.md                 # This file
├── README.md                 # User-facing docs (French)
├── .env.example              # Environment variable template
├── .gitignore
└── multi_motors_ai/          # Main application package
    ├── __init__.py
    ├── main.py               # Entry point, scheduler, orchestration
    ├── config.py             # Configuration constants, env loading
    ├── models.py             # MotorSpec dataclass
    ├── parser.py             # Regex-based spec extraction (~20 patterns)
    ├── sheets.py             # Google Sheets API integration (SheetsManager)
    ├── requirements.txt      # Python dependencies
    └── scrapers/
        ├── __init__.py
        ├── base.py           # BaseScraper abstract class (HTTP, parsing utils)
        ├── search_engine.py  # DuckDuckGo discovery (SearchEngineScraper)
        └── shop_scraper.py   # Shop + manufacturer scrapers
```

## Key Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r multi_motors_ai/requirements.txt
cp .env.example .env

# Run the application
python -m multi_motors_ai.main

# Stop gracefully
Ctrl+C
```

## Architecture & Data Flow

1. **Discovery** — DuckDuckGo searches by brand/stator size (`SearchEngineScraper`)
2. **Shop scraping** — Crawls 5 FPV retailers (`ShopScraper`)
3. **Manufacturer scraping** — Visits manufacturer product pages (`ManufacturerScraper`)
4. **Parsing** — Regex extraction of specs from HTML text/tables (`parser.py`)
5. **Deduplication** — By REF field (format: `BRAND-STATOR-KV`)
6. **Validation** — Requires marque, kv, and classe fields (`MotorSpec.is_valid()`)
7. **Insert** — Batch write to Google Sheets (`SheetsManager.add_motors()`)

### Class Hierarchy

- `BaseScraper` — HTTP session, delays, HTML parsing utilities
  - `SearchEngineScraper` — DuckDuckGo-based motor discovery
  - `ShopScraper` — FPV shop product link extraction
  - `ManufacturerScraper` — Direct manufacturer site scraping

### Core Model

`MotorSpec` (dataclass in `models.py`) — 30 fields matching Google Sheet columns:
- `generate_ref()` — Creates unique ID like `EMAX-2207-1900`
- `to_sheet_row()` — Converts to spreadsheet row list
- `is_valid()` — Checks minimum required fields
- `completeness_score()` — Returns 0–1 fill ratio for prioritization

## Configuration

All config lives in `config.py`, loaded from `.env` with defaults:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SPREADSHEET_ID` | (preset) | Target Google Sheet |
| `SHEET_GID` | (preset) | Target worksheet tab |
| `GOOGLE_CREDENTIALS_FILE` | `credentials.json` | Service account key path |
| `SCAN_INTERVAL_MINUTES` | `60` | Minutes between scan cycles |
| `REQUEST_DELAY_MIN` | `2` | Min seconds between HTTP requests |
| `REQUEST_DELAY_MAX` | `5` | Max seconds between HTTP requests |
| `MAX_RESULTS_PER_SEARCH` | `30` | Max results per DuckDuckGo query |
| `LOG_LEVEL` | `INFO` | Logging level |

## Conventions & Patterns

### Code Style
- Follows PEP 8 informally (no formatter/linter configured)
- Type hints used on dataclass fields and function signatures
- Docstrings on classes and key functions
- French column names and terminology (MARQUE, NOM, CLASSE, POIDS, etc.)
- README is in French

### Error Handling
- Try/except around scraping operations — individual failures don't halt the cycle
- Batch insert falls back to individual row inserts on failure
- Graceful shutdown via SIGINT/SIGTERM signal handlers

### Logging
- Dual output: stdout + `multi_motors_ai.log` file
- Per-module loggers via `logging.getLogger(__name__)`
- Configurable level via `LOG_LEVEL` env var

### Web Scraping Etiquette
- Random delays (2–5s) between requests
- Realistic User-Agent header
- URL filtering to skip non-product sites (YouTube, Amazon, Reddit, etc.)

### Secrets Management
- `credentials.json`, `.env`, and key files are in `.gitignore`
- Google Service Account authentication (OAuth2)
- Never commit API keys or credential files

## Testing & CI

No test suite or CI/CD pipeline exists currently. There are no `pytest`, `tox`, or GitHub Actions configurations. If adding tests:
- Create a `tests/` directory at project root
- Use `pytest` as the test runner
- Mock external dependencies: Google Sheets API (`gspread`), HTTP requests (`requests`), DuckDuckGo search
- Focus on `parser.py` (regex patterns) and `models.py` (validation logic) as high-value test targets

## Important Notes for AI Assistants

- The application requires a valid `credentials.json` (Google Service Account key) to run — it cannot be executed without Google Cloud credentials
- The data model has 30 columns defined in `config.SHEET_COLUMNS` — keep `MotorSpec` fields and `to_sheet_row()` in sync with this list
- Parser regex patterns in `parser.py` are the most complex and fragile part of the codebase — test changes thoroughly
- Brand list (`MOTOR_BRANDS`) and stator sizes (`STATOR_SIZES`) in `config.py` define the search scope — extend these lists to add new brands/sizes
- Shop scraper URLs in `SCRAPE_SOURCES` dict may break if retailers change their site structure
- The deduplication key is the REF field — changes to `generate_ref()` logic affect duplicate detection
