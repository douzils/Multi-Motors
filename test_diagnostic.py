#!/usr/bin/env python3
"""Diagnostic script to test each component independently."""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("test")


def test_sheets_connection():
    """Test 1: Can we connect and read the Google Sheet?"""
    logger.info("=" * 50)
    logger.info("TEST 1: Google Sheets connection")
    logger.info("=" * 50)

    from multi_motors_ai.sheets import SheetsManager

    sheets = SheetsManager()
    try:
        sheets.connect()
        logger.info("OK - Connected in mode: %s", sheets.mode)
        logger.info("OK - Brand tabs found: %d", sheets.brand_count)
        logger.info("OK - Total motors loaded: %d", sheets.get_total_count())

        brand_counts = sheets.get_brand_counts()
        for brand, count in sorted(brand_counts.items()):
            logger.info("     %s: %d motors", brand, count)

        return sheets
    except Exception as e:
        logger.error("FAIL - %s", e)
        return None


def test_write_motor(sheets):
    """Test 2: Can we write a test motor to the sheet?"""
    logger.info("=" * 50)
    logger.info("TEST 2: Write a test motor")
    logger.info("=" * 50)

    if not sheets or not sheets.is_writable:
        logger.error("FAIL - Not writable (mode: %s)", sheets.mode if sheets else "none")
        return False

    from multi_motors_ai.models import MotorSpec

    test_motor = MotorSpec(
        ref="TEST-2207-1800",
        marque="TEST",
        nom="Test Motor AI",
        version="V1",
        classe="2207",
        kv="1800",
        poids="30",
        h_stator="07",
        d_stator="22",
        lipo="4S-6S",
        voltage="22.2",
        lien="https://test.example.com",
    )

    try:
        success = sheets.drip_add_motor(test_motor)
        if success:
            logger.info("OK - Test motor added to sheet!")
            logger.info("     Check your Google Sheet for a 'TEST' tab")
            logger.info("     Delete the test row/tab when done")
        else:
            logger.info("SKIP - Motor already exists or invalid")
        return True
    except Exception as e:
        logger.error("FAIL - %s", e)
        return False


def test_search():
    """Test 3: Can we search for motors?"""
    logger.info("=" * 50)
    logger.info("TEST 3: Search engine (DuckDuckGo)")
    logger.info("=" * 50)

    try:
        from multi_motors_ai.scrapers.search_engine import SearchEngineScraper

        scraper = SearchEngineScraper()
        results = scraper.search_brand("Emax", max_results=5)
        logger.info("OK - Found %d URLs for brand 'Emax'", len(results))
        for r in results[:3]:
            logger.info("     %s", r["url"][:80])
        return len(results) > 0
    except Exception as e:
        logger.error("FAIL - %s", e)
        return False


def test_scrape_and_parse():
    """Test 4: Can we scrape a page and extract motor data?"""
    logger.info("=" * 50)
    logger.info("TEST 4: Scrape + parse a motor page")
    logger.info("=" * 50)

    try:
        from multi_motors_ai.scrapers.search_engine import SearchEngineScraper

        scraper = SearchEngineScraper()

        # Try known motor pages
        test_urls = [
            ("https://www.getfpv.com/motors/mini-quad-motors.html", ""),
            ("https://betafpv.com/collections/brushless-motors", "BetaFPV"),
        ]

        for url, brand in test_urls:
            logger.info("Trying: %s", url)
            try:
                motors = scraper.scrape_product_page(url=url, brand=brand)
                if motors:
                    logger.info("OK - Found %d motor(s):", len(motors))
                    for m in motors[:3]:
                        logger.info(
                            "     %s | %s | %s %sKV | completeness=%.0f%%",
                            m.ref, m.marque, m.classe, m.kv,
                            m.completeness_score() * 100,
                        )
                    return True
                else:
                    logger.info("     No motors extracted from this page")
            except Exception as e:
                logger.warning("     Failed: %s", e)

        logger.warning("No motors found from any test URL")
        return False

    except Exception as e:
        logger.error("FAIL - %s", e)
        return False


def main():
    logger.info("Multi-Motors AI - Diagnostic Test")
    logger.info("")

    # Test 1: Connection
    sheets = test_sheets_connection()

    # Test 2: Write
    if sheets:
        test_write_motor(sheets)

    # Test 3: Search
    test_search()

    # Test 4: Scrape + Parse
    test_scrape_and_parse()

    logger.info("")
    logger.info("=" * 50)
    logger.info("Diagnostic complete. Check results above.")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
