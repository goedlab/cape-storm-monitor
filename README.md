# Cape Storm Monitor

Real-time storm and incident tracker for Cape Town, built by [klein-dade](https://github.com/klein-dade).

**Live:** [klein-dade.github.io/cape-storm-tracker](https://klein-dade.github.io/cape-storm-tracker)

## Features

- Real-time tracking: storms, floods, road closures, power outages, internet outages
- Interactive Leaflet.js map with dark basemap and toggleable layers
- Automatic data updates every 30 minutes via GitHub Actions
- Client-side polling every 2 minutes — no page reload required
- Dark theme, mobile-first design
- Trilingual labels: English / Afrikaans / Xhosa
- Offline graceful degradation — shows last known state on fetch failure

## Severity levels

| Level | Colour | Meaning |
|-------|--------|---------|
| `ALL_CLEAR` | Green | Normal conditions |
| `WATCH` | Yellow | Conditions developing — stay alert |
| `WARNING` | Orange | Active threat — take precautions |
| `EMERGENCY` | Red | Immediate danger — act now |

## Repo structure

```
cape-storm-tracker/
├── index.html              # Single-page app
├── style.css               # Dark theme, mobile-first
├── app.js                  # Fetch + render + Leaflet map
├── data/
│   ├── data.json           # Source of truth — updated by scraper
│   └── geojson.json        # GeoJSON map markers
├── scraper/
│   ├── scrape.py           # Multi-source scraper
│   └── requirements.txt
├── .github/workflows/
│   └── scrape.yml          # Scheduled GitHub Action (every 30 min)
└── _headers                # GitHub Pages CDN cache headers
```

## Running the scraper locally

```bash
cd scraper
pip install -r requirements.txt
python scrape.py
```

Set `OPENWEATHER_API_KEY` in your environment for live weather conditions (optional — free tier).

## Data sources

| Source | Data |
|--------|------|
| SA Weather Service | Warnings, gale notices, advisories |
| City of Cape Town | Disaster alerts, power faults |
| Traffic SA | Road closures |
| OpenWeatherMap | Current wind / conditions (optional) |

## Data API

Static endpoints available for developers:

- `data/data.json` — full incident data (JSON)
- `data/geojson.json` — map markers (GeoJSON)

## GitHub Pages setup

1. Go to **Settings → Pages**
2. Source: **Deploy from a branch**, branch `main`, folder `/`
3. Add `OPENWEATHER_API_KEY` to **Settings → Secrets → Actions** (optional)

---

*Built by klein-dade. Small actions, real impact.*
