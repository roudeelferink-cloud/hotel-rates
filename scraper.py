#!/usr/bin/env python3
"""
Hotel prijs scraper - goedkoopste standaard tweepersoonskamer voor morgen.

Hotels en booking systemen:
  # Eigen hotel (referentie)
  1. Van der Valk Hengelo       (hotelhengelo.nl)          -> Valkenhorst
  # Concurrenten
  2. Van der Valk Enschede      (vandervalkhotelenschede.nl) -> Valkenhorst
  3. Van der Valk Deventer      (hoteldeventer.nl)           -> Valkenhorst
  4. Van der Valk Zwolle        (hotelzwolle.nl)             -> Valkenhorst
  5. Van der Valk Apeldoorn     (valkhotelapeldoorn.nl)      -> Valkenhorst
  6. Theaterhotel Almelo        (theaterhotel.nl)            -> vp-receipt-summary componenten
  7. U-park Hotel Enschede      (uparkhotel.nl)              -> Guestline IBE (Playwright)
  8. City Hotel Hengelo         (cityhotelhengelo.com)       -> Leonardo Hotels IBE (Playwright)
  9. Lumen Hotel Zwolle         (lumenzwolle.nl)             -> SmartHotel IBE (Playwright)

Hotels 7-9 worden gescraped met Playwright (headless Chromium) omdat hun booking engines
volledig client-side gerenderd zijn.
Installatie: pip install playwright && python -m playwright install chromium

BTW: De getoonde prijzen zijn consumentenprijzen. Op grond van de Prijzenwet zijn deze
inclusief BTW. Het hotelkamertarief valt momenteel onder het 21% BTW-tarief.
De websiteprijzen zijn als zodanig bruikbaar voor vergelijking; geen herberekening nodig.

Toeristenbelasting:
  - Van der Valk hotels (Valkenhorst): prijzen zijn inclusief toeristenbelasting ("incl. citytax")
  - Theaterhotel Almelo: scraper pakt het TOTAAL (kamerprijs + EUR 3,80 toeristenbelasting)
  - Hanze Hotel is verwijderd uit de lijst

Ontbijt: alle hotels tonen prijzen exclusief ontbijt (Hanze vermeldde dit expliciet;
de Van der Valk hotels en Theaterhotel vermelden het niet maar serveren het apart).

Gebruik:
  pip install requests beautifulsoup4 playwright
  python -m playwright install chromium
  python scraper.py
"""
import json
import re
from datetime import date, timedelta, datetime

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_BESCHIKBAAR = True
except ImportError:
    PLAYWRIGHT_BESCHIKBAAR = False

try:
    from scraper_ota import scrape_booking, scrape_expedia
    OTA_BESCHIKBAAR = True
except ImportError:
    OTA_BESCHIKBAAR = False

# Gedeelde sessie zodat sessie-cookies bewaard blijven tussen requests
_sessie = requests.Session()


# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------

HOTELS = [
    # --- Eigen hotel ---
    {
        "naam": "Van der Valk Hengelo",
        "eigen": True,
        "type": "valkenhorst",
        "url": "https://www.hotelhengelo.nl/api/availabilityapi/getavailability",
        "hotel_id": 23,
        "referer": "https://www.hotelhengelo.nl/kamer-boeken/",
        "stad": "Hengelo",
        "booking_slug": "van-der-valk-hengelo.nl",
    },
    # --- Concurrenten ---
    {
        "naam": "Van der Valk Enschede",
        "eigen": False,
        "type": "valkenhorst",
        "url": "https://www.vandervalkhotelenschede.nl/api/availabilityapi/getavailability",
        "hotel_id": 243,
        "referer": "https://www.vandervalkhotelenschede.nl/kamer-boeken/",
        "stad": "Enschede",
        "booking_slug": "van-der-valk-enschede.nl",
    },
    {
        "naam": "Van der Valk Deventer",
        "eigen": False,
        "type": "valkenhorst",
        "url": "https://www.hoteldeventer.nl/api/availabilityapi/getavailability",
        "hotel_id": 302,
        "referer": "https://www.hoteldeventer.nl/kamer-boeken/",
        "stad": "Deventer",
        "booking_slug": "van-der-valk-deventer.nl",
    },
    {
        "naam": "Van der Valk Zwolle",
        "eigen": False,
        "type": "valkenhorst",
        "url": "https://www.hotelzwolle.nl/api/availabilityapi/getavailability",
        "hotel_id": 254,
        "referer": "https://www.hotelzwolle.nl/kamer-boeken/",
        "stad": "Zwolle",
        "booking_slug": "van-der-valk-zwolle.nl",
    },
    {
        "naam": "Van der Valk Apeldoorn",
        "eigen": False,
        "type": "valkenhorst",
        "url": "https://www.valkhotelapeldoorn.nl/api/availabilityapi/getavailability",
        "hotel_id": 305,
        "referer": "https://www.valkhotelapeldoorn.nl/kamer-boeken/",
        "stad": "Apeldoorn",
        "booking_slug": "van-der-valk-apeldoorn.nl",
    },
    {
        "naam": "Van der Valk Theaterhotel Almelo",
        "eigen": False,
        "type": "theaterhotel",
        "url": "https://www.theaterhotel.nl/nl/kamers-suites/",
        "stad": "Almelo",
        "booking_slug": "theaterhotel-almelo.nl",
    },
    # --- Playwright (JS-rendered booking engines) ---
    {
        "naam": "U-park Hotel Enschede",
        "eigen": False,
        "type": "guestline",
        "property_code": "UPARK",
        "stad": "Enschede",
        "booking_slug": "u-parkhotel.nl",
        "booking_zoekterm": "U Parkhotel Enschede",  # 'U-park' geeft Taiwanese resultaten
    },
    {
        "naam": "City Hotel Hengelo",
        "eigen": False,
        "type": "leonardo",
        "hotel_slug": "leonardo-hotel-hengelo-city-center",
        "stad": "Hengelo",
        "booking_slug": "city-hotel-hengelo.nl",
    },
    {
        "naam": "Lumen Hotel Zwolle",
        "eigen": False,
        "type": "smarthotel",
        "hotel_id": "41133d04-419a-487d-b305-1b79a4690302",
        "stad": "Zwolle",
        "booking_slug": "lumen.nl",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = 20


# ---------------------------------------------------------------------------
# Hulpfunctie
# ---------------------------------------------------------------------------

def parse_prijs(tekst: str) -> float | None:
    """Extraheer eerste prijs (bijv. '121,00') als float."""
    m = re.search(r"(\d+[,.]\d{2})", tekst.replace("\xa0", " "))
    if m:
        return float(m.group(1).replace(",", "."))
    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def haal_prijs_valkenhorst(url: str, aankomst: str, vertrek: str, hotel_id: int, referer: str) -> tuple:
    """
    Van der Valk hotels (Valkenhorst booking systeem) — live beschikbaarheids-API.

    Endpoint: /api/availabilityapi/getavailability
    Geeft JSON terug met een "Rooms" lijst. Alleen beschikbare kamers worden teruggegeven.
    MinPrice is de goedkoopste rateplan voor die kamer op de opgegeven datum.
    Prijs is inclusief toeristenbelasting.

    Retourneert (prijs: float, kamer_type: str) van de goedkoopste beschikbare kamer, of (None, None).
    """
    # Haal eerst de boekingspagina op om sessie-cookies te verkrijgen
    _sessie.get(referer, headers=HEADERS, timeout=TIMEOUT)

    params = {
        "language": "nl",
        "startDate": aankomst,
        "endDate": vertrek,
        "adults": 2,
        "babies": 0,
        "children": 0,
        "hotelId": hotel_id,
        "bookingsType": 979,
    }
    api_headers = {
        **HEADERS,
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer,
    }
    resp = _sessie.get(url, params=params, headers=api_headers, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("HasRooms"):
        return None, None

    kamers = []
    for kamer in data.get("Rooms", []):
        naam = kamer.get("RoomName", "").strip()
        prijs_str = kamer.get("MinPrice")
        if naam and prijs_str:
            try:
                kamers.append((float(prijs_str), naam))
            except ValueError:
                pass

    if not kamers:
        return None, None

    goedkoopste = min(kamers, key=lambda x: x[0])
    return goedkoopste[0], goedkoopste[1]


def haal_prijs_theaterhotel(url: str, aankomst: str, vertrek: str) -> tuple:
    """
    Van der Valk Theaterhotel Almelo.

    Kamers staan in: <section class="card" data-test-class="persuade-card">
    Beschikbaarheid: aanwezigheid van <vp-receipt-summary> én <a data-test-id="persuade-card-cta">.
    Niet-beschikbare kamers hebben geen vp-receipt-summary of geen CTA-link.

    Prijsstructuur in vp-receipt-summary:
        <span data-test-id="receipt-item-name">Economy met balkon</span>
        <span data-test-id="receipt-item-price">EUR 69,00</span>   <- kamerprijs excl. belasting
        <span data-test-id="tourist-tax-price">EUR 3,80</span>     <- toeristenbelasting
        <span data-test-id="total-price">EUR 72,80</span>          <- TOTAAL (dit pakken we)

    Pakt het TOTAAL incl. toeristenbelasting van de goedkoopste beschikbare kamer,
    zodat het vergelijkbaar is met de Van der Valk Valkenhorst prijzen.

    Retourneert (prijs: float, kamer_type: str) of (None, None).
    """
    params = {"arrival": aankomst, "departure": vertrek, "adults": 2, "rooms": 1}
    resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    kamers = []
    for section in soup.select('section.card[data-test-class="persuade-card"]'):
        # Sla amenities-kaart over (heeft geen h3.heading-group)
        if not section.find("h3", class_="heading-group"):
            continue

        # Beschikbaarheidscheck: vp-receipt-summary én boekingslink vereist
        vp = section.find("vp-receipt-summary")
        cta = section.find("a", attrs={"data-test-id": "persuade-card-cta"})
        if not vp or not cta:
            continue

        naam_el = vp.find(attrs={"data-test-id": "receipt-item-name"})
        totaal_el = vp.find(attrs={"data-test-id": "total-price"})
        if not naam_el or not totaal_el:
            continue

        naam = naam_el.get_text(strip=True)
        prijs = parse_prijs(totaal_el.get_text())
        if prijs is not None:
            kamers.append((prijs, naam))

    if not kamers:
        return None, None

    goedkoopste = min(kamers, key=lambda x: x[0])
    return goedkoopste[0], goedkoopste[1]


# ---------------------------------------------------------------------------
# Playwright hulpfuncties
# ---------------------------------------------------------------------------

_PW_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _pw_context(pw):
    """Maak een browser context met realistische browser-fingerprint."""
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=_PW_USER_AGENT,
        locale="nl-NL",
        viewport={"width": 1280, "height": 900},
        extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9"},
    )
    return browser, context




# ---------------------------------------------------------------------------
# Playwright scrapers
# ---------------------------------------------------------------------------

def haal_prijs_guestline(aankomst: str, vertrek: str, property_code: str) -> tuple:
    """
    U-park Hotel Enschede via Guestline booking engine.

    Strategie:
    1. Laad de beschikbaarheidspagina (sessie-cookies instellen, cookie-consent sluiten)
    2. Roep via JS-fetch direct de `/enhanced` beschikbaarheids-API aan
    3. Kruisverwijzing met `/roomRates` voor kamer-namen
    4. Goedkoopste prijs excl. ontbijt retourneren

    Guestline API-structuur:
      GET /api/availabilities/{code}/{code}/enhanced?arrival=YYYY-MM-DD&departure=YYYY-MM-DD&adults=2
      Response: { "availabilities": { "rooms": [ { "roomId": str, "rateId": str,
                   "prices": [ { "amountAfterTax": float } ] } ] } }
      rateId "BAR_INCL" = inclusief ontbijt — wordt overgeslagen.

    Retourneert (prijs: float, kamer_type: str) of gooit een Exception.
    """
    if not PLAYWRIGHT_BESCHIKBAAR:
        raise RuntimeError("Playwright niet geïnstalleerd (pip install playwright && python -m playwright install chromium)")

    pagina_url = (
        f"https://booking.eu.guestline.app/{property_code}/availability"
        f"?CheckIn={aankomst}&CheckOut={vertrek}&Adults=2&Children=0&Infants=0"
    )

    with sync_playwright() as pw:
        browser, context = _pw_context(pw)
        page = context.new_page()

        try:
            page.goto(pagina_url, wait_until="networkidle", timeout=60_000)

            # Cookie-consent sluiten zodat de sessie geldig is
            for sel in ["button:has-text('Accept')", "button:has-text('Accepteer')"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            # Kamer-namen ophalen
            room_naam: dict[str, str] = {}
            try:
                rr = page.evaluate(
                    f"async () => {{"
                    f"  const r = await fetch('/api/roomRates/{property_code}/{property_code}?language=nl&debug=false');"
                    f"  return r.ok ? await r.json() : null;"
                    f"}}"
                )
                if rr and isinstance(rr.get("rooms"), list):
                    for r in rr["rooms"]:
                        room_naam[r["id"]] = r["name"]
            except Exception:
                pass

            # Beschikbaarheid + prijzen via enhanced-API
            result = page.evaluate(
                f"async () => {{"
                f"  const url = '/api/availabilities/{property_code}/{property_code}/enhanced"
                f"?arrival={aankomst}&departure={vertrek}&adults=2&children=0&infants=0';"
                f"  const r = await fetch(url);"
                f"  return r.ok ? await r.json() : null;"
                f"}}"
            )

            if not result or "availabilities" not in result:
                raise ValueError(f"Geen beschikbaarheidsdata (Guestline, {property_code})")

            kamers = []
            for room in result["availabilities"].get("rooms", []):
                rate_id = room.get("rateId", "")
                if "INCL" in rate_id:        # ontbijt-inclusief tarieven overslaan
                    continue
                room_id = room.get("roomId", "")
                for price in room.get("prices", []):
                    p = price.get("amountAfterTax")
                    if p and float(p) > 0:
                        naam = room_naam.get(room_id, room_id)
                        kamers.append((float(p), naam))

            if not kamers:
                raise ValueError(f"Geen kamerprijzen gevonden (Guestline, {property_code})")

            return min(kamers, key=lambda x: x[0])

        except PlaywrightTimeout:
            raise TimeoutError(f"Timeout bij laden Guestline pagina ({property_code})")
        finally:
            browser.close()


def haal_prijs_smarthotel(aankomst: str, vertrek: str, hotel_id: str) -> tuple:
    """
    Lumen Hotel Zwolle via SmartHotel IBE.

    Directe URL met datums in het pad:
      https://ibe.smarthotel.nl/hotel/{id}/{aankomst}/{vertrek}/2/0/0/0/rooms

    Strategie: body-tekst parsen op "Prijzen - <kamer>" blokken en daarin de
    "Overnachting exclusief ontbijt" prijs pakken.

    DOM-patroon:
      Prijzen - <kamer_naam>
      Overnachting exclusief ontbijt
      € XX,XX

    Retourneert (prijs: float, kamer_type: str) of gooit een Exception.
    """
    if not PLAYWRIGHT_BESCHIKBAAR:
        raise RuntimeError("Playwright niet geïnstalleerd")

    url = f"https://ibe.smarthotel.nl/hotel/{hotel_id}/{aankomst}/{vertrek}/2/0/0/0/rooms"

    with sync_playwright() as pw:
        browser, context = _pw_context(pw)
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(2_000)

            body = page.inner_text("body")
            kamers = _smarthotel_parse_body(body)

            if not kamers:
                raise ValueError(f"Geen kamerprijzen gevonden (SmartHotel, id={hotel_id})")

            return min(kamers, key=lambda x: x[0])

        except PlaywrightTimeout:
            raise TimeoutError(f"Timeout bij laden SmartHotel pagina (id={hotel_id})")
        finally:
            browser.close()


_TOEGANKELIJKHEID_WOORDEN = {
    "mindervalide", "toegankelijk", "accessible", "wheelchair",
    "rolstoel", "handicap", "disability",
}


def _smarthotel_parse_body(body: str) -> list:
    """
    Parseer SmartHotel IBE body-tekst.
    Zoekt "Prijzen - <naam>\\nOvernachting exclusief ontbijt\\n€ XX,XX" blokken.
    Filtert "non refundable" en toegankelijkheidskamers (mindervalide etc.) uit.
    Retourneert lijst van (prijs: float, naam: str).
    """
    kamers = []
    blokken = re.split(r"Prijzen - ", body)
    for blok in blokken[1:]:
        regels = blok.splitlines()
        naam = regels[0].strip() if regels else "onbekend"

        # Sla toegankelijkheidskamers over
        naam_lower = naam.lower()
        if any(woord in naam_lower for woord in _TOEGANKELIJKHEID_WOORDEN):
            continue

        # Zoek de prijs na "Overnachting exclusief ontbijt" (niet non-refundable)
        for i, regel in enumerate(regels):
            if "exclusief ontbijt" in regel.lower() and "non" not in regel.lower() and "refund" not in regel.lower():
                for j in range(i + 1, min(i + 5, len(regels))):
                    p = parse_prijs(regels[j])
                    if p:
                        kamers.append((p, naam))
                        break
                break
    return kamers


def haal_prijs_leonardo(aankomst: str, vertrek: str, hotel_slug: str) -> tuple:
    """
    City Hotel Hengelo (nu Leonardo Hotel Hengelo City Center) via Leonardo Hotels IBE.

    cityhotelhengelo.com redirecteert naar leonardo-hotels.com.
    De directe boekingspagina gebruikt het URL-patroon:
      https://www.leonardo-hotels.com/booking?hotel={slug}&from={aankomst}&to={vertrek}
        &stay=leisure&redeemPoints=false&paxesConfig=adults,2,children,0,infants,0

    DOM-patroon per kamer:
      [kamer_naam]
      Select Room
      Room Only
      Best Available Rate excluding Breakfast
      ...
      Non-member Rate
      1 Night
      €XXX,XX

    Retourneert (prijs: float, kamer_type: str) of gooit een Exception.
    """
    if not PLAYWRIGHT_BESCHIKBAAR:
        raise RuntimeError("Playwright niet geïnstalleerd")

    url = (
        f"https://www.leonardo-hotels.com/booking"
        f"?hotel={hotel_slug}"
        f"&from={aankomst}&to={vertrek}"
        f"&stay=leisure&redeemPoints=false"
        f"&paxesConfig=adults,2,children,0,infants,0"
    )

    with sync_playwright() as pw:
        browser, context = _pw_context(pw)
        page = context.new_page()

        try:
            page.goto(url, wait_until="load", timeout=90_000)
            page.wait_for_timeout(5_000)

            body = page.inner_text("body")
            kamers = _leonardo_parse_body(body)

            if not kamers:
                raise ValueError(f"Geen kamerprijzen gevonden (Leonardo, {hotel_slug})")

            return min(kamers, key=lambda x: x[0])

        except PlaywrightTimeout:
            raise TimeoutError(f"Timeout bij laden Leonardo Hotels pagina ({hotel_slug})")
        finally:
            browser.close()


def _leonardo_parse_body(body: str) -> list:
    """
    Parseer Leonardo Hotels boekingspagina body-tekst.

    Elk kamer-blok bevat:
      "Room Only\\n...\\nNon-member\\u00a0Rate\\n1\\u00a0Night\\n€XXX,XX"

    Kamer-naam staat in een "Slide X of Y\\n<naam>" patroon.
    Retourneert lijst van (prijs: float, naam: str).
    """
    kamers = []

    # Kamer-naam + "Room Only" prijs
    # Patroon: naam wordt voorafgegaan door "Slide X of Y\n"
    # Prijs staat na "Non-member\u00a0Rate\n1\u00a0Night\n€"
    blokken = re.split(r"Slide \d+ of \d+\n", body)
    for blok in blokken[1:]:
        regels = blok.splitlines()
        naam = regels[0].strip() if regels else "onbekend"
        # Sla blokken zonder "Room Only" over
        if "Room Only" not in blok:
            continue
        # Zoek het "Non-member Rate" price-blok binnen de "Room Only" sectie
        room_only_deel = blok.split("Bed And Breakfast")[0]  # stop bij ontbijt-sectie
        for i, regel in enumerate(room_only_deel.splitlines()):
            if "Non-member" in regel:
                # Prijs staat 1-2 regels verder
                for j in range(i + 1, min(i + 5, len(room_only_deel.splitlines()))):
                    p = parse_prijs(room_only_deel.splitlines()[j])
                    if p:
                        kamers.append((p, naam))
                        break
                break

    return kamers


# ---------------------------------------------------------------------------
# Hoofd scrape-functie
# ---------------------------------------------------------------------------

def scrape_hotel(hotel: dict, aankomst: str, vertrek: str) -> dict:
    """Haal prijs op voor een hotel en geef gestructureerde data terug."""
    result = {
        "naam": hotel["naam"],
        "eigen": hotel.get("eigen", False),
        "datum": aankomst,
        "timestamp": datetime.now().isoformat(),
        "prijs": None,
        "kamer_type": None,
        "fout": None,
        "booking_prijs": None,
        "booking_rank": None,
        "expedia_prijs": None,
        "expedia_rank": None,
    }

    if hotel["type"] == "niet_ondersteund":
        result["fout"] = hotel.get("reden", "Niet ondersteund")
        return result

    try:
        if hotel["type"] == "valkenhorst":
            prijs, kamer = haal_prijs_valkenhorst(
                hotel["url"], aankomst, vertrek,
                hotel["hotel_id"], hotel["referer"],
            )
        elif hotel["type"] == "theaterhotel":
            prijs, kamer = haal_prijs_theaterhotel(hotel["url"], aankomst, vertrek)
        elif hotel["type"] == "guestline":
            prijs, kamer = haal_prijs_guestline(aankomst, vertrek, hotel["property_code"])
        elif hotel["type"] == "smarthotel":
            prijs, kamer = haal_prijs_smarthotel(aankomst, vertrek, hotel["hotel_id"])
        elif hotel["type"] == "leonardo":
            prijs, kamer = haal_prijs_leonardo(aankomst, vertrek, hotel["hotel_slug"])
        else:
            result["fout"] = f"Onbekend type: {hotel['type']}"
            return result

        if prijs is None:
            result["fout"] = "Prijs niet gevonden op de pagina"
        else:
            result["prijs"] = prijs
            result["kamer_type"] = kamer

    except requests.RequestException as e:
        result["fout"] = f"Netwerkfout: {e}"
    except Exception as e:
        result["fout"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> list:
    morgen = date.today() + timedelta(days=1)
    overmorgen = morgen + timedelta(days=1)
    aankomst = morgen.strftime("%Y-%m-%d")
    vertrek = overmorgen.strftime("%Y-%m-%d")

    print(f"Prijzen ophalen voor: {aankomst} -> {vertrek}")
    print("-" * 55)

    resultaten = []
    for hotel in HOTELS:
        label = "[eigen] " if hotel.get("eigen") else "        "
        print(f"  {label}{hotel['naam']} ...", end="", flush=True)
        data = scrape_hotel(hotel, aankomst, vertrek)
        resultaten.append(data)
        if data["prijs"] is not None:
            print(f"  EUR {data['prijs']:.2f}  ({data['kamer_type']})")
        else:
            print(f"  --  {data['fout']}")

    # OTA prijzen en ranks (Booking.com + Expedia) — zoekop op hotelnaam
    if OTA_BESCHIKBAAR:
        print("\nOTA prijzen ophalen (Booking.com)...")
        booking_data = scrape_booking(HOTELS, aankomst, vertrek)

        print("OTA prijzen ophalen (Expedia)...")
        expedia_data = scrape_expedia(HOTELS, aankomst, vertrek)

        for i, hotel in enumerate(HOTELS):
            naam = hotel["naam"]
            b = booking_data.get(naam, {})
            e = expedia_data.get(naam, {})
            resultaten[i]["booking_prijs"] = b.get("prijs")
            resultaten[i]["booking_rank"] = b.get("rank")
            resultaten[i]["expedia_prijs"] = e.get("prijs")
            resultaten[i]["expedia_rank"] = e.get("rank")

            b_prijs, b_rank = b.get("prijs"), b.get("rank")
            e_prijs, e_rank = e.get("prijs"), e.get("rank")
            b_str = f"EUR {b_prijs:.2f}  #{b_rank}" if b_prijs else ("--" if b_rank is None else f"--  #{b_rank}")
            e_str = f"EUR {e_prijs:.2f}  #{e_rank}" if e_prijs else ("--" if e_rank is None else f"--  #{e_rank}")
            print(f"  {naam:40s}  B.com: {b_str:20s}  Expedia: {e_str}")
    else:
        print("\n[OTA scraping overgeslagen — scraper_ota.py niet gevonden]")

    output_bestand = "data.json"
    with open(output_bestand, "w", encoding="utf-8") as f:
        json.dump(resultaten, f, ensure_ascii=False, indent=2)

    print(f"\nResultaten opgeslagen in {output_bestand}")
    return resultaten


if __name__ == "__main__":
    main()
