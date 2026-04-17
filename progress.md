# Hotel Rates Monitor — Projectstatus

**Laatste update: 16 april 2026**

## Status: volledig operationeel + OTA monitoring

Alle 9 hotels worden gemonitord. De scraper haalt 3x per dag automatisch de goedkoopste beschikbare standaard tweepersoonskamer voor de volgende nacht op, schrijft de resultaten naar Google Sheets en vernieuwt het dashboard.

Per hotel worden drie prijsbronnen vergeleken:
- Directe websiteprijs
- Booking.com prijs + zoekresultaatpositie (rank) bij naamszoekactie
- Expedia prijs + rank (geblokkeerd door bot-detectie — zie sectie OTA)

---

## Hotels

| Hotel | Type | Methode | Stad | Booking.com slug | Status |
|---|---|---|---|---|---|
| Van der Valk Hengelo | Eigen hotel | Valkenhorst JSON-API | Hengelo | `van-der-valk-hengelo.nl` | Werkt |
| Van der Valk Enschede | Concurrent | Valkenhorst JSON-API | Enschede | `van-der-valk-enschede.nl` | Werkt |
| Van der Valk Deventer | Concurrent | Valkenhorst JSON-API | Deventer | `van-der-valk-deventer.nl` | Werkt |
| Van der Valk Zwolle | Concurrent | Valkenhorst JSON-API | Zwolle | `van-der-valk-zwolle.nl` | Werkt |
| Van der Valk Apeldoorn | Concurrent | Valkenhorst JSON-API | Apeldoorn | `van-der-valk-apeldoorn.nl` | Werkt |
| Van der Valk Theaterhotel Almelo | Concurrent | HTML scraper (requests + BeautifulSoup) | Almelo | `theaterhotel-almelo.nl` | Werkt |
| U-park Hotel Enschede | Concurrent | Playwright — Guestline `/enhanced` API | Enschede | `u-parkhotel.nl` | Werkt |
| City Hotel Hengelo | Concurrent | Playwright — Leonardo Hotels boekingspagina | Hengelo | `city-hotel-hengelo.nl` | Werkt |
| Lumen Hotel Zwolle | Concurrent | Playwright — SmartHotel IBE body-tekst | Zwolle | `lumen.nl` | Werkt |

---

## Bestanden

| Bestand | Functie |
|---|---|
| `scraper.py` | Haalt directe kamerprijzen op voor alle 9 hotels |
| `scraper_ota.py` | Haalt Booking.com prijzen + ranks op per hotel (naamszoekactie + slug-verificatie) |
| `sheets_writer.py` | Voert scraper uit, schrijft naar Google Sheets, vernieuwt dashboard |
| `dashboard.py` | Genereert `dashboard.html` vanuit `data.json` |
| `dashboard.html` | Lokaal HTML-dashboard, gesynct naar OneDrive (alleen als map bestaat) |
| `data.json` | Output van de meest recente scraper-run |
| `credentials.json` | Google Service Account — staat in `.gitignore`, nooit committen |
| `.github/workflows/hotel-rates.yml` | GitHub Actions workflow voor automatisch draaien in de cloud |

---

## Technische details per scraper-type

### Valkenhorst (VdV Hengelo, Enschede, Deventer, Zwolle, Apeldoorn)
- Endpoint: `/api/availabilityapi/getavailability`
- Eerst boekingspagina ophalen voor sessie-cookies, dan JSON-request met `Accept: application/json`
- Alleen beschikbare kamers zitten in de response; `MinPrice` is de goedkoopste rate per kamer
- Prijzen inclusief BTW en toeristenbelasting; `bookingsType=979`

| Hotel | hotelId |
|---|---|
| Hengelo | 23 |
| Enschede | 243 |
| Deventer | 302 |
| Zwolle | 254 |
| Apeldoorn | 305 |

### Theaterhotel Almelo
- `requests` + `BeautifulSoup` op `theaterhotel.nl/nl/kamers-suites/`
- Kamer beschikbaar als `vp-receipt-summary` én `a[data-test-id="persuade-card-cta"]` aanwezig zijn
- Pakt `data-test-id="total-price"`: kamerprijs + €3,80 toeristenbelasting

### U-park Hotel Enschede — Guestline
- Playwright laadt `booking.eu.guestline.app/UPARK/availability` (sessie + cookie-consent)
- JS-fetch naar `/api/availabilities/UPARK/UPARK/enhanced?arrival=...&departure=...&adults=2`
- `amountAfterTax` per kamer; tarieven met `INCL` in de rateId (ontbijt) worden overgeslagen
- Kamer-namen via `/api/roomRates/UPARK/UPARK`

### City Hotel Hengelo — Leonardo Hotels
- Playwright navigeert direct naar:
  `https://www.leonardo-hotels.com/booking?hotel=leonardo-hotel-hengelo-city-center&from=...&to=...`
- Body-tekst parser: zoekt `Slide X of Y → [naam] → Room Only → Non-member Rate → €XXX`
- Goedkoopste "Room Only" prijs (excl. ontbijt, non-member tarief)

### Lumen Hotel Zwolle — SmartHotel IBE
- Playwright navigeert naar:
  `https://ibe.smarthotel.nl/hotel/41133d04-419a-487d-b305-1b79a4690302/{aankomst}/{vertrek}/2/0/0/0/rooms`
- Body-tekst parser: zoekt `Prijzen - [naam] → Overnachting exclusief ontbijt → €XXX`
- Filtert non-refundable en toegankelijkheidskamers uit

### OTA scraping — Booking.com (scraper_ota.py)
- Eén Playwright-sessie voor alle 9 hotels (browser hergebruikt)
- Zoekterm per hotel → slug-verificatie via `[data-testid="title-link"]` href
  - Hiermee wordt het exacte hotel geïdentificeerd, geen fuzzy matching
- U-park heeft aparte `booking_zoekterm`: "U Parkhotel Enschede"
  (bij "U-park Hotel Enschede" geeft Booking.com Taiwanese resultaten)
- Rank = positie in zoekresultaten bij naamszoekactie (1 = eerste resultaat)
- Prijsstrategie:
  1. Standaard prijselement `[data-testid="price-and-discounted-price"]`
  2. Fallback: "Al vanaf €X"-carousel voor de gevraagde aankomstdatum

### OTA scraping — Expedia
- Geblokkeerd door Expedia bot-detectie (CAPTCHA: "Toon ons van je menselijke kant")
- Code staat in `scraper_ota.py` maar retourneert `None` voor alle hotels
- Oplossing vereist Expedia Rapid API (affiliate-account) of andere aanpak

---

## Google Sheets
- Sheet ID: `1QIitW5l90dYN0palPrbGM81m6tqKuvvLgPXqn6lSXwI`
- Kolommen: `timestamp | hotelnaam | kamernaam | tarieftype | prijs | booking_prijs | booking_rank | expedia_prijs | expedia_rank`
- Elke run voegt 9 rijen toe

---

## Dashboard
- Gegenereerd door `dashboard.py` op basis van `data.json`
- Lokaal gesynct naar OneDrive: `Documenten\Hotel Tarieven\dashboard.html`
  (sync wordt overgeslagen als de OneDrive-map niet bestaat, bv. op GitHub Actions)
- Kolommen: Hotel | Kamertype | Directe prijs | Booking.com (prijs + rank) | Expedia | vs. eigen hotel
- Rank badge kleurcodering: groen (#1–3), oranje (#4–7), rood (#8+)

---

## Automatisering

### Windows Taakplanner (lokaal — alleen als laptop aan is)

| Taaknaam | Tijd | Tijdslimiet |
|---|---|---|
| HotelRates_0700 | 07:00 | 30 min |
| HotelRates_1200 | 12:00 | 30 min |
| HotelRates_1800 | 18:00 | 30 min |

`StartWhenAvailable` zorgt dat gemiste runs alsnog worden uitgevoerd bij opstarten.

### GitHub Actions (cloud — draait ook als laptop uitstaat)

Workflow: `.github/workflows/hotel-rates.yml`

| Cron (UTC) | Lokale tijd CEST (zomer) | Lokale tijd CET (winter) |
|---|---|---|
| `0 5 * * *` | 07:00 | 06:00 |
| `0 10 * * *` | 12:00 | 11:00 |
| `0 16 * * *` | 18:00 | 17:00 |

In de winter (okt–apr) loopt de trigger 1 uur vroeger. Pas dan de cron-tijden aan naar `0 6`, `0 11`, `0 17`.

#### ⚠ GitHub Actions is nog NIET actief — vereiste stappen:

**Stap 1 — Git-repo initialiseren (terminal in `hotel-rates` map):**
```
git init
git add .
git commit -m "Initial commit"
```

**Stap 2 — Private repo aanmaken op GitHub:**
Ga naar https://github.com/new → naam `hotel-rates` → Private → Create (niets aanvinken).

**Stap 3 — Code pushen:**
```
git remote add origin https://github.com/JOUW_GEBRUIKERSNAAM/hotel-rates.git
git branch -M main
git push -u origin main
```

**Stap 4 — Google credentials als Secret toevoegen:**
Ga naar `github.com/JOUW_GEBRUIKERSNAAM/hotel-rates` →
**Settings → Secrets and variables → Actions → New repository secret**

| Veld | Waarde |
|---|---|
| Name | `GOOGLE_CREDENTIALS_JSON` |
| Secret | volledige inhoud van `credentials.json` (plak het JSON-bestand) |

**Stap 5 — Testen:**
Ga naar **Actions → Hotel Rates Monitor → Run workflow** en controleer of de run slaagt.

Na een geslaagde run commit de workflow automatisch bijgewerkte `data.json` en `dashboard.html` terug naar de repo.

---

## Installatie-vereisten (lokaal)
```
pip install requests beautifulsoup4 gspread google-auth playwright
python -m playwright install chromium
```
