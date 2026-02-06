"""Google Sheets integration for Multi-Motors catalog.

Each brand has its own worksheet tab (e.g. "1 - 3BHOBBY", "2 - Emax").
Motors are inserted one at a time (drip feed) with delays between each.

Handles 194+ tabs by using batch reads to avoid API rate limits.
"""

import logging
import re
import time
import random
from typing import Optional

import requests

from .config import (
    SPREADSHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_API_KEY,
    SHEET_COLUMNS,
)
from .models import MotorSpec

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Delay between each motor insertion (seconds)
DRIP_DELAY_MIN = 3
DRIP_DELAY_MAX = 8

# Pattern for brand sheet names: "N - BRAND"
SHEET_NAME_RE = re.compile(r"^(\d+)\s*-\s*(.+)$")

# Batch size for reading tabs (stay under 60 reads/min quota)
BATCH_READ_SIZE = 20
BATCH_READ_DELAY = 2  # seconds between batches


class SheetsManager:
    """Manages multi-tab Google Sheet where each tab = one brand.

    Uses batch reads to handle 194+ tabs without hitting API rate limits.
    Only writes to existing tabs (no tab creation needed).
    """

    def __init__(self):
        self._client = None
        self._spreadsheet = None
        self._mode: str = "none"
        # brand (uppercase) -> worksheet object
        self._brand_sheets: dict[str, object] = {}
        # brand (uppercase) -> original brand name (for display)
        self._brand_names: dict[str, str] = {}
        # brand (uppercase) -> set of existing REFs
        self._brand_refs: dict[str, set[str]] = {}
        # All refs across all sheets for quick duplicate check
        self._all_refs: set[str] = set()

    def connect(self):
        if self._try_service_account():
            return
        if self._try_api_key():
            return
        raise RuntimeError("Cannot connect to Google Sheets.")

    def _try_service_account(self) -> bool:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
            )
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open_by_key(SPREADSHEET_ID)
            self._mode = "service_account"
            logger.info("Connected to '%s'", self._spreadsheet.title)
            self._load_all_brand_sheets()
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.warning("Service Account failed: %s", e)
            return False

    def _try_api_key(self) -> bool:
        if not GOOGLE_API_KEY:
            return False
        try:
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
            resp = requests.get(url, params={"key": GOOGLE_API_KEY}, timeout=10)
            resp.raise_for_status()
            self._mode = "api_key"
            logger.info("Connected via API Key (READ-ONLY)")
            return True
        except Exception:
            return False

    def _load_all_brand_sheets(self):
        """Load all brand tabs and their refs using batch reads."""
        self._brand_sheets.clear()
        self._brand_refs.clear()
        self._brand_names.clear()
        self._all_refs.clear()

        worksheets = self._spreadsheet.worksheets()
        logger.info("Found %d worksheet tabs", len(worksheets))

        # Step 1: Map brand names to worksheets (no API calls needed)
        brand_ws_list = []
        for ws in worksheets:
            match = SHEET_NAME_RE.match(ws.title)
            if match:
                brand_name = match.group(2).strip()
                brand_key = brand_name.upper()
                self._brand_sheets[brand_key] = ws
                self._brand_names[brand_key] = brand_name
                self._brand_refs[brand_key] = set()
                brand_ws_list.append((brand_key, ws))

        logger.info("Mapped %d brand tabs", len(brand_ws_list))

        # Step 2: Batch-read column B (REF) from all tabs
        # Process in batches to respect API rate limits
        for batch_start in range(0, len(brand_ws_list), BATCH_READ_SIZE):
            batch = brand_ws_list[batch_start:batch_start + BATCH_READ_SIZE]

            # Build batch ranges: "TabName!B:B" for each tab
            ranges = []
            batch_brands = []
            for brand_key, ws in batch:
                # Quote sheet name for special characters
                safe_title = ws.title.replace("'", "''")
                ranges.append(f"'{safe_title}'!B:B")
                batch_brands.append(brand_key)

            try:
                # Single API call for the whole batch
                result = self._spreadsheet.values_batch_get(ranges)
                value_ranges = result.get("valueRanges", [])

                for i, vr in enumerate(value_ranges):
                    brand_key = batch_brands[i]
                    values = vr.get("values", [])
                    # Skip header row, flatten single-column values
                    refs = set()
                    for row in values[1:]:
                        if row and row[0].strip():
                            refs.add(row[0].strip())
                    self._brand_refs[brand_key] = refs
                    self._all_refs.update(refs)

                loaded_count = sum(len(self._brand_refs[bk]) for bk in batch_brands)
                logger.info(
                    "  Batch %d-%d: loaded %d refs from %d tabs",
                    batch_start + 1,
                    min(batch_start + BATCH_READ_SIZE, len(brand_ws_list)),
                    loaded_count,
                    len(batch),
                )

            except Exception as e:
                logger.warning("Batch read failed (tabs %d-%d): %s",
                               batch_start + 1, batch_start + len(batch), e)
                # Fallback: try reading tabs one by one with delay
                for brand_key, ws in batch:
                    try:
                        time.sleep(1)
                        ref_col = ws.col_values(2)
                        refs = {r.strip() for r in ref_col[1:] if r.strip()}
                        self._brand_refs[brand_key] = refs
                        self._all_refs.update(refs)
                    except Exception as e2:
                        logger.debug("Skip tab '%s': %s", ws.title, e2)

            # Pause between batches to respect rate limits
            if batch_start + BATCH_READ_SIZE < len(brand_ws_list):
                time.sleep(BATCH_READ_DELAY)

        logger.info(
            "Loaded %d brand tabs, %d total motors",
            len(self._brand_sheets),
            len(self._all_refs),
        )

    def _get_brand_sheet(self, brand: str):
        """Get the worksheet for a brand. Returns None if no tab exists."""
        brand_key = brand.upper()
        ws = self._brand_sheets.get(brand_key)
        if ws is None:
            logger.debug("No tab for brand '%s', skipping", brand)
        return ws

    def motor_exists(self, ref: str) -> bool:
        return ref.strip() in self._all_refs

    def drip_add_motor(self, motor: MotorSpec) -> bool:
        """Add a single motor to the correct brand tab with a delay."""
        if not motor.is_valid():
            return False
        if not motor.ref:
            motor.generate_ref()
        if self.motor_exists(motor.ref):
            return False
        if not motor.marque:
            return False
        if self._mode != "service_account":
            logger.warning("Cannot write in %s mode", self._mode)
            return False

        ws = self._get_brand_sheet(motor.marque)
        if ws is None:
            return False

        try:
            row = motor.to_sheet_row()
            ws.append_row(row, value_input_option="USER_ENTERED")

            brand_key = motor.marque.upper()
            self._brand_refs.setdefault(brand_key, set()).add(motor.ref)
            self._all_refs.add(motor.ref)

            logger.info(
                ">> Added: %s | %s %s %sKV | tab='%s' [%.0f%%]",
                motor.ref, motor.marque, motor.nom, motor.kv,
                ws.title, motor.completeness_score() * 100,
            )

            delay = random.uniform(DRIP_DELAY_MIN, DRIP_DELAY_MAX)
            time.sleep(delay)
            return True

        except Exception as e:
            logger.error("Failed to add %s: %s", motor.ref, e)
            return False

    def get_all_refs(self) -> set[str]:
        return self._all_refs.copy()

    def get_total_count(self) -> int:
        return len(self._all_refs)

    def get_brand_counts(self) -> dict[str, int]:
        return {b: len(r) for b, r in self._brand_refs.items() if r}

    def get_known_brands(self) -> set[str]:
        """Return all brand names that have a tab in the sheet."""
        return set(self._brand_names.values())

    def has_brand_tab(self, brand: str) -> bool:
        """Check if a brand has an existing tab."""
        return brand.upper() in self._brand_sheets

    def refresh_refs(self):
        if self._mode == "service_account":
            self._load_all_brand_sheets()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_writable(self) -> bool:
        return self._mode == "service_account"

    @property
    def brand_count(self) -> int:
        return len(self._brand_sheets)
