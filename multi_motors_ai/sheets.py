"""Google Sheets integration for Multi-Motors catalog."""

import logging
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from .config import SPREADSHEET_ID, SHEET_GID, GOOGLE_CREDENTIALS_FILE, SHEET_COLUMNS
from .models import MotorSpec

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsManager:
    """Manages interactions with the Google Sheet motor catalog."""

    def __init__(self):
        self._client: Optional[gspread.Client] = None
        self._spreadsheet = None
        self._worksheet = None
        self._existing_refs: set[str] = set()

    def connect(self):
        """Authenticate and connect to Google Sheets."""
        try:
            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
            )
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open_by_key(SPREADSHEET_ID)

            # Find the worksheet by GID
            self._worksheet = None
            for ws in self._spreadsheet.worksheets():
                if ws.id == SHEET_GID:
                    self._worksheet = ws
                    break

            if self._worksheet is None:
                # Fallback to first sheet
                self._worksheet = self._spreadsheet.sheet1
                logger.warning(
                    "Could not find sheet with GID %s, using first sheet", SHEET_GID
                )

            logger.info(
                "Connected to spreadsheet '%s', sheet '%s'",
                self._spreadsheet.title,
                self._worksheet.title,
            )
            self._load_existing_refs()

        except FileNotFoundError:
            logger.error(
                "Credentials file '%s' not found. "
                "Please set up a Google Service Account and download the JSON key. "
                "See README for instructions.",
                GOOGLE_CREDENTIALS_FILE,
            )
            raise
        except Exception as e:
            logger.error("Failed to connect to Google Sheets: %s", e)
            raise

    def _load_existing_refs(self):
        """Load all existing REF values to avoid duplicates."""
        try:
            # REF is column B (index 2)
            ref_col = self._worksheet.col_values(2)
            # Skip header
            self._existing_refs = {ref.strip() for ref in ref_col[1:] if ref.strip()}
            logger.info("Loaded %d existing motor references", len(self._existing_refs))
        except Exception as e:
            logger.error("Failed to load existing refs: %s", e)
            self._existing_refs = set()

    def motor_exists(self, ref: str) -> bool:
        """Check if a motor with the given REF already exists."""
        return ref.strip() in self._existing_refs

    def add_motor(self, motor: MotorSpec) -> bool:
        """Add a single motor to the sheet. Returns True if added."""
        if not motor.is_valid():
            logger.debug("Skipping invalid motor: %s", motor.ref)
            return False

        if not motor.ref:
            motor.generate_ref()

        if self.motor_exists(motor.ref):
            logger.debug("Motor already exists: %s", motor.ref)
            return False

        try:
            row = motor.to_sheet_row()
            self._worksheet.append_row(row, value_input_option="USER_ENTERED")
            self._existing_refs.add(motor.ref)
            logger.info(
                "Added motor: %s (%s %s %sKV) [completeness: %.0f%%]",
                motor.ref,
                motor.marque,
                motor.nom,
                motor.kv,
                motor.completeness_score() * 100,
            )
            return True
        except Exception as e:
            logger.error("Failed to add motor %s: %s", motor.ref, e)
            return False

    def add_motors(self, motors: list[MotorSpec]) -> int:
        """Add multiple motors to the sheet. Returns count of motors added."""
        added = 0
        new_motors = []

        for motor in motors:
            if not motor.is_valid():
                continue
            if not motor.ref:
                motor.generate_ref()
            if not self.motor_exists(motor.ref):
                new_motors.append(motor)

        if not new_motors:
            logger.info("No new motors to add")
            return 0

        # Batch append for efficiency
        try:
            rows = [m.to_sheet_row() for m in new_motors]
            self._worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            for motor in new_motors:
                self._existing_refs.add(motor.ref)
                added += 1
                logger.info(
                    "Added motor: %s (%s %s %sKV)",
                    motor.ref,
                    motor.marque,
                    motor.nom,
                    motor.kv,
                )
        except Exception as e:
            logger.error("Batch insert failed, trying one by one: %s", e)
            for motor in new_motors:
                if self.add_motor(motor):
                    added += 1

        logger.info("Added %d new motors out of %d candidates", added, len(motors))
        return added

    def get_all_refs(self) -> set[str]:
        """Return all existing motor references."""
        return self._existing_refs.copy()

    def get_row_count(self) -> int:
        """Return the total number of data rows (excluding header)."""
        try:
            all_values = self._worksheet.get_all_values()
            return max(0, len(all_values) - 1)
        except Exception:
            return 0

    def refresh_refs(self):
        """Reload existing references from the sheet."""
        self._load_existing_refs()
