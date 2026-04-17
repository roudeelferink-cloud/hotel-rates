#!/usr/bin/env python3
"""
Google Sheets writer - schrijft scraper output weg naar Google Sheets.

Elke run voegt rijen toe aan het eerste tabblad met kolommen:
  timestamp | hotelnaam | kamernaam | tarieftype | prijs

Gebruik:
  python sheets_writer.py          # voert scraper uit en schrijft resultaten
  python sheets_writer.py --dry-run  # toont rijen zonder te schrijven

Vereisten:
  pip install gspread google-auth
  credentials.json (Google Service Account sleutelbestand) in dezelfde map
  Sheet gedeeld met het e-mailadres uit credentials.json (als Editor)
"""

import argparse
import json
import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from scraper import main as scrape
from dashboard import genereer as genereer_dashboard

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------

SHEET_ID = "1QIitW5l90dYN0palPrbGM81m6tqKuvvLgPXqn6lSXwI"
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
HEADER = [
    "timestamp", "datum", "hotelnaam", "kamernaam", "tarieftype", "prijs",
    "booking_prijs", "booking_rank", "expedia_prijs", "expedia_rank",
]


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def verbind_sheet() -> gspread.Worksheet:
    """Authenticeer en geef het eerste tabblad terug."""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    return spreadsheet.sheet1


def zorg_voor_header(ws: gspread.Worksheet) -> None:
    """Voeg de headerrij toe als het sheet leeg is."""
    if ws.row_count == 0 or not ws.row_values(1):
        ws.append_row(HEADER, value_input_option="RAW")


def resultaten_naar_rijen(resultaten: list) -> list:
    """Zet scraper-resultaten om naar rijen voor Google Sheets."""
    rijen = []
    for r in resultaten:
        if r["prijs"] is None:
            continue  # sla hotels zonder prijs over
        rijen.append([
            r["timestamp"],
            r.get("datum", ""),
            r["naam"],
            r["kamer_type"] or "",
            "eigen" if r.get("eigen") else "concurrent",
            r["prijs"],
            r.get("booking_prijs") or "",
            r.get("booking_rank") or "",
            r.get("expedia_prijs") or "",
            r.get("expedia_rank") or "",
        ])
    return rijen


def schrijf_naar_sheets(resultaten: list, dry_run: bool = False) -> int:
    """
    Schrijf resultaten naar Google Sheets.
    Geeft het aantal geschreven rijen terug.
    """
    rijen = resultaten_naar_rijen(resultaten)

    if not rijen:
        print("Geen rijen om te schrijven (alle hotels hebben fout of geen prijs).")
        return 0

    if dry_run:
        print(f"\n[DRY RUN] {len(rijen)} rijen (niet geschreven):")
        print("  " + " | ".join(HEADER))
        print("  " + "-" * 65)
        for rij in rijen:
            print("  " + " | ".join(str(k) for k in rij))
        return len(rijen)

    ws = verbind_sheet()
    zorg_voor_header(ws)
    ws.append_rows(rijen, value_input_option="USER_ENTERED")
    print(f"\n{len(rijen)} rijen toegevoegd aan Google Sheets.")
    return len(rijen)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape hotelprijzen en sla op in Google Sheets.")
    parser.add_argument("--dry-run", action="store_true", help="Toon rijen zonder te schrijven")
    args = parser.parse_args()

    if not args.dry_run and not CREDENTIALS_FILE.exists():
        print(f"FOUT: {CREDENTIALS_FILE} niet gevonden.", file=sys.stderr)
        print("Zorg dat het Google Service Account JSON-bestand aanwezig is.", file=sys.stderr)
        sys.exit(1)

    print("Stap 1: Hotelprijzen ophalen...")
    resultaten = scrape()

    data_file = Path(__file__).parent / "data.json"
    data_file.write_text(json.dumps(resultaten, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"data.json bijgewerkt ({len(resultaten)} hotels)")

    print("\nStap 2: Wegschrijven naar Google Sheets...")
    schrijf_naar_sheets(resultaten, dry_run=args.dry_run)

    print("\nStap 3: Dashboard genereren...")
    genereer_dashboard()



if __name__ == "__main__":
    main()
