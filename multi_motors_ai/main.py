#!/usr/bin/env python3
"""Multi-Motors AI - Continuous brushless motor catalog builder.

Finds brushless motors online, extracts specs, and adds them
one by one (drip feed) to the correct brand tab in Google Sheets.
"""

import logging
import random
import signal
import sys
import time
from datetime import datetime

import schedule

from .config import (
    MOTOR_BRANDS,
    STATOR_SIZES,
    SCAN_INTERVAL_MINUTES,
    LOG_LEVEL,
)
from .sheets import SheetsManager
from .scrapers.search_engine import SearchEngineScraper
from .scrapers.shop_scraper import ShopScraper, ManufacturerScraper
from .models import MotorSpec

# --- Logging setup ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("multi_motors_ai.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("multi_motors_ai")

# Global flag for graceful shutdown
_running = True


def signal_handler(sig, frame):
    global _running
    logger.info("Shutdown signal received, finishing current motor...")
    _running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def deduplicate_motors(motors: list[MotorSpec]) -> list[MotorSpec]:
    """Remove duplicate motors based on REF."""
    seen = set()
    unique = []
    for motor in motors:
        if not motor.ref:
            motor.generate_ref()
        if motor.ref and motor.ref not in seen:
            seen.add(motor.ref)
            unique.append(motor)
    return unique


def run_scan_cycle(sheets: SheetsManager) -> int:
    """Run one complete scan cycle: discover motors then drip-feed them.

    Returns the number of new motors added.
    """
    logger.info("=" * 60)
    logger.info("Starting scan cycle at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    all_motors: list[MotorSpec] = []
    existing_refs = sheets.get_all_refs()

    # --- Phase 1: Search Engine Discovery ---
    logger.info("--- Phase 1: Search Engine Discovery ---")
    try:
        search_scraper = SearchEngineScraper()

        # Rotate through brands (random subset each cycle)
        brand_sample = random.sample(
            MOTOR_BRANDS,
            min(10, len(MOTOR_BRANDS)),
        )
        stator_sample = random.sample(
            STATOR_SIZES,
            min(8, len(STATOR_SIZES)),
        )

        discovered = search_scraper.discover_motors(
            brands=brand_sample,
            stator_sizes=stator_sample,
            include_new=True,
        )

        for result in discovered:
            if not _running:
                break
            try:
                motors = search_scraper.scrape_product_page(
                    url=result["url"],
                    brand=result.get("brand", ""),
                )
                for motor in motors:
                    if not motor.ref:
                        motor.generate_ref()
                    if motor.ref not in existing_refs:
                        all_motors.append(motor)
            except Exception as e:
                logger.debug("Failed to scrape %s: %s", result["url"], e)

        logger.info("Phase 1 complete: %d candidate motors", len(all_motors))

    except Exception as e:
        logger.error("Phase 1 failed: %s", e)

    if not _running:
        return 0

    # --- Phase 2: Shop Scraping ---
    logger.info("--- Phase 2: FPV Shop Scraping ---")
    try:
        shop_scraper = ShopScraper()
        shop_motors = shop_scraper.scrape()
        all_motors.extend(shop_motors)
        logger.info("Phase 2 complete: %d motors from shops", len(shop_motors))
    except Exception as e:
        logger.error("Phase 2 failed: %s", e)

    if not _running:
        return 0

    # --- Phase 3: Manufacturer Websites ---
    logger.info("--- Phase 3: Manufacturer Scraping ---")
    try:
        mfg_scraper = ManufacturerScraper()
        mfg_motors = mfg_scraper.scrape()
        all_motors.extend(mfg_motors)
        logger.info("Phase 3 complete: %d motors from manufacturers", len(mfg_motors))
    except Exception as e:
        logger.error("Phase 3 failed: %s", e)

    # --- Deduplicate and filter ---
    all_motors = deduplicate_motors(all_motors)
    valid_motors = [m for m in all_motors if m.is_valid() and m.marque]

    logger.info(
        "After deduplication: %d valid motors (with brand) out of %d total",
        len(valid_motors),
        len(all_motors),
    )

    # Sort by completeness (most complete first)
    valid_motors.sort(key=lambda m: m.completeness_score(), reverse=True)

    # --- Drip feed to Google Sheets ---
    if valid_motors:
        logger.info("--- Drip Feed: inserting motors one by one ---")
        added = 0
        for motor in valid_motors:
            if not _running:
                logger.info("Shutdown requested, stopping drip feed")
                break
            if sheets.drip_add_motor(motor):
                added += 1
        logger.info("Drip feed done: %d new motors added", added)
    else:
        added = 0
        logger.info("No new motors to add this cycle")

    # Log summary
    total = sheets.get_total_count()
    brand_counts = sheets.get_brand_counts()
    logger.info("Scan cycle complete. Total motors in catalog: %d", total)
    logger.info("Motors per brand:")
    for brand, count in sorted(brand_counts.items()):
        logger.info("  %s: %d", brand, count)
    logger.info("=" * 60)

    return added


def main():
    """Main entry point - runs the continuous scraping loop."""
    logger.info("=" * 60)
    logger.info("  Multi-Motors AI - Brushless Motor Catalog Builder")
    logger.info("  Mode: drip feed (one motor at a time per brand tab)")
    logger.info("=" * 60)

    # Connect to Google Sheets
    sheets = SheetsManager()
    try:
        sheets.connect()
    except Exception as e:
        logger.critical("Cannot connect to Google Sheets: %s", e)
        logger.critical(
            "Make sure credentials.json is present and the service account "
            "has access to the spreadsheet."
        )
        sys.exit(1)

    total = sheets.get_total_count()
    logger.info("Current catalog: %d motors across %d brand tabs", total, sheets.brand_count)
    logger.info("Authentication mode: %s", sheets.mode)

    if not sheets.is_writable:
        logger.warning(
            "Running in READ-ONLY mode (API Key). "
            "Motors will be discovered but NOT added to the sheet. "
            "Set up a Service Account for write access (see README)."
        )

    # Run first scan immediately
    logger.info("Running initial scan...")
    run_scan_cycle(sheets)

    # Schedule periodic scans
    schedule.every(SCAN_INTERVAL_MINUTES).minutes.do(run_scan_cycle, sheets)
    logger.info(
        "Scheduled scans every %d minutes. Press Ctrl+C to stop.",
        SCAN_INTERVAL_MINUTES,
    )

    # Main loop
    while _running:
        schedule.run_pending()
        time.sleep(10)

    logger.info("Multi-Motors AI stopped gracefully.")


if __name__ == "__main__":
    main()
