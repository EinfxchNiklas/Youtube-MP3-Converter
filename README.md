# YouTube MP3 Converter

Passwortgeschützte Web-App: YouTube-URL eingeben → Ausschnitt per Millisekunde wählen → MP3 (320 kbps) herunterladen.

**Stack:** FastAPI · yt-dlp · ffmpeg · Render

---

## Lokale Entwicklung

### Voraussetzungen
- Python 3.11+

> ffmpeg wird automatisch über das Paket `imageio-ffmpeg` mitgeliefert –
> keine separate Installation nötig.

### Setup

```bash
# 1. Virtuelle Umgebung
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 2. Abhängigkeiten
pip install -r requirements.txt

# 3. Umgebungsvariablen
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/macOS
# .env anpassen: APP_USERNAME, APP_PASSWORD, SECRET_KEY

# 4. Server starten
uvicorn app.main:app --reload
```

Öffne http://localhost:8000 im Browser.

**Standard-Zugangsdaten (nur lokal):** `admin` / `changeme`  
→ Unbedingt in `.env` ändern!

---

## Deployment auf Render

1. Repository auf GitHub pushen
2. Auf [render.com](https://render.com) → **New → Blueprint** → Repository wählen  
   (Render liest `render.yaml` automatisch)
3. In den **Environment Variables** des Services setzen:
   - `APP_USERNAME` – gewünschter Benutzername
   - `APP_PASSWORD` – sicheres Passwort
   - `SECRET_KEY` wird von Render automatisch generiert
4. Deploy starten → fertig

> **Hinweis:** Auf dem kostenlosen Render-Tier können lange Videos (>5 min)  
> durch den Request-Timeout abbrechen. Kürzere Ausschnitte funktionieren zuverlässig.

---

## Projektstruktur

```
app/
  main.py          # FastAPI-App, Routen
  auth.py          # Login / Session
  converter.py     # yt-dlp + ffmpeg
  templates/       # Jinja2-HTML (login.html, index.html)
  static/          # style.css (Dark Theme), app.js
requirements.txt
render.yaml
.env.example
```