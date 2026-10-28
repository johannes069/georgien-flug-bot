#!/usr/bin/env python3
"""
=============================================================================
Flugpreis-Bot: Georgien-Schnäppchen-Finder
=============================================================================
Dieses Skript sucht automatisch über die Aviasales / Travelpayouts Data API
nach günstigen Flügen von NRW/Hessen/Niedersachsen nach Georgien, vergleicht
die Preise mit deinen Grenzen und schickt echte Deals per Telegram.
"""

import os
import sys
import json
import time
import argparse
import statistics
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import requests
import yaml

# Bekannte Airlines für schönere Telegram-Nachrichten
AIRLINE_NAMES: Dict[str, str] = {
    "W6": "Wizz Air",
    "W4": "Wizz Air Malta",
    "PC": "Pegasus Airlines",
    "TK": "Turkish Airlines",
    "LH": "Lufthansa",
    "EW": "Eurowings",
    "FR": "Ryanair",
    "A9": "Georgian Airways",
    "XQ": "SunExpress",
    "OS": "Austrian Airlines",
    "LO": "LOT Polish Airlines",
    "XC": "Corendon Airlines",
    "DE": "Condor",
    "KL": "KLM",
    "AF": "Air France",
}

# Pfade zu den Daten- und Konfigurationsdateien
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
DATA_DIR = BASE_DIR / "data"
NOTIFIED_DEALS_PATH = DATA_DIR / "notified_deals.json"
PRICE_HISTORY_PATH = DATA_DIR / "price_history.json"
STATUS_PATH = DATA_DIR / "status.json"


def load_config() -> dict:
    """Lädt die Konfigurationsdatei config.yaml."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json_file(path: Path, default: Any) -> Any:
    """Lädt eine JSON-Datei oder gibt einen Standardwert zurück, falls sie nicht existiert."""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Warnung: Konnte {path.name} nicht lesen ({e}). Verwende Standardwert.")
            return default
    return default


def save_json_file(path: Path, data: Any) -> None:
    """Speichert Daten formatiert in einer JSON-Datei."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_airline_name(code: str) -> str:
    """Gibt den Klarnamen der Airline zurück oder das Kürzel, falls unbekannt."""
    return AIRLINE_NAMES.get(code.upper(), code.upper())


def format_date_german(date_str: str) -> str:
    """Wandelt ein ISO-Datum (2027-02-15) in deutsches Format um (15.02.2027)."""
    try:
        # Falls ein Zeitstempel enthalten ist (z. B. 2027-02-15T08:30:00)
        pure_date = date_str.split("T")[0]
        dt = datetime.strptime(pure_date, "%Y-%m-%d")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return date_str


def calculate_stay_days(dep_date_str: str, ret_date_str: str) -> Optional[int]:
    """Berechnet die Anzahl der Reisetage zwischen Hin- und Rückflug."""
    try:
        dep = datetime.strptime(dep_date_str.split("T")[0], "%Y-%m-%d")
        ret = datetime.strptime(ret_date_str.split("T")[0], "%Y-%m-%d")
        return (ret - dep).days
    except Exception:
        return None


def create_google_flights_link(origin: str, destination: str, dep_date_str: str, ret_date_str: str) -> str:
    """
    Erstellt einen direkten Google Flights Link mit vorausgewählten Flughäfen und Reisedaten.
    """
    dep = dep_date_str.split("T")[0]
    ret = ret_date_str.split("T")[0]
    return f"https://www.google.com/travel/flights?q=Flights%20to%20{destination}%20from%20{origin}%20on%20{dep}%20through%20{ret}"


def send_telegram_message(token: str, chat_id: str, html_text: str) -> bool:
    """
    Sendet eine formatierte Nachricht an deinen Telegram-Chat über den Telegram Bot API-Endpunkt.
    Teilt Nachrichten automatisch auf, falls sie das Telegram-Limit von 4096 Zeichen überschreiten.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Telegram erlaubt maximal 4096 Zeichen pro Nachricht
    max_length = 4000
    chunks = []
    
    if len(html_text) <= max_length:
        chunks = [html_text]
    else:
        # Nachricht abschnittsweise aufteilen
        parts = html_text.split("\n\n")
        current_chunk = ""
        for part in parts:
            if len(current_chunk) + len(part) + 2 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = part + "\n\n"
            else:
                current_chunk += part + "\n\n"
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

    success = True
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                print(f"❌ Telegram Fehler {resp.status_code}: {resp.text}")
                success = False
        except Exception as e:
            print(f"❌ Telegram Ausnahme: {e}")
            success = False

    return success


def fetch_prices_for_route(
    api_token: str,
    origin: str,
    destination: str,
    departure_month: str,
    currency: str = "eur",
) -> List[dict]:
    """
    Fragt günstige Flüge über den Aviasales Data API v3 Endpunkt ab.
    Sucht gezielt nach Hin- und Rückflügen für den angegebenen Monat.
    """
    url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": departure_month,
        "one_way": "false",  # Hin- und Rückflug
        "currency": currency,
        "sorting": "price",
        "limit": 30,
        "token": api_token,
    }
    headers = {
        "User-Agent": "GeorgiaFlightTrackerBot/1.0",
        "Accept": "application/json",
    }
    
    response = requests.get(url, params=params, headers=headers, timeout=20)
    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("success", False):
            return res_json.get("data", [])
        else:
            print(f"⚠️ API meldete Erfolg=False für {origin}->{destination} ({departure_month}): {res_json.get('error')}")
            return []
    elif response.status_code == 429:
        print("⚠️ API Rate-Limit erreicht (429 Too Many Requests).")
        raise requests.exceptions.RequestException("Rate limit exceeded")
    else:
        print(f"⚠️ API HTTP-Status {response.status_code} für {origin}->{destination}: {response.text}")
        response.raise_for_status()
        return []


def build_daily_summary(best_offer_per_route: Dict[str, dict], max_price: int, now_berlin: datetime) -> str:
    """Baut die tägliche Lebenszeichen-Nachricht mit den aktuell günstigsten Strecken."""
    header = (
        f"☀️ <b>Tagesbericht Flugpreis-Bot</b> ({now_berlin.strftime('%d.%m.%Y')})\n"
        "Der Bot läuft. Hier die günstigsten Preise, die er gerade kennt "
        f"(Feb/Mär 2027, 7–14 Tage, Hin & Zurück, dein Limit: {max_price} €):"
    )
    if not best_offer_per_route:
        return header + "\n\nℹ️ Heute hat die Flug-API für keine Strecke passende Angebote geliefert."

    top = sorted(best_offer_per_route.values(), key=lambda o: o["price"])[:5]
    lines = []
    for i, o in enumerate(top):
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
        link = create_google_flights_link(o["origin"], o["destination"], o["dep_date"], o["ret_date"])
        lines.append(
            f"{medal} <b>{o['price']} €</b> · {o['origin_name']} ➔ {o['destination_name']}\n"
            f"     {format_date_german(o['dep_date'])} – {format_date_german(o['ret_date'])} "
            f"({o['stay_days']} Tage), {get_airline_name(o['airline_code'])} · "
            f"<a href=\"{link}\">ansehen</a>"
        )
    gap = top[0]["price"] - max_price
    footer = (
        f"\n\n📊 Bestpreis liegt noch <b>{gap} €</b> über deinem Limit."
        if gap > 0 else "\n\n🎉 Bestpreis liegt unter deinem Limit!"
    )
    return header + "\n\n" + "\n".join(lines) + footer


def run_test_mode(telegram_token: str, telegram_chat_id: str) -> None:
    """Sendet eine Beispiel-Testnachricht, um zu prüfen, ob Telegram funktioniert."""
    print("🚀 Testmodus aktiv: Sende Beispiel-Deal an Telegram...")
    
    test_msg = (
        "<b>✅ Flugpreis-Bot: Verbindungstest erfolgreich!</b>\n\n"
        "Hallo! Dein Flugpreis-Bot ist startklar und kann dir Benachrichtigungen auf Telegram senden.\n\n"
        "<b>So wird ein Fund später aussehen:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✈️ <b>Dortmund (DTM) ➔ Kutaisi (KUT)</b>\n"
        "📅 <b>Hin:</b> 12.02.2027 | <b>Rück:</b> 21.02.2027 (9 Tage)\n"
        "💰 <b>Preis: 85 €</b> pro Person (Hin & Zurück)\n"
        "🏢 <b>Airline:</b> Wizz Air\n"
        "🎯 <b>Deal-Status:</b> 35 € unter deiner Maximalgrenze (120 €)!\n"
        "🔗 <a href=\"https://www.google.com/travel/flights?q=Flights%20to%20KUT%20from%20DTM%20on%202027-02-12%20through%202027-02-21\">Auf Google Flights ansehen & buchen</a>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<i>Der Bot sucht nun alle 30 Minuten vollautomatisch nach echten Schnäppchen.</i>"
    )
    
    ok = send_telegram_message(telegram_token, telegram_chat_id, test_msg)
    if ok:
        print("✅ Testnachricht erfolgreich über Telegram gesendet!")
    else:
        print("❌ Testnachricht konnte nicht gesendet werden. Bitte Telegram-Token und Chat-ID prüfen!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Flugpreis-Bot für Georgien-Reisen")
    parser.add_argument("--test", action="store_true", help="Sendet nur eine Telegram-Testnachricht")
    parser.add_argument("--dry-run", action="store_true", help="Führt die Suche aus, sendet aber keine Telegram-Nachrichten")
    args = parser.parse_args()

    # 1. Konfiguration laden
    config = load_config()
    
    # 2. Zugangsdaten aus Umgebungsvariablen (GitHub Secrets) auslesen
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    api_token = os.getenv("TRAVELPAYOUTS_TOKEN", "").strip()

    if not telegram_token or not telegram_chat_id:
        print("❌ Fehler: TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt in den Umgebungsvariablen!")
        sys.exit(1)

    # Wenn der Benutzer den Testmodus gewählt hat:
    if args.test:
        run_test_mode(telegram_token, telegram_chat_id)
        return

    if not api_token:
        print("❌ Fehler: TRAVELPAYOUTS_TOKEN fehlt in den Umgebungsvariablen!")
        sys.exit(1)

    # 3. Lokale Datenspeicher laden
    notified_deals = load_json_file(NOTIFIED_DEALS_PATH, default={})
    price_history = load_json_file(PRICE_HISTORY_PATH, default={})
    status_data = load_json_file(STATUS_PATH, default={"consecutive_errors": 0, "last_successful_run": None})

    # Parameter aus config.yaml
    origins = config.get("origins", [])
    destinations = config.get("destinations", [])
    months = config.get("months", ["2027-02", "2027-03"])
    
    min_stay = config.get("stay_duration", {}).get("min_days", 7)
    max_stay = config.get("stay_duration", {}).get("max_days", 14)
    
    max_price = config.get("deals", {}).get("max_price_eur", 120)
    rel_discount = config.get("deals", {}).get("relative_discount_percent", 30)
    min_history = config.get("deals", {}).get("min_history_samples", 3)
    price_drop_threshold = config.get("deals", {}).get("price_drop_threshold_eur", 10)
    
    currency = config.get("settings", {}).get("currency", "eur")
    delay = config.get("settings", {}).get("request_delay_seconds", 0.2)
    max_errors_alert = config.get("settings", {}).get("max_consecutive_errors_before_alert", 3)

    summary_cfg = config.get("daily_summary", {}) or {}
    summary_enabled = summary_cfg.get("enabled", True)
    summary_hour = summary_cfg.get("hour", 9)

    # Heutiges Datum in deutscher Zeit (für Tages-Historie und Tagesbericht)
    now_berlin = datetime.now(ZoneInfo("Europe/Berlin"))
    today = now_berlin.strftime("%Y-%m-%d")

    # Preis-Historie: pro Strecke EIN Bestpreis pro Tag, z. B. {"DTM_KUT": {"2026-10-28": 231}}
    # Altes Format (lange Liste mit immer denselben Preisen) wird verworfen, weil es
    # den "üblichen Preis" verfälscht hat.
    for rk in list(price_history.keys()):
        if not isinstance(price_history[rk], dict):
            print(f"♻️ Alte Preis-Historie für {rk} wird auf das neue Tagesformat umgestellt.")
            price_history[rk] = {}

    print(f"🔍 Starte Flugsuche: {len(origins)} Abflughäfen x {len(destinations)} Ziele x {len(months)} Monate")

    collected_deals: List[dict] = []
    total_queries = 0
    failed_queries = 0
    # Günstigstes passendes Angebot je Strecke in diesem Lauf (für Historie + Tagesbericht)
    best_offer_per_route: Dict[str, dict] = {}

    # 4. Suche über alle Strecken und Monate ausführen
    for origin_info in origins:
        orig = origin_info["code"]
        orig_name = origin_info.get("name", orig)

        for dest_info in destinations:
            dest = dest_info["code"]
            dest_name = dest_info.get("name", dest)
            route_key = f"{orig}_{dest}"

            # "Üblicher Preis" = Median der Tages-Bestpreise der VORHERIGEN Tage
            past_days = {d: p for d, p in price_history.get(route_key, {}).items() if d != today}
            median_price = statistics.median(past_days.values()) if past_days else None

            for month in months:
                total_queries += 1
                try:
                    time.sleep(delay)
                    raw_offers = fetch_prices_for_route(api_token, orig, dest, month, currency=currency)
                except Exception as e:
                    print(f"❌ Fehler bei Anfrage für {orig} -> {dest} ({month}): {e}")
                    failed_queries += 1
                    continue

                for offer in raw_offers:
                    price = offer.get("price")
                    dep_at = offer.get("departure_at")
                    ret_at = offer.get("return_at")
                    airline_code = offer.get("airline", "Unbekannt")
                    
                    if not price or not dep_at or not ret_at:
                        continue

                    # Aufenthaltsdauer prüfen (7 bis 14 Tage)
                    stay_days = calculate_stay_days(dep_at, ret_at)
                    if stay_days is None or stay_days < min_stay or stay_days > max_stay:
                        continue

                    # Günstigstes Angebot dieser Strecke im aktuellen Lauf merken
                    if route_key not in best_offer_per_route or price < best_offer_per_route[route_key]["price"]:
                        best_offer_per_route[route_key] = {
                            "origin": orig, "origin_name": orig_name,
                            "destination": dest, "destination_name": dest_name,
                            "dep_date": dep_at.split("T")[0], "ret_date": ret_at.split("T")[0],
                            "stay_days": stay_days, "price": price, "airline_code": airline_code,
                        }

                    # 5. Deal-Kriterien prüfen
                    is_absolute_deal = price <= max_price
                    is_relative_deal = False
                    savings_info = ""

                    if median_price is not None and len(past_days) >= min_history:
                        discount_threshold = median_price * (1 - (rel_discount / 100.0))
                        if price <= discount_threshold:
                            is_relative_deal = True
                            diff = median_price - price
                            savings_info = f"{int(diff)} € günstiger als üblich (Schnitt: ~{int(median_price)} €)"

                    if not (is_absolute_deal or is_relative_deal):
                        # Weder unter der absoluten Grenze noch unter der relativen Grenze
                        continue

                    # Deal-Begründung formulieren
                    reason = ""
                    if is_absolute_deal and is_relative_deal:
                        reason = f"🔥 Hammer-Deal: {savings_info} & unter deiner Maximalgrenze ({max_price} €)!"
                    elif is_absolute_deal:
                        diff = max_price - price
                        reason = f"🎯 Deal: {price} € (liegt unter deinem Limit von {max_price} €)"
                    else:
                        reason = f"📉 Starker Rabatt: {savings_info}"

                    # 6. Duplikatsprüfung
                    dep_date_clean = dep_at.split("T")[0]
                    ret_date_clean = ret_at.split("T")[0]
                    deal_key = f"{orig}_{dest}_{dep_date_clean}_{ret_date_clean}_{airline_code}"

                    is_repeat = deal_key in notified_deals
                    if is_repeat:
                        prev_price = notified_deals[deal_key].get("last_price", 999999)
                        if price <= prev_price - price_drop_threshold:
                            # Preis ist nochmals spürbar gefallen!
                            reason = f"💥 <b>PREIS GEFALLEN!</b> Von {prev_price} € auf nur noch <b>{price} €</b> gesunken!"
                        else:
                            # Bereits gemeldet und nicht deutlich billiger geworden -> ignorieren
                            continue

                    # Deal erfassen
                    booking_link = create_google_flights_link(orig, dest, dep_date_clean, ret_date_clean)
                    
                    deal_item = {
                        "deal_key": deal_key,
                        "origin": orig,
                        "origin_name": orig_name,
                        "destination": dest,
                        "destination_name": dest_name,
                        "dep_date": dep_date_clean,
                        "ret_date": ret_date_clean,
                        "stay_days": stay_days,
                        "price": price,
                        "airline_code": airline_code,
                        "airline_name": get_airline_name(airline_code),
                        "reason": reason,
                        "booking_link": booking_link,
                    }
                    collected_deals.append(deal_item)

                    # Als gemeldet vormerken (wird nach erfolgreichem Senden gespeichert)
                    notified_deals[deal_key] = {
                        "last_price": price,
                        "last_notified": datetime.utcnow().isoformat(),
                    }

    # Tages-Bestpreis je Strecke in die Historie schreiben (niedrigster Preis des Tages zählt)
    for rk, offer in best_offer_per_route.items():
        day_prices = price_history.setdefault(rk, {})
        if today not in day_prices or offer["price"] < day_prices[today]:
            day_prices[today] = offer["price"]

    # Nur die letzten 60 Tage behalten, damit die Datei klein bleibt
    for rk in price_history:
        if len(price_history[rk]) > 60:
            newest = sorted(price_history[rk].keys())[-60:]
            price_history[rk] = {d: price_history[rk][d] for d in newest}

    # 7. Fehlerbehandlung für wiederholte API-Ausfälle
    if total_queries > 0 and failed_queries == total_queries:
        # Alle Abfragen sind fehlgeschlagen!
        status_data["consecutive_errors"] = status_data.get("consecutive_errors", 0) + 1
        print(f"❌ Kompletter Ausfall: {status_data['consecutive_errors']} aufeinanderfolgende Fehlerläufe.")
        
        if status_data["consecutive_errors"] == max_errors_alert:
            alert_msg = (
                "⚠️ <b>Warnung von deinem Flugpreis-Bot:</b>\n\n"
                f"Die Flug-API konnte in den letzten {max_errors_alert} Läufen nicht erreicht werden.\n"
                "Mögliche Ursachen:\n"
                "• Das TRAVELPAYOUTS_TOKEN ist abgelaufen oder ungültig\n"
                "• Die Flug-API hat temporäre Wartungsarbeiten\n"
                "Schau bitte im GitHub Actions Log nach!"
            )
            send_telegram_message(telegram_token, telegram_chat_id, alert_msg)
    else:
        # Mindestens eine Abfrage war erfolgreich
        status_data["consecutive_errors"] = 0
        status_data["last_successful_run"] = datetime.utcnow().isoformat()

    telegram_failed = False

    # 8. Tagesbericht: einmal am Tag ab der eingestellten Uhrzeit ein Lebenszeichen schicken
    if (
        summary_enabled
        and now_berlin.hour >= summary_hour
        and status_data.get("last_daily_summary") != today
        and failed_queries < total_queries
    ):
        summary_msg = build_daily_summary(best_offer_per_route, max_price, now_berlin)
        if args.dry_run:
            print("\n--- DRY RUN (Tagesbericht) ---")
            print(summary_msg)
            print("------------------------------")
        elif send_telegram_message(telegram_token, telegram_chat_id, summary_msg):
            print("✅ Tagesbericht gesendet.")
            status_data["last_daily_summary"] = today
        else:
            print("❌ Tagesbericht konnte nicht gesendet werden.")
            telegram_failed = True

    # Status und Historie persistent speichern
    if not args.dry_run:
        save_json_file(STATUS_PATH, status_data)
        save_json_file(PRICE_HISTORY_PATH, price_history)

    # 9. Telegram-Nachricht mit allen Deals des Laufs bündeln
    if not collected_deals:
        print("ℹ️ Keine neuen Schnäppchen in diesem Durchlauf gefunden. Sende keine Deal-Nachricht.")
        if telegram_failed:
            sys.exit(1)  # Lauf in GitHub rot markieren, damit Telegram-Probleme auffallen
        return

    print(f"🎉 {len(collected_deals)} Schnäppchen gefunden! Bereite Telegram-Nachricht vor...")

    # Sortiere Deals nach Preis aufsteigend
    collected_deals.sort(key=lambda d: d["price"])

    message_blocks = [
        f"🚨 <b>{len(collected_deals)} NEUE(R) FLUG-DEAL(S) GEFUNDEN!</b> 🇬🇪\n"
        f"Reisezeitraum: Feb / Mär 2027 (7–14 Tage)"
    ]

    for d in collected_deals:
        block = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✈️ <b>{d['origin_name']} ({d['origin']}) ➔ {d['destination_name']} ({d['destination']})</b>\n"
            f"📅 <b>Hin:</b> {format_date_german(d['dep_date'])} | <b>Rück:</b> {format_date_german(d['ret_date'])} ({d['stay_days']} Tage)\n"
            f"💰 <b>Preis: {d['price']} €</b> (Hin & Rückflug gesamt)\n"
            f"🏢 <b>Airline:</b> {d['airline_name']}\n"
            f"{d['reason']}\n"
            f"🔗 <a href=\"{d['booking_link']}\">Direkt bei Google Flights prüfen</a>"
        )
        message_blocks.append(block)

    full_message = "\n\n".join(message_blocks)

    if args.dry_run:
        print("\n--- DRY RUN (Nachrichtenvorschau) ---")
        print(full_message)
        print("-------------------------------------")
    else:
        sent_ok = send_telegram_message(telegram_token, telegram_chat_id, full_message)
        if sent_ok:
            print("✅ Telegram-Nachricht erfolgreich gesendet!")
            save_json_file(NOTIFIED_DEALS_PATH, notified_deals)
        else:
            print("❌ Fehler beim Senden der Telegram-Nachricht.")
            telegram_failed = True

    if telegram_failed:
        sys.exit(1)  # Lauf in GitHub rot markieren, damit Telegram-Probleme auffallen


if __name__ == "__main__":
    main()
