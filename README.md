# ✈️ Flugpreis-Bot: Georgien-Schnäppchen (Kutaisi, Tiflis, Batumi)

Ein automatisierter Bot, der über **GitHub Actions** regelmäßig nach außergewöhnlich günstigen Hin- und Rückflügen von NRW/Hessen/Niedersachsen nach Georgien sucht und echte Deals direkt auf dein Smartphone per **Telegram** schickt.

---

## 📌 Übersicht & Features

- **Abflughäfen (optimiert für Meschede/Sauerland):**
  - **Prio 1:** Dortmund (DTM), Paderborn/Lippstadt (PAD)
  - **Prio 2:** Düsseldorf (DUS), Köln/Bonn (CGN), Münster/Osnabrück (FMO)
  - **Prio 3:** Frankfurt (FRA), Hannover (HAJ), Weeze (NRN)
- **Ziele in Georgien:** Kutaisi (KUT), Tiflis (TBS), Batumi (BUS)
- **Reisezeitraum:** Februar & März 2027 mit 7 bis 14 Tagen Aufenthaltsdauer.
- **Nur echte Schnäppchen:**
  - **Absolute Preisgrenze:** Maximal z. B. 120 € für Hin- & Rückflug zusammen.
  - **Relative Preisgrenze:** Mindestens 30 % unter dem Median bisheriger Flugpreise.
- **Keine doppelten Benachrichtigungen:** Angebote werden gespeichert. Eine erneute Benachrichtigung erfolgt nur, wenn der Preis um mindestens 10 € weiter gefallen ist.
- **100 % Serverless & Kostenlos:** Läuft komplett in der GitHub Cloud – kein eigener Server oder laufender PC nötig.

---

## 🛠️ Konfiguration (`config.yaml`)

Du kannst alle Kriterien in der Datei [`config.yaml`](file:///c:/Users/ladmin/Documents/antigravity/delightful-goodall/config.yaml) nach Belieben anpassen:

```yaml
deals:
  max_price_eur: 120            # Maximale absolute Schmerzgrenze in Euro
  relative_discount_percent: 30 # Mindestens 30 % günstiger als der Streckendurchschnitt
  min_history_samples: 3        # Ab wie vielen Beobachtungen der Rabatt berechnet wird
  price_drop_threshold_eur: 10  # Preissturz-Schwelle für erneute Meldung
```

---

## 🔒 Benötigte GitHub Secrets

Damit der Bot läuft, müssen folgende 3 geheime Schlüssel in deinem GitHub-Repository hinterlegt sein:

| Secret Name | Beschreibung |
| :--- | :--- |
| `TRAVELPAYOUTS_TOKEN` | Dein kostenloser API-Schlüssel von Travelpayouts / Aviasales |
| `TELEGRAM_BOT_TOKEN` | Der Bot-Token, den du von `@BotFather` auf Telegram erhalten hast |
| `TELEGRAM_CHAT_ID` | Deine persönliche Telegram-Chat-ID (z. B. über `@userinfobot`) |
