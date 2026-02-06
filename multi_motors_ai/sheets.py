"""Google Sheets integration for Multi-Motors catalog.

Supports two authentication modes:
- Service Account (credentials.json) → full read/write access (recommended)
- API Key only → read-only access for testing/verification
"""

import logging
from typing import Optional

import requests

from .config import (
    SPREADSHEET_ID,
    SHEET_GID,
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

SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsManager:
    """Manages interactions with the Google Sheet motor catalog.

    Tries Service Account first (full access).
    Falls back to API Key (read-only) if no credentials.json.
    """

    def __init__(self):
        self._client = None  # gspread client (service account mode)
        self._spreadsheet = None
        self._worksheet = None
        self._existing_refs: set[str] = set()
        self._mode: str = "none"  # "service_account", "api_key", or "none"
        self._sheet_name: Optional[str] = None

    def connect(self):
        """Authenticate and connect to Google Sheets."""
        # Try Service Account first
        if self._try_service_account():
            return

        # Fallback to API Key
        if self._try_api_key():
            return

        raise RuntimeError(
            "Cannot connect to Google Sheets.\n"
            "Option 1 (recommended): Place credentials.json in the project root.\n"
            "Option 2 (read-only): Set GOOGLE_API_KEY in .env file.\n"
            "See README.md for setup instructions."
        )

    def _try_service_account(self) -> bool:
        """Try to connect using Service Account credentials."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials

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
                self._worksheet = self._spreadsheet.sheet1
                logger.warning(
                    "Could not find sheet with GID %s, using first sheet",
                    SHEET_GID,
                )

            self._mode = "service_account"
            self._sheet_name = self._worksheet.title
            logger.info(
                "Connected via Service Account to '%s', sheet '%s'",
                self._spreadsheet.title,
                self._sheet_name,
            )
            self._load_existing_refs()
            return True

        except FileNotFoundError:
            logger.info(
                "No credentials.json found, will try API Key..."
            )
            return False
        except ImportError:
            logger.warning("gspread not installed, will try API Key...")
            return False
        except Exception as e:
            logger.warning("Service Account auth failed: %s", e)
            return False

    def _try_api_key(self) -> bool:
        """Try to connect using API Key (read-only)."""
        if not GOOGLE_API_KEY:
            logger.warning("No GOOGLE_API_KEY configured")
            return False

        try:
            # Test the connection by reading sheet metadata
            url = f"{SHEETS_API_BASE}/{SPREADSHEET_ID}"
            params = {"key": GOOGLE_API_KEY}
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()

            data = resp.json()
            title = data.get("properties", {}).get("title", "Unknown")

            # Find sheet name by GID
            self._sheet_name = None
            for sheet in data.get("sheets", []):
                props = sheet.get("properties", {})
                if props.get("sheetId") == SHEET_GID:
                    self._sheet_name = props.get("title")
                    break

            if not self._sheet_name:
                # Fallback to first sheet
                sheets = data.get("sheets", [])
                if sheets:
                    self._sheet_name = sheets[0]["properties"]["title"]

            self._mode = "api_key"
            logger.info(
                "Connected via API Key (READ-ONLY) to '%s', sheet '%s'",
                title,
                self._sheet_name,
            )
            logger.warning(
                "API Key mode is READ-ONLY. "
                "To add motors, set up a Service Account (see README)."
            )
            self._load_existing_refs()
            return True

        except Exception as e:
            logger.warning("API Key connection failed: %s", e)
            return False

    def _api_key_read_column(self, col_letter: str) -> list[str]:
        """Read a column via the Sheets API with API Key."""
        range_str = f"{self._sheet_name}!{col_letter}:{col_letter}"
        url = f"{SHEETS_API_BASE}/{SPREADSHEET_ID}/values/{range_str}"
        params = {"key": GOOGLE_API_KEY}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        return [row[0] if row else "" for row in values]

    def _api_key_read_all(self) -> list[list[str]]:
        """Read all data via API Key."""
        range_str = f"{self._sheet_name}"
        url = f"{SHEETS_API_BASE}/{SPREADSHEET_ID}/values/{range_str}"
        params = {"key": GOOGLE_API_KEY}
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("values", [])

    def _api_key_append_rows(self, rows: list[list[str]]) -> bool:
        """Append rows via API Key. This requires the sheet to be publicly editable."""
        range_str = f"{self._sheet_name}!A:AD"
        url = f"{SHEETS_API_BASE}/{SPREADSHEET_ID}/values/{range_str}:append"
        params = {
            "key": GOOGLE_API_KEY,
            "valueInputOption": "USER_ENTERED",
            "insertDataOption": "INSERT_ROWS",
        }
        body = {"values": rows}
        resp = requests.post(url, params=params, json=body, timeout=30)
        if resp.status_code == 403:
            logger.error(
                "API Key does not have write access. "
                "Set up a Service Account for write access (see README)."
            )
            return False
        resp.raise_for_status()
        return True

    def _load_existing_refs(self):
        """Load all existing REF values to avoid duplicates."""
        try:
            if self._mode == "service_account":
                ref_col = self._worksheet.col_values(2)  # Column B
            elif self._mode == "api_key":
                ref_col = self._api_key_read_column("B")
            else:
                ref_col = []

            # Skip header
            self._existing_refs = {
                ref.strip() for ref in ref_col[1:] if ref.strip()
            }
            logger.info(
                "Loaded %d existing motor references", len(self._existing_refs)
            )
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

            if self._mode == "service_account":
                self._worksheet.append_row(
                    row, value_input_option="USER_ENTERED"
                )
            elif self._mode == "api_key":
                if not self._api_key_append_rows([row]):
                    return False
            else:
                logger.error("Not connected to Google Sheets")
                return False

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

            if self._mode == "service_account":
                self._worksheet.append_rows(
                    rows, value_input_option="USER_ENTERED"
                )
            elif self._mode == "api_key":
                if not self._api_key_append_rows(rows):
                    logger.error(
                        "API Key write failed. Use Service Account for write access."
                    )
                    return 0
            else:
                logger.error("Not connected")
                return 0

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

        logger.info(
            "Added %d new motors out of %d candidates", added, len(motors)
        )
        return added

    def get_all_refs(self) -> set[str]:
        """Return all existing motor references."""
        return self._existing_refs.copy()

    def get_row_count(self) -> int:
        """Return the total number of data rows (excluding header)."""
        try:
            if self._mode == "service_account":
                all_values = self._worksheet.get_all_values()
            elif self._mode == "api_key":
                all_values = self._api_key_read_all()
            else:
                return 0
            return max(0, len(all_values) - 1)
        except Exception:
            return 0

    def refresh_refs(self):
        """Reload existing references from the sheet."""
        self._load_existing_refs()

    @property
    def mode(self) -> str:
        """Return the current authentication mode."""
        return self._mode

    @property
    def is_writable(self) -> bool:
        """Check if the current mode supports writing."""
        return self._mode == "service_account"
