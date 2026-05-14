#!/usr/bin/env python3
"""
Cape Storm Monitor scraper.
Fetches data from SA Weather Service, City of Cape Town, Traffic SA,
Open-Meteo (weather + flood), and GDACS.
Builds data.json + geojson.json and commits only when content has changed.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

SAST = ZoneInfo("Africa/Johannesburg")

ROOT_DIR     = os.path.join(os.path.dirname(__file__), '..')
DATA_FILE    = os.path.join(ROOT_DIR, 'data', 'data.json')
GEOJSON_FILE = os.path.join(ROOT_DIR, 'data', 'geojson.json')

HEADERS = {
    'User-Agent': 'CapeStormTracker/1.0 (klein-dade.github.io; storm-monitoring-bot)'
}
TIMEOUT = 15


def now_sast() -> str:
    return datetime.now(SAST).isoformat(timespec='seconds')


# ── Western Cape locations for weather ───────────────────────────────────────

WC_LOCATIONS = [
    {'name': 'Cape Town',    'lat': -33.9249, 'lng': 18.4241},
    {'name': 'Citrusdal',    'lat': -32.5833, 'lng': 19.0167},
    {'name': 'Stellenbosch', 'lat': -33.9321, 'lng': 18.8602},
    {'name': 'George',       'lat': -33.9646, 'lng': 22.4608},
    {'name': 'Ceres',        'lat': -33.3667, 'lng': 19.3167},
]

FLOOD_RIVERS = [
    {'name': 'Olifants River', 'area': 'Citrusdal',          'lat': -32.35, 'lng': 19.00},
    {'name': 'Breede River',   'area': 'Worcester',           'lat': -33.65, 'lng': 19.45},
    {'name': 'Berg River',     'area': 'Paarl / Franschhoek', 'lat': -33.70, 'lng': 18.96},
    {'name': 'Eerste River',   'area': 'Stellenbosch',        'lat': -33.93, 'lng': 18.86},
    {'name': 'Liesbeek River', 'area': 'Cape Town',           'lat': -33.94, 'lng': 18.49},
]

WMO_LABELS = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Freezing fog',
    51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle',
    61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
    71: 'Slight snow', 73: 'Moderate snow', 75: 'Heavy snow',
    80: 'Rain showers', 81: 'Moderate showers', 82: 'Violent showers',
    95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Severe thunderstorm',
}


# ── Scrapers ──────────────────────────────────────────────────────────────────

def scrape_saws() -> list:
    """Scrape SA Weather Service for warnings and advisories."""
    incidents = []
    try:
        res = requests.get(
            'https://www.weathersa.co.za/home/mediareleases',
            headers=HEADERS, timeout=TIMEOUT
        )
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'lxml')

        candidates = (
            soup.find_all(class_=lambda c: c and any(
                kw in c.lower() for kw in ('warning', 'alert', 'bulletin', 'advisory')
            )) or
            soup.find_all(['article', 'section', 'li'])
        )

        for i, el in enumerate(candidates[:6]):
            text = el.get_text(separator=' ', strip=True)
            if len(text) < 30 or len(text) > 3000:
                continue
            sev = 'WARNING' if any(w in text.lower() for w in ('gale', 'severe', 'emergency')) else 'WATCH'
            incidents.append({
                'id':          f'saws-{i + 1:03d}',
                'type':        'storm',
                'title':       text[:80].rstrip('.'),
                'area':        'Cape Town Metro',
                'lat':         -33.9249,
                'lng':         18.4241,
                'severity':    sev,
                'description': text[:500],
                'source':      'SA Weather Service',
                'source_url':  'https://www.weathersa.co.za/home/mediareleases',
                'updated':     now_sast(),
                'active':      True,
            })
    except Exception as exc:
        print(f'[WARN] SAWS scrape failed: {exc}', file=sys.stderr)

    return incidents


def scrape_city_of_ct() -> list:
    """Scrape City of Cape Town disaster / service alert pages."""
    incidents = []
    urls = [
        ('https://www.capetown.gov.za/Media-and-news/Newsroom', 'infrastructure'),
    ]
    for url, inc_type in urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'lxml')

            alerts = soup.find_all(class_=lambda c: c and any(
                kw in c.lower() for kw in ('alert', 'notice', 'warning', 'update', 'outage')
            ))
            for i, el in enumerate(alerts[:4]):
                text = el.get_text(separator=' ', strip=True)
                if len(text) < 30:
                    continue
                incidents.append({
                    'id':          f'cct-{inc_type}-{i + 1:03d}',
                    'type':        inc_type,
                    'title':       text[:80].rstrip('.'),
                    'area':        'Cape Town',
                    'lat':         -33.9249,
                    'lng':         18.4241,
                    'severity':    'WATCH',
                    'description': text[:500],
                    'source':      'City of Cape Town',
                    'source_url':  url,
                    'updated':     now_sast(),
                    'active':      True,
                })
        except Exception as exc:
            print(f'[WARN] City of CT scrape failed ({url}): {exc}', file=sys.stderr)

    return incidents


def scrape_traffic_sa() -> list:
    """Scrape Traffic SA for road closures."""
    incidents = []
    try:
        res = requests.get('https://www.traffic.gov.za', headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'lxml')

        closures = soup.find_all(class_=lambda c: c and any(
            kw in c.lower() for kw in ('closure', 'closed', 'incident', 'roadwork')
        ))
        for i, el in enumerate(closures[:4]):
            text = el.get_text(separator=' ', strip=True)
            if len(text) < 20:
                continue
            incidents.append({
                'id':          f'traffic-{i + 1:03d}',
                'type':        'road',
                'title':       text[:80].rstrip('.'),
                'area':        'Cape Town Metro',
                'lat':         -33.9249 + (i * 0.04),
                'lng':         18.4241  + (i * 0.04),
                'severity':    'WARNING',
                'description': text[:500],
                'source':      'Traffic SA',
                'source_url':  'https://www.traffic.gov.za',
                'updated':     now_sast(),
                'active':      True,
            })
    except Exception as exc:
        print(f'[WARN] Traffic SA scrape failed: {exc}', file=sys.stderr)

    return incidents


def fetch_open_meteo() -> dict | None:
    """Fetch current conditions across key Western Cape locations from Open-Meteo."""
    try:
        lats = ','.join(str(l['lat']) for l in WC_LOCATIONS)
        lngs = ','.join(str(l['lng']) for l in WC_LOCATIONS)
        url = (
            'https://api.open-meteo.com/v1/forecast'
            f'?latitude={lats}&longitude={lngs}'
            '&current=wind_speed_10m,wind_gusts_10m,precipitation,weather_code'
            '&hourly=wave_height'
            '&forecast_days=1'
            '&timezone=Africa%2FJohannesburg'
        )
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
        results = res.json()
        if not isinstance(results, list):
            results = [results]

        locations = []
        for i, d in enumerate(results):
            cur = d.get('current', {})
            hourly = d.get('hourly', {})
            wave_heights = [h for h in (hourly.get('wave_height') or []) if h is not None]
            locations.append({
                'name':     WC_LOCATIONS[i]['name'] if i < len(WC_LOCATIONS) else f'loc-{i}',
                'lat':      WC_LOCATIONS[i]['lat'],
                'lng':      WC_LOCATIONS[i]['lng'],
                'gusts':    cur.get('wind_gusts_10m', 0) or 0,
                'wind':     cur.get('wind_speed_10m', 0) or 0,
                'precip':   cur.get('precipitation', 0) or 0,
                'wmo':      cur.get('weather_code', 0) or 0,
                'max_wave': max(wave_heights[:6]) if wave_heights else 0,
            })

        return {
            'locations': locations,
            'gusts':    max(l['gusts']    for l in locations),
            'wind':     max(l['wind']     for l in locations),
            'precip':   max(l['precip']   for l in locations),
            'wmo':      locations[0]['wmo'],
            'max_wave': max(l['max_wave'] for l in locations),
        }
    except Exception as exc:
        print(f'[WARN] Open-Meteo fetch failed: {exc}', file=sys.stderr)
        return None


def open_meteo_summary(c: dict) -> str:
    """Build a one-line status summary from Open-Meteo conditions."""
    parts = []
    label = WMO_LABELS.get(c['wmo'], '')
    parts.append(f'Cape Town: {label}' if label else 'Western Cape')
    if c['gusts'] >= 40:
        parts.append(f'gusts {round(c["gusts"])} km/h')
    if c['precip'] > 0.2:
        parts.append(f'{round(c["precip"], 1)} mm rain')
    if c['max_wave'] > 1.0:
        parts.append(f'seas {round(c["max_wave"], 1)} m')
    alerts = [l['name'] for l in c.get('locations', [])[1:]
              if l['gusts'] > 60 or l['precip'] > 5]
    if alerts:
        parts.append(f'alerts: {", ".join(alerts)}')
    return ' · '.join(parts)


def open_meteo_incidents(c: dict) -> list:
    """Generate incidents for any Western Cape location exceeding thresholds."""
    incidents = []
    for loc in c.get('locations', []):
        name, lat, lng = loc['name'], loc['lat'], loc['lng']
        slug = name.lower().replace(' ', '-')
        gusts, precip, max_wave = loc['gusts'], loc['precip'], loc['max_wave']

        if gusts > 100:      sev = 'EMERGENCY'
        elif gusts > 80:     sev = 'WARNING'
        elif gusts > 60:     sev = 'WATCH'
        else:                sev = None
        if sev:
            incidents.append({
                'id': f'om-wind-{slug}', 'type': 'wind',
                'title': f'Strong Wind Advisory – {name} ({round(gusts)} km/h gusts)',
                'area': name, 'lat': lat, 'lng': lng, 'severity': sev,
                'description': f'Wind gusts of {round(gusts)} km/h at {name}. Secure loose items and avoid exposed areas.',
                'source': 'Open-Meteo', 'source_url': 'https://open-meteo.com',
                'updated': now_sast(), 'active': True,
            })

        if precip > 15:      rain_sev = 'EMERGENCY'
        elif precip > 5:     rain_sev = 'WARNING'
        else:                rain_sev = None
        if rain_sev:
            incidents.append({
                'id': f'om-rain-{slug}', 'type': 'flood',
                'title': f'Heavy Rainfall – {name} ({precip} mm/hr)',
                'area': name, 'lat': lat, 'lng': lng, 'severity': rain_sev,
                'description': f'Rainfall rate of {precip} mm/hr at {name}. Avoid low-lying areas and flood-prone roads.',
                'source': 'Open-Meteo', 'source_url': 'https://open-meteo.com',
                'updated': now_sast(), 'active': True,
            })

        if max_wave > 6:     wave_sev = 'EMERGENCY'
        elif max_wave > 4:   wave_sev = 'WARNING'
        elif max_wave > 2.5: wave_sev = 'WATCH'
        else:                wave_sev = None
        if wave_sev:
            incidents.append({
                'id': f'om-wave-{slug}', 'type': 'coastal',
                'title': f'High Wave Warning – {name} ({max_wave}m)',
                'area': name, 'lat': lat, 'lng': lng, 'severity': wave_sev,
                'description': f'Wave heights up to {max_wave}m at {name}. Keep clear of coastal rocks and piers.',
                'source': 'Open-Meteo', 'source_url': 'https://open-meteo.com',
                'updated': now_sast(), 'active': True,
            })
    return incidents


def scrape_flood_api() -> list:
    """Fetch river discharge for key Western Cape rivers via Open-Meteo Flood API."""
    incidents = []
    try:
        lats = ','.join(str(r['lat']) for r in FLOOD_RIVERS)
        lngs = ','.join(str(r['lng']) for r in FLOOD_RIVERS)
        url = (
            'https://flood.open-meteo.com/v1/flood'
            f'?latitude={lats}&longitude={lngs}'
            '&daily=river_discharge'
            '&past_days=14&forecast_days=1'
        )
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
        results = res.json()
        if not isinstance(results, list):
            results = [results]

        for i, d in enumerate(results):
            if i >= len(FLOOD_RIVERS):
                break
            river = FLOOD_RIVERS[i]
            discharges = [v for v in (d.get('daily', {}).get('river_discharge') or []) if v is not None]
            if len(discharges) < 2:
                continue
            current  = discharges[-1]
            baseline = discharges[:-1]
            mean     = sum(baseline) / len(baseline)
            if mean <= 0:
                continue

            ratio = current / mean
            if ratio > 5:     sev = 'EMERGENCY'
            elif ratio > 3:   sev = 'WARNING'
            elif ratio > 1.8: sev = 'WATCH'
            else:              sev = None

            if sev:
                slug = river['name'].lower().replace(' ', '-')
                print(f'  [FLOOD] {river["name"]}: {round(current)} m³/s ({round(ratio,1)}× mean) → {sev}')
                incidents.append({
                    'id':          f'flood-{slug}',
                    'type':        'flood',
                    'title':       f'{river["name"]} Flooding – {river["area"]}',
                    'area':        river['area'],
                    'lat':         river['lat'],
                    'lng':         river['lng'],
                    'severity':    sev,
                    'description': (
                        f'{river["name"]} discharge {round(current)} m³/s — '
                        f'{round(ratio, 1)}× above 14-day mean ({round(mean)} m³/s). '
                        'River levels significantly elevated.'
                    ),
                    'source':      'Open-Meteo Flood API',
                    'source_url':  'https://open-meteo.com/en/docs/flood-api',
                    'updated':     now_sast(),
                    'active':      True,
                })

    except Exception as exc:
        print(f'[WARN] Flood API failed: {exc}', file=sys.stderr)

    return incidents


def scrape_gdacs() -> list:
    """Parse GDACS RSS feed for South Africa disaster alerts."""
    import xml.etree.ElementTree as ET
    incidents = []
    try:
        res = requests.get('https://www.gdacs.org/xml/rss.xml', headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
        root = ET.fromstring(res.text)

        sa_terms = ('south africa', 'cape town', 'western cape', 'eastern cape')
        channel  = root.find('channel')
        if channel is None:
            return incidents

        for item in channel.findall('item'):
            title       = (item.findtext('title') or '').strip()
            description = (item.findtext('description') or '').strip()
            link        = (item.findtext('link') or '').strip()
            combined    = (title + ' ' + description).lower()

            if not any(t in combined for t in sa_terms):
                continue

            if any(w in combined for w in ('cyclone', 'hurricane', 'tropical storm')):
                inc_type = 'storm'
            elif any(w in combined for w in ('flood', 'flash flood')):
                inc_type = 'flood'
            elif any(w in combined for w in ('earthquake', 'seismic')):
                inc_type = 'infrastructure'
            else:
                inc_type = 'storm'

            if any(w in combined for w in ('red alert', 'orange alert', 'extreme')):
                sev = 'EMERGENCY'
            elif any(w in combined for w in ('orange', 'severe', 'warning')):
                sev = 'WARNING'
            else:
                sev = 'WATCH'

            incidents.append({
                'id':          f'gdacs-{abs(hash(title)) % 10000:04d}',
                'type':        inc_type,
                'title':       title[:80].rstrip('.'),
                'area':        'South Africa',
                'lat':         -33.9249,
                'lng':         18.4241,
                'severity':    sev,
                'description': description[:500],
                'source':      'GDACS',
                'source_url':  link or 'https://www.gdacs.org',
                'updated':     now_sast(),
                'active':      True,
            })

    except Exception as exc:
        print(f'[WARN] GDACS scrape failed: {exc}', file=sys.stderr)

    return incidents


def fetch_openweathermap(api_key: str) -> dict | None:
    """Fetch current Cape Town conditions from OpenWeatherMap free tier."""
    if not api_key:
        return None
    try:
        url = (
            'https://api.openweathermap.org/data/2.5/weather'
            f'?lat=-33.9249&lon=18.4241&appid={api_key}&units=metric'
        )
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        d = res.json()

        wind_kmh = d.get('wind', {}).get('speed', 0) * 3.6
        desc     = d.get('weather', [{}])[0].get('description', 'unknown')

        if wind_kmh > 80:    sev = 'EMERGENCY'
        elif wind_kmh > 60:  sev = 'WARNING'
        elif wind_kmh > 40:  sev = 'WATCH'
        else:                sev = 'ALL_CLEAR'

        return {'wind_kmh': round(wind_kmh), 'description': desc, 'severity': sev}
    except Exception as exc:
        print(f'[WARN] OpenWeatherMap failed: {exc}', file=sys.stderr)
        return None


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_existing() -> dict:
    try:
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_hash(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def dominant_severity(incidents: list) -> str:
    order = ['EMERGENCY', 'WARNING', 'WATCH', 'ALL_CLEAR']
    active_sevs = {i['severity'] for i in incidents if i.get('active')}
    for lvl in order:
        if lvl in active_sevs:
            return lvl
    return 'ALL_CLEAR'


def build_data(scraped: list, existing: dict, summary: str = '', live_scraped: list | None = None) -> dict:
    active       = [i for i in scraped if i.get('active')]
    roads_closed = sum(1 for i in active if i.get('type') in ('road', 'coastal'))
    areas        = len({i.get('area', '') for i in active})
    open_shelters = sum(1 for s in existing.get('shelters', []) if s.get('open'))
    # Status reflects only freshly-scraped data so stale incidents don't inflate severity
    severity     = dominant_severity(live_scraped if live_scraped is not None else scraped)

    map_markers = [
        {
            'id':       f'm-{inc["id"]}',
            'type':     inc['type'],
            'lat':      inc['lat'],
            'lng':      inc['lng'],
            'label':    inc['title'],
            'severity': inc['severity'],
        }
        for inc in active if inc.get('lat') and inc.get('lng')
    ]
    for m in existing.get('map_markers', []):
        if m.get('type') == 'shelter':
            map_markers.append(m)

    return {
        'status':       severity,
        'last_updated': now_sast(),
        'summary':      summary or existing.get('summary', 'Conditions monitoring active'),
        'stats': {
            'active_incidents': len(active),
            'roads_closed':     roads_closed,
            'shelters_open':    open_shelters,
            'areas_affected':   areas,
        },
        'incidents':    scraped,
        'map_markers':  map_markers,
        'timeline':     existing.get('timeline', []),
        'contacts':     existing.get('contacts', []),
        'shelters':     existing.get('shelters', []),
        'actions':      existing.get('actions', {}),
        'outlook':      existing.get('outlook', {}),
        'event':        existing.get('event'),
        'outcomes':     existing.get('outcomes'),
    }


def build_geojson(data: dict) -> dict:
    features = []

    for inc in data.get('incidents', []):
        if not (inc.get('active') and inc.get('lat') and inc.get('lng')):
            continue
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [inc['lng'], inc['lat']]},
            'properties': {
                'id':          inc['id'],
                'type':        inc['type'],
                'title':       inc['title'],
                'area':        inc.get('area', ''),
                'severity':    inc['severity'],
                'description': inc.get('description', ''),
                'updated':     inc.get('updated', ''),
            },
        })

    for m in data.get('map_markers', []):
        if m.get('type') == 'shelter':
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [m['lng'], m['lat']]},
                'properties': {
                    'id':       m['id'],
                    'type':     'shelter',
                    'title':    m['label'],
                    'severity': m.get('severity', 'ALL_CLEAR'),
                },
            })

    return {
        'type':      'FeatureCollection',
        'generated': now_sast(),
        'features':  features,
    }


def git_commit_and_push():
    subprocess.run(['git', 'config', 'user.name',  'klein-dade-bot'],           check=False)
    subprocess.run(['git', 'config', 'user.email', 'bot@klein-dade.github.io'], check=False)
    subprocess.run(['git', 'add', DATA_FILE, GEOJSON_FILE], check=False)
    result = subprocess.run(
        ['git', 'commit', '-m', 'chore: update storm data [skip ci]'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        subprocess.run(['git', 'push'], check=False)
        print('Data changed — committed and pushed.')
    else:
        print(f'[WARN] git commit returned non-zero: {result.stderr.strip()}')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key  = os.environ.get('OPENWEATHER_API_KEY', '')
    existing = load_existing()

    print('Scraping SA Weather Service…')
    saws = scrape_saws()

    print('Scraping City of Cape Town…')
    cct = scrape_city_of_ct()

    print('Scraping Traffic SA…')
    traffic = scrape_traffic_sa()

    print('Fetching Open-Meteo conditions…')
    om_conditions = fetch_open_meteo()
    open_meteo    = open_meteo_incidents(om_conditions) if om_conditions else []
    om_summary    = open_meteo_summary(om_conditions)   if om_conditions else ''
    if om_conditions:
        print(f'  Open-Meteo: {om_summary}')

    print('Fetching flood data…')
    flood = scrape_flood_api()

    print('Fetching GDACS alerts…')
    gdacs = scrape_gdacs()

    live_scraped = saws + cct + traffic + open_meteo + flood + gdacs

    if not live_scraped:
        print('[WARN] All scrapers returned empty — retaining existing incidents for display only.')
        all_scraped = existing.get('incidents', [])
    else:
        all_scraped = live_scraped

    weather = fetch_openweathermap(api_key)
    if weather:
        print(f'  OpenWeatherMap: {weather["description"]}, {weather["wind_kmh"]} km/h ({weather["severity"]})')

    new_data = build_data(all_scraped, existing, summary=om_summary, live_scraped=live_scraped)

    geojson = build_geojson(new_data)
    with open(GEOJSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)

    def strip_ts(d):
        return {k: v for k, v in d.items() if k != 'last_updated'}

    if get_hash(strip_ts(new_data)) != get_hash(strip_ts(existing)):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
        git_commit_and_push()
    else:
        print('No content change — skipping commit.')


if __name__ == '__main__':
    main()
