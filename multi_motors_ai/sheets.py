"""Google Sheets integration for Multi-Motors catalog.

Each brand has its own worksheet tab (e.g. "1 - 3BHOBBY", "2 - Emax").
Motors are inserted one at a time (drip feed) with delays between each.
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


class SheetsManager:
    """Manages multi-tab Google Sheet where each tab = one brand.

    Sheet tabs follow the naming pattern: "1 - 3BHOBBY", "2 - Emax", etc.
    Motors are routed to the correct tab based on their brand.
    """

    def __init__(self):
        self._client = None
        self._spreadsheet = None
        self._mode: str = "none"
        # brand (uppercase) -> worksheet object
        self._brand_sheets: dict[str, object] = {}
        # brand (uppercase) -> set of existing REFs
        self._brand_refs: dict[str, set[str]] = {}
        # All refs across all sheets for quick duplicate check
        self._all_refs: set[str] = set()
        # Next sheet number for creating new brand tabs
        self._next_sheet_number: int = 1

    def connect(self):
        """Authenticate and connect to Google Sheets."""
        if self._try_service_account():
            return
        if self._try_api_key():
            return
        raise RuntimeError(
            "Cannot connect to Google Sheets.\n"
            "Place credentials.json in the project root (see README)."
        )

    def _try_service_account(self) -> bool:
        """Connect using Service Account credentials."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
            )
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open_by_key(SPREADSHEET_ID)
            self._mode = "service_account"

            logger.info(
                "Connected via Service Account to '%s'",
                self._spreadsheet.title,
            )
            self._load_all_brand_sheets()
            return True

        except FileNotFoundError:
            logger.info("No credentials.json found, will try API Key...")
            return False
        except ImportError:
            logger.warning("gspread not installed, will try API Key...")
            return False
        except Exception as e:
            logger.warning("Service Account auth failed: %s", e)
            return False

    def _try_api_key(self) -> bool:
        """Connect using API Key (read-only)."""
        if not GOOGLE_API_KEY:
            logger.warning("No GOOGLE_API_KEY configured")
            return False
        try:
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
            resp = requests.get(url, params={"key": GOOGLE_API_KEY}, timeout=10)
            resp.raise_for_status()
            self._mode = "api_key"
            logger.info("Connected via API Key (READ-ONLY)")
            logger.warning(
                "API Key mode is READ-ONLY. "
                "To add motors, set up a Service Account."
            )
            return True
        except Exception as e:
            logger.warning("API Key connection failed: %s", e)
            return False

    def _load_all_brand_sheets(self):
        """Scan all worksheet tabs and map brand names to sheets."""
        self._brand_sheets.clear()
        self._brand_refs.clear()
        self._all_refs.clear()
        max_num = 0

        worksheets = self._spreadsheet.worksheets()
        logger.info("Found %d worksheet tabs", len(worksheets))

        for ws in worksheets:
            match = SHEET_NAME_RE.match(ws.title)
            if match:
                num = int(match.group(1))
                brand_name = match.group(2).strip()
                brand_key = brand_name.upper()

                self._brand_sheets[brand_key] = ws
                max_num = max(max_num, num)

                # Load existing refs for this brand
                try:
                    ref_col = ws.col_values(2)  # Column B = REF
                    refs = {r.strip() for r in ref_col[1:] if r.strip()}
                    self._brand_refs[brand_key] = refs
                    self._all_refs.update(refs)
                    logger.info(
                        "  Tab '%s': %d motors loaded", ws.title, len(refs)
                    )
                except Exception as e:
                    logger.warning("Failed to load refs from '%s': %s", ws.title, e)
                    self._brand_refs[brand_key] = set()
            else:
                logger.debug("Skipping tab '%s' (doesn't match brand pattern)", ws.title)

        self._next_sheet_number = max_num + 1
        logger.info(
            "Loaded %d brand tabs, %d total motors",
            len(self._brand_sheets),
            len(self._all_refs),
        )

    def _get_or_create_brand_sheet(self, brand: str):
        """Get the worksheet for a brand, creating it if it doesn't exist."""
        brand_key = brand.upper()

        if brand_key in self._brand_sheets:
            return self._brand_sheets[brand_key]

        # Create a new sheet for this brand
        sheet_title = f"{self._next_sheet_number} - {brand}"
        self._next_sheet_number += 1

        try:
            new_ws = self._spreadsheet.add_worksheet(
                title=sheet_title, rows=1000, cols=len(SHEET_COLUMNS)
            )
            # Add header row
            new_ws.append_row(SHEET_COLUMNS, value_input_option="USER_ENTERED")

            self._brand_sheets[brand_key] = new_ws
            self._brand_refs[brand_key] = set()

            logger.info("Created new brand tab: '%s'", sheet_title)
            return new_ws

        except Exception as e:
            logger.error("Failed to create tab for brand '%s': %s", brand, e)
            return None

    def motor_exists(self, ref: str) -> bool:
        """Check if a motor REF already exists in any tab."""
        return ref.strip() in self._all_refs

    def drip_add_motor(self, motor: MotorSpec) -> bool:
        """Add a single motor to the correct brand tab with a delay.

        This is the 'drip feed' method - one motor at a time.
        Returns True if the motor was added.
        """
        if not motor.is_valid():
            logger.debug("Skipping invalid motor: %s", motor.ref)
            return False

        if not motor.ref:
            motor.generate_ref()

        if self.motor_exists(motor.ref):
            logger.debug("Motor already exists: %s", motor.ref)
            return False

        if not motor.marque:
            logger.debug("No brand for motor: %s", motor.ref)
            return False

        if self._mode != "service_account":
            logger.warning("Cannot write in %s mode", self._mode)
            return False

        # Find the right worksheet for this brand
        ws = self._get_or_create_brand_sheet(motor.marque)
        if ws is None:
            return False

        try:
            row = motor.to_sheet_row()
            ws.append_row(row, value_input_option="USER_ENTERED")

            # Update caches
            brand_key = motor.marque.upper()
            self._brand_refs.setdefault(brand_key, set()).add(motor.ref)
            self._all_refs.add(motor.ref)

            logger.info(
                ">> Added: %s | %s %s %sKV | tab='%s' [%.0f%%]",
                motor.ref,
                motor.marque,
                motor.nom,
                motor.kv,
                ws.title,
                motor.completeness_score() * 100,
            )

            # Drip delay - wait before next insertion
            delay = random.uniform(DRIP_DELAY_MIN, DRIP_DELAY_MAX)
            logger.debug("Waiting %.1fs before next insertion...", delay)
            time.sleep(delay)

            return True

        except Exception as e:
            logger.error("Failed to add motor %s: %s", motor.ref, e)
            return False

    def drip_add_motors(self, motors: list[MotorSpec]) -> int:
        """Add motors one by one (drip feed) to their respective brand tabs.

        Returns the count of motors successfully added.
        """
        if not motors:
            logger.info("No motors to add")
            return 0

        added = 0
        skipped = 0
        total = len(motors)

        logger.info(
            "Starting drip feed: %d motors to process...", total
        )

        for i, motor in enumerate(motors, 1):
            if not motor.ref:
                motor.generate_ref()

            if not motor.is_valid() or not motor.marque:
                skipped += 1
                continue

            if self.motor_exists(motor.ref):
                skipped += 1
                continue

            success = self.drip_add_motor(motor)
            if success:
                added += 1

            # Progress log every 5 motors
            if i % 5 == 0 or i == total:
                logger.info(
                    "Progress: %d/%d processed | %d added | %d skipped",
                    i, total, added, skipped,
                )

        logger.info(
            "Drip feed complete: %d added, %d skipped out of %d total",
            added, skipped, total,
        )
        return added

    def get_all_refs(self) -> set[str]:
        """Return all existing motor references across all tabs."""
        return self._all_refs.copy()

    def get_total_count(self) -> int:
        """Return total motors across all brand tabs."""
        return len(self._all_refs)

    def get_brand_counts(self) -> dict[str, int]:
        """Return motor count per brand."""
        return {brand: len(refs) for brand, refs in self._brand_refs.items()}

    def refresh_refs(self):
        """Reload all refs from all tabs."""
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
