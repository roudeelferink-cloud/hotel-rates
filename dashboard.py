#!/usr/bin/env python3
"""
Genereert dashboard.html op basis van data.json.

Gebruik:
  python dashboard.py          # genereert dashboard.html
  python dashboard.py --open   # genereert en opent in browser
"""

import argparse
import json
import webbrowser
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data.json"
OUTPUT_FILE = Path(__file__).parent / "dashboard.html"
ONEDRIVE_FILE = Path(r"C:\Users\roude\OneDrive - VAN DER VALK HOTELS\Documenten\Hotel Tarieven\dashboard.html")


def laad_data() -> list:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _ota_cel(prijs: float | None, rank: int | None) -> str:
    """Formatteer een OTA prijs + rank badge als HTML-cel inhoud."""
    if prijs is None and rank is None:
        return "—"

    prijs_str = f"€\u00a0{prijs:.2f}" if prijs is not None else "—"

    if rank is not None:
        if rank <= 3:
            rank_css = "rank-top"
        elif rank <= 7:
            rank_css = "rank-midden"
        else:
            rank_css = "rank-laag"
        rank_html = f'<span class="rank {rank_css}">#{rank}</span>'
    else:
        rank_html = ""

    return f'{prijs_str} {rank_html}'


def genereer_html(resultaten: list) -> str:
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M")

    # Bepaal laagste directe prijs voor markering
    prijzen = [r["prijs"] for r in resultaten if r["prijs"] is not None]
    laagste = min(prijzen) if prijzen else None

    eigen = next((r for r in resultaten if r.get("eigen")), None)
    eigen_prijs = eigen["prijs"] if eigen else None

    rijen_html = ""
    for r in resultaten:
        if r["prijs"] is None:
            css = "niet-beschikbaar"
            badge = '<span class="badge nb">N/B</span>'
            prijs_str = "—"
            kamer_str = "—"
            verschil_str = "—"
        else:
            is_eigen = r.get("eigen", False)
            is_laagste = r["prijs"] == laagste
            css = "eigen" if is_eigen else ("laagste" if is_laagste else "")
            badge = '<span class="badge eigen-badge">Eigen</span>' if is_eigen else (
                '<span class="badge laagste-badge">Laagste</span>' if is_laagste else ""
            )
            prijs_str = f"€\u00a0{r['prijs']:.2f}"
            kamer_str = r.get("kamer_type") or "—"

            if eigen_prijs and not is_eigen:
                diff = r["prijs"] - eigen_prijs
                teken = "+" if diff >= 0 else ""
                verschil_css = "positief" if diff >= 0 else "negatief"
                verschil_str = f'<span class="{verschil_css}">{teken}€\u00a0{diff:.2f}</span>'
            else:
                verschil_str = "—"

        booking_str = _ota_cel(r.get("booking_prijs"), r.get("booking_rank"))
        expedia_str = _ota_cel(r.get("expedia_prijs"), r.get("expedia_rank"))

        rijen_html += f"""
        <tr class="{css}">
            <td class="td-naam">{r['naam']} {badge}</td>
            <td class="td-kamer">{kamer_str}</td>
            <td class="prijs">{prijs_str}</td>
            <td class="ota">{booking_str}</td>
            <td class="ota">{expedia_str}</td>
            <td class="verschil">{verschil_str}</td>
        </tr>"""

    run_datum = ""
    if resultaten:
        ts = resultaten[0].get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            run_datum = dt.strftime("%d-%m-%Y %H:%M")
        except Exception:
            run_datum = ts

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Hotel Tarieven Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f0f2f5;
      color: #1a1a2e;
      min-height: 100vh;
      padding: 32px 16px;
    }}

    .container {{
      max-width: 1120px;
      margin: 0 auto;
    }}

    header {{
      margin-bottom: 28px;
    }}

    header h1 {{
      font-size: 1.6rem;
      font-weight: 700;
      color: #1a1a2e;
    }}

    header p {{
      color: #666;
      font-size: 0.9rem;
      margin-top: 4px;
    }}

    .card {{
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.07);
      overflow: hidden;
      margin-bottom: 24px;
    }}

    .card-header {{
      padding: 16px 24px;
      border-bottom: 1px solid #f0f0f0;
      font-weight: 600;
      font-size: 0.95rem;
      color: #444;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
    }}

    th {{
      text-align: left;
      padding: 10px 16px;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #888;
      background: #fafafa;
      border-bottom: 1px solid #f0f0f0;
      white-space: nowrap;
    }}

    td {{
      padding: 13px 16px;
      border-bottom: 1px solid #f8f8f8;
      font-size: 0.93rem;
      vertical-align: middle;
    }}

    .td-naam {{ min-width: 220px; }}
    .td-kamer {{ color: #666; font-size: 0.85rem; }}

    tr:last-child td {{ border-bottom: none; }}

    tr.eigen {{ background: #eff6ff; }}
    tr.laagste {{ background: #f0fdf4; }}
    tr.niet-beschikbaar {{ opacity: 0.5; }}

    td.prijs {{
      font-weight: 700;
      font-size: 1.05rem;
      color: #1a1a2e;
      white-space: nowrap;
    }}

    tr.eigen td.prijs {{ color: #1d4ed8; }}
    tr.laagste td.prijs {{ color: #16a34a; }}

    td.ota {{
      font-size: 0.9rem;
      white-space: nowrap;
      color: #374151;
    }}

    .verschil {{ font-size: 0.9rem; white-space: nowrap; }}
    .positief {{ color: #16a34a; font-weight: 600; }}
    .negatief {{ color: #dc2626; font-weight: 600; }}

    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 99px;
      font-size: 0.72rem;
      font-weight: 600;
      vertical-align: middle;
      margin-left: 6px;
    }}

    .eigen-badge {{ background: #dbeafe; color: #1d4ed8; }}
    .laagste-badge {{ background: #dcfce7; color: #16a34a; }}
    .nb {{ background: #f3f4f6; color: #9ca3af; }}

    /* OTA rank badges */
    .rank {{
      display: inline-block;
      padding: 1px 6px;
      border-radius: 99px;
      font-size: 0.72rem;
      font-weight: 700;
      margin-left: 4px;
      vertical-align: middle;
    }}
    .rank-top    {{ background: #dcfce7; color: #15803d; }}
    .rank-midden {{ background: #fef9c3; color: #854d0e; }}
    .rank-laag   {{ background: #fee2e2; color: #b91c1c; }}

    .legenda {{
      display: flex;
      gap: 20px;
      padding: 14px 24px;
      background: #fafafa;
      border-top: 1px solid #f0f0f0;
      font-size: 0.82rem;
      color: #666;
      flex-wrap: wrap;
    }}

    .legenda span {{ display: flex; align-items: center; gap: 6px; }}
    .dot {{
      width: 10px; height: 10px; border-radius: 50%; display: inline-block;
    }}
    .dot-eigen {{ background: #1d4ed8; }}
    .dot-laagste {{ background: #16a34a; }}

    footer {{
      text-align: center;
      color: #bbb;
      font-size: 0.8rem;
      margin-top: 8px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Hotel Tarieven Dashboard</h1>
      <p>Kamerprijzen voor morgen &nbsp;·&nbsp; Laatste run: {run_datum} &nbsp;·&nbsp; Gegenereerd: {timestamp}</p>
    </header>

    <div class="card">
      <div class="card-header">
        Prijsvergelijking — standaard tweepersoonskamer (1 nacht)
      </div>
      <table>
        <thead>
          <tr>
            <th>Hotel</th>
            <th>Kamertype</th>
            <th>Directe prijs</th>
            <th>Booking.com</th>
            <th>Expedia</th>
            <th>vs. eigen hotel</th>
          </tr>
        </thead>
        <tbody>
          {rijen_html}
        </tbody>
      </table>
      <div class="legenda">
        <span><span class="dot dot-eigen"></span> Eigen hotel</span>
        <span><span class="dot dot-laagste"></span> Laagste directe prijs</span>
        <span><span class="rank rank-top">#1</span> top&nbsp;3 in stad</span>
        <span><span class="rank rank-midden">#5</span> positie&nbsp;4–7</span>
        <span><span class="rank rank-laag">#9</span> positie&nbsp;8+</span>
      </div>
    </div>

    <footer>Directe prijs incl. BTW en toeristenbelasting &nbsp;·&nbsp; OTA-rank = positie in stadszoekresultaten (populariteitsvolgorde)</footer>
  </div>
</body>
</html>"""


def genereer(open_browser: bool = False) -> None:
    resultaten = laad_data()
    html = genereer_html(resultaten)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Dashboard gegenereerd: {OUTPUT_FILE}")
    if ONEDRIVE_FILE.parent.exists():
        ONEDRIVE_FILE.write_text(html, encoding="utf-8")
        print(f"Dashboard gesynct naar OneDrive: {ONEDRIVE_FILE}")
    if open_browser:
        webbrowser.open(OUTPUT_FILE.as_uri())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true", help="Open dashboard in browser na genereren")
    args = parser.parse_args()
    genereer(open_browser=args.open)


if __name__ == "__main__":
    main()
