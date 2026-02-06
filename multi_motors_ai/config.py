"""Configuration for Multi-Motors AI scraper."""

import os
from dotenv import load_dotenv

load_dotenv()

# Google Sheets
SPREADSHEET_ID = os.getenv(
    "SPREADSHEET_ID",
    "1xjOAtOVLFV1Nf2H30MIW-AXwlEBXlmaZ5FlJbus7KTc",
)
SHEET_GID = int(os.getenv("SHEET_GID", "1456126498"))
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Scraping
REQUEST_DELAY_MIN = float(os.getenv("REQUEST_DELAY_MIN", "2"))
REQUEST_DELAY_MAX = float(os.getenv("REQUEST_DELAY_MAX", "5"))
MAX_RESULTS_PER_SEARCH = int(os.getenv("MAX_RESULTS_PER_SEARCH", "30"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Scheduling
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "60"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Column mapping matching the Google Sheet structure
SHEET_COLUMNS = [
    "ID",
    "REF",
    "MARQUE",
    "NOM",
    "VERSION",
    "CLASSE",
    "KV",
    "POIDS",
    "H STATOR",
    "D STATOR",
    "H MOTEUR",
    "D MOTEUR",
    "D SHAFT",
    "L SHAFT",
    "TYPE SHAFT",
    "VIS HEL",
    "VIS FIX",
    "ENTRAXE FIX",
    "LIPO",
    "VOLTAGE",
    "L CABLE",
    "TYPE CABLE",
    "HELICE",
    "PUISSANCE",
    "AMP",
    "AIMANT",
    "CLOCHE",
    "CONFIG",
    "LIEN",
    "IMG",
]

# Known brushless motor brands to search for
MOTOR_BRANDS = [
    "3BHOBBY",
    "BetaFPV",
    "BrotherHobby",
    "Cobra",
    "DYS",
    "Emax",
    "FlyFishRC",
    "Flywoo",
    "GepRC",
    "HappyModel",
    "HGLrc",
    "iFlight",
    "Ldarc",
    "LDPOWER",
    "Mamba",
    "NewBeeDrone",
    "Rcinpower",
    "Rcx",
    "SunnySky",
    "T-Motor",
    "Xnova",
    "AMAX",
    "Diatone",
    "FPVCycle",
    "Hulkie",
    "HSKRC",
    "JMT",
    "KingKong",
    "LDARC",
    "NamelessRC",
    "Racerstar",
    "ReadyToSky",
    "RushFPV",
    "SpeedyBee",
    "Surpass",
    "Tattu",
    "Tcmmrc",
    "TopMotor",
    "URUAV",
    "ZMX",
]

# Search queries for finding brushless motors
SEARCH_QUERIES = [
    "{brand} brushless motor fpv specs",
    "{brand} brushless motor drone KV stator",
    "{brand} fpv racing motor specifications",
    "brushless motor {stator} KV fpv drone",
    "new brushless motor fpv 2024 2025 specs",
    "micro brushless motor whoop specs weight",
]

# Common stator sizes to search for
STATOR_SIZES = [
    "0603", "0702", "0802", "0803", "1002", "1103", "1104", "1105",
    "1106", "1202", "1204", "1303", "1306", "1404", "1405", "1406",
    "1408", "1507", "1604", "1606", "1806", "1808", "2004", "2005",
    "2006", "2204", "2205", "2206", "2207", "2208", "2306", "2307",
    "2308", "2405", "2406", "2407", "2505", "2506", "2507", "2806",
    "2807", "2808", "3110", "3115",
]

# Source websites for scraping
SCRAPE_SOURCES = {
    "getfpv": {
        "base_url": "https://www.getfpv.com",
        "search_url": "https://www.getfpv.com/catalogsearch/result/?q={query}",
        "category": "motors",
    },
    "racedayquads": {
        "base_url": "https://www.racedayquads.com",
        "search_url": "https://www.racedayquads.com/search?type=product&q={query}",
        "category": "motors",
    },
    "pyrodrone": {
        "base_url": "https://pyrodrone.com",
        "search_url": "https://pyrodrone.com/search?q={query}",
        "category": "motors",
    },
    "betafpv": {
        "base_url": "https://betafpv.com",
        "search_url": "https://betafpv.com/search?q={query}",
        "category": "motors",
    },
    "iflight": {
        "base_url": "https://www.iflight-rc.com",
        "search_url": "https://www.iflight-rc.com/index.php?route=product/search&search={query}",
        "category": "motors",
    },
}
