#!/usr/bin/env python3
"""
OTA prijs- en rankscraper: Booking.com en Expedia.nl.

Per hotel wordt op naam gezocht. De prijs en rank (positie in de
zoekresultaten) worden opgehaald voor dat specifieke hotel.

Rank = hoe prominent een hotel verschijnt als iemand op naam zoekt.
Rank 1 = het eerste zoekresultaat.

Alle 9 hotels worden in één browser-sessie per platform verwerkt
om overhead te beperken.

Gebruik:
  from scraper_ota import scrape_booking, scrape_expedia
"""
import re
import urllib.parse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_BESCHIKBAAR = True
except ImportError:
    PLAYWRIGHT_BESCHIKBAAR = False


_PW_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Gedeelde helpers
# ---------------------------------------------------------------------------

def _pw_context(pw):
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=_PW_USER_AGENT,
        locale="nl-NL",
        viewport={"width": 1440, "height": 900},
        extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"},
    )
    return browser, context


def _sluit_cookie_popup(page) -> None:
    selectors = [
        "#onetrust-accept-btn-handler",
        "#accept-button",
        "button:has-text('Alles accepteren')",
        "button:has-text('Accepteer alles')",
        "button:has-text('Accepteer')",
        "button:has-text('Accept all')",
        "button:has-text('Accept')",
        "[data-gdpr-consent='accept']",
        "#didomi-notice-agree-button",
        ".fc-cta-consent",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(600)
                return
        except Exception:
            pass


def _parse_eur_prijs(tekst: str) -> float | None:
    """Parseer Europees bedrag (€ 162, € 162,70, € 1.234,56)."""
    tekst = re.sub(r"[\s\u00a0\u202f\u2009]", "", tekst)
    # 1.234,56
    m = re.search(r"(\d{1,3}(?:\.\d{3})+,\d{2})", tekst)
    if m:
        return float(m.group(1).replace(".", "").replace(",", "."))
    # 162,70
    m = re.search(r"(\d+),(\d{2})\b", tekst)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    # geheel getal na €
    m = re.search(r"€(\d{2,4})\b", tekst)
    if m:
        v = int(m.group(1))
        if 20 <= v <= 9999:
            return float(v)
    return None


# ---------------------------------------------------------------------------
# Booking.com — één browser-sessie voor alle hotels
# ---------------------------------------------------------------------------

_MAANDEN_KORT = ["", "jan", "feb", "mrt", "apr", "mei", "jun",
                 "jul", "aug", "sep", "okt", "nov", "dec"]


def _prijs_uit_carousel(kaart, aankomst: str) -> float | None:
    """
    Haal prijs op uit de 'next available dates' carousel van een Booking.com kaart.
    Zoekt de regel met de aankomstdatum en pakt het eerste bedrag erna.
    Booking.com toont hier 'Al vanaf €X' per datumcombinatie.
    """
    carousel = kaart.query_selector('[data-testid="next-available-dates-carousel"]')
    if not carousel:
        return None

    tekst = carousel.inner_text()
    dag = int(aankomst.split("-")[2])
    maand = int(aankomst.split("-")[1])
    datum_kort = f"{dag} {_MAANDEN_KORT[maand]}"   # bv. "17 apr"

    regels = tekst.split("\n")
    for i, regel in enumerate(regels):
        if datum_kort in regel.lower():
            # Prijs staat 1–4 regels verder (na "1 nacht" en "Al vanaf")
            for j in range(i + 1, min(i + 6, len(regels))):
                p = _parse_eur_prijs(regels[j])
                if p:
                    return p
    return None


def _zoek_hotel_booking_pagina(page, hotel_naam: str, booking_slug: str,
                               aankomst: str, vertrek: str) -> tuple:
    """
    Zoek één hotel op naam op Booking.com en identificeer het via de exacte slug.

    Parameters
    ----------
    hotel_naam   : leesbare naam (alleen voor de zoekterm)
    booking_slug : Booking.com hotel-slug (bv. 'van-der-valk-hengelo.nl')
                   Wordt gebruikt om het juiste hotel in de resultaten te vinden.
    aankomst     : YYYY-MM-DD
    vertrek      : YYYY-MM-DD

    Geeft (prijs: float|None, rank: int|None).
    Rank = positie van het hotel in de zoekresultatenlijst (1 = eerste).

    Prijsstrategie:
    1. Standaard prijselement in de kaart
    2. Fallback: 'Al vanaf €X'-carousel voor de gevraagde aankomstdatum
    """
    zoekterm = urllib.parse.quote_plus(hotel_naam)
    url = (
        "https://www.booking.com/searchresults.nl.html"
        f"?ss={zoekterm}"
        f"&checkin={aankomst}&checkout={vertrek}"
        "&group_adults=2&no_rooms=1"
    )

    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2_000)
    _sluit_cookie_popup(page)
    page.wait_for_timeout(2_000)

    try:
        page.wait_for_selector('[data-testid="property-card"]', timeout=12_000)
    except Exception:
        return None, None

    kaarten = page.query_selector_all('[data-testid="property-card"]')

    for rank, kaart in enumerate(kaarten, start=1):
        # Identificeer hotel via slug in de link — geen fuzzy matching
        link_el = kaart.query_selector('[data-testid="title-link"]')
        href = link_el.get_attribute("href") if link_el else ""
        if booking_slug not in (href or ""):
            continue

        # Prijs ophalen — standaard selector
        prijs = None
        for sel in [
            '[data-testid="price-and-discounted-price"]',
            '[data-testid="price"]',
            ".bui-price-display__value",
            '[class*="priceDisplay"]',
            '[class*="price"]',
        ]:
            el = kaart.query_selector(sel)
            if el:
                p = _parse_eur_prijs(el.inner_text())
                if p:
                    prijs = p
                    break

        # Fallback: carousel met "Al vanaf €X" voor de gevraagde datum
        if prijs is None:
            prijs = _prijs_uit_carousel(kaart, aankomst)

        return prijs, rank

    return None, None


def scrape_booking(hotels: list, aankomst: str, vertrek: str) -> dict:
    """
    Haalt Booking.com prijs en rank op voor elk hotel in de lijst.

    Parameters
    ----------
    hotels   : lijst van hotel-dicts met minimaal {"naam": str}
    aankomst : YYYY-MM-DD
    vertrek  : YYYY-MM-DD

    Geeft dict terug:
      { hotel_naam: {"prijs": float|None, "rank": int|None} }
    """
    resultaten = {h["naam"]: {"prijs": None, "rank": None} for h in hotels}

    if not PLAYWRIGHT_BESCHIKBAAR:
        return resultaten

    with sync_playwright() as pw:
        browser, context = _pw_context(pw)
        cookie_popup_gesloten = False

        for hotel in hotels:
            naam = hotel["naam"]
            slug = hotel.get("booking_slug", "")
            if not slug:
                print(f"  [Booking.com] Geen slug geconfigureerd voor {naam}, wordt overgeslagen")
                continue
            zoekterm = hotel.get("booking_zoekterm", naam)
            page = context.new_page()
            try:
                prijs, rank = _zoek_hotel_booking_pagina(page, zoekterm, slug, aankomst, vertrek)
                resultaten[naam] = {"prijs": prijs, "rank": rank}
            except PlaywrightTimeout:
                pass
            except Exception as e:
                print(f"  [Booking.com] Fout bij {naam}: {e}")
            finally:
                page.close()

        browser.close()

    return resultaten


# ---------------------------------------------------------------------------
# Expedia — één browser-sessie voor alle hotels
# ---------------------------------------------------------------------------

def _zoek_hotel_expedia_pagina(page, hotel_naam: str, aankomst: str, vertrek: str) -> tuple:
    """
    Zoek één hotel op naam op Expedia.nl.
    Geeft (prijs: float|None, rank: int|None).
    """
    j, ms, d = aankomst.split("-")
    j2, ms2, d2 = vertrek.split("-")
    aankomst_exp = f"{ms}%2F{d}%2F{j}"
    vertrek_exp = f"{ms2}%2F{d2}%2F{j2}"
    zoekterm = urllib.parse.quote_plus(hotel_naam)

    url = (
        "https://www.expedia.nl/Hotel-Zoeken"
        f"?destination={zoekterm}"
        f"&startDate={aankomst_exp}&endDate={vertrek_exp}"
        "&adults=2&rooms=1"
    )

    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(4_000)
    _sluit_cookie_popup(page)
    page.wait_for_timeout(2_000)

    # Bot-detectie check
    body_tekst = page.inner_text("body")
    if "mens" in body_tekst.lower() or "bot" in body_tekst.lower() or "captcha" in body_tekst.lower():
        return None, None

    # Wacht op hotelkaarten
    for wacht_sel in [
        '[data-stid="lodging-card-responsive"]',
        'li[data-stid="open-hotel-information"]',
        'article[class*="uitk-card"]',
        '[class*="uitk-layout-grid-item"]',
    ]:
        try:
            page.wait_for_selector(wacht_sel, timeout=8_000)
            break
        except Exception:
            pass

    # Kaarten ophalen
    kaarten = []
    for sel in [
        '[data-stid="lodging-card-responsive"]',
        'li[data-stid="open-hotel-information"]',
        'article[class*="uitk-card"]',
    ]:
        kaarten = page.query_selector_all(sel)
        if kaarten:
            break

    for rank, kaart in enumerate(kaarten, start=1):
        naam = None
        for sel in [
            '[data-stid="content-hotel-title"]',
            "h3",
            "h2",
            '[class*="title"]',
        ]:
            el = kaart.query_selector(sel)
            if el:
                t = el.inner_text().strip()
                if t:
                    naam = t
                    break

        if not naam:
            continue

        prijs = None
        for sel in [
            '[data-stid="price-summary"]',
            '[data-stid="price-display"]',
            '[class*="PriceSummary"]',
            '[class*="price-summary"]',
            '[class*="price"]',
        ]:
            el = kaart.query_selector(sel)
            if el:
                p = _parse_eur_prijs(el.inner_text())
                if p:
                    prijs = p
                    break

        return prijs, rank

    return None, None


def scrape_expedia(hotels: list, aankomst: str, vertrek: str) -> dict:
    """
    Haalt Expedia prijs en rank op voor elk hotel in de lijst.

    Parameters
    ----------
    hotels   : lijst van hotel-dicts met minimaal {"naam": str}
    aankomst : YYYY-MM-DD
    vertrek  : YYYY-MM-DD

    Geeft dict terug:
      { hotel_naam: {"prijs": float|None, "rank": int|None} }
    """
    resultaten = {h["naam"]: {"prijs": None, "rank": None} for h in hotels}

    if not PLAYWRIGHT_BESCHIKBAAR:
        return resultaten

    with sync_playwright() as pw:
        browser, context = _pw_context(pw)

        for hotel in hotels:
            naam = hotel["naam"]
            page = context.new_page()
            try:
                prijs, rank = _zoek_hotel_expedia_pagina(page, naam, aankomst, vertrek)
                resultaten[naam] = {"prijs": prijs, "rank": rank}
            except PlaywrightTimeout:
                pass
            except Exception as e:
                print(f"  [Expedia] Fout bij {naam}: {e}")
            finally:
                page.close()

        browser.close()

    return resultaten
