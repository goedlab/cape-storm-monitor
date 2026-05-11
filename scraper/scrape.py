#!/usr/bin/env python3
"""
Cape Storm Monitor scraper.
Fetches data from SA Weather Service, City of Cape Town, and Traffic SA,
builds data.json + geojson.json, and commits only when content has changed.
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

ROOT_DIR    = os.path.join(os.path.dirname(__file__), '..')
DATA_FILE   = os.path.join(ROOT_DIR, 'data', 'data.json')
GEOJSON_FILE = os.path.join(ROOT_DIR, 'data', 'geojson.json')

HEADERS = {
    'User-Agent': 'CapeStormTracker/1.0 (klein-dade.github.io; storm-monitoring-bot)'
}
TIMEOUT = 15


def now_sast() -> str:
    return datetime.now(SAST).isoformat(timespec='seconds')


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

        # Try to find warning/alert elements — SAWS HTML structure varies by deploy
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
        ('https://www.capetown.gov.za/general/alerts-and-notifications', 'power'),
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


def scrape_open_meteo() -> list:
    """Fetch inclement conditions from Open-Meteo (free, no key)."""
    incidents = []
    try:
        url = (
            'https://api.open-meteo.com/v1/forecast'
            '?latitude=-33.9249&longitude=18.4241'
            '&current=wind_speed_10m,wind_gusts_10m,precipitation,weather_code'
            '&hourly=wave_height'
            '&forecast_days=1'
            '&timezone=Africa%2FJohannesburg'
        )
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
        d = res.json()

        cur = d.get('current', {})
        gusts    = cur.get('wind_gusts_10m', 0) or 0
        precip   = cur.get('precipitation', 0) or 0
        wmo_code = cur.get('weather_code', 0) or 0

        hourly = d.get('hourly', {})
        wave_heights = [h for h in (hourly.get('wave_height') or []) if h is not None]
        max_wave = max(wave_heights[:6]) if wave_heights else 0

        if gusts > 100:
            sev = 'EMERGENCY'
        elif gusts > 80:
            sev = 'WARNING'
        elif gusts > 60:
            sev = 'WATCH'
        else:
            sev = None

        if sev:
            incidents.append({
                'id':          'om-wind-001',
                'type':        'wind',
                'title':       f'Strong Wind Advisory – Cape Town ({round(gusts)} km/h gusts)',
                'area':        'Cape Town Metro',
                'lat':         -33.9249,
                'lng':         18.4241,
                'severity':    sev,
                'description': f'Wind gusts of {round(gusts)} km/h detected. Secure loose outdoor items and avoid exposed coastal or mountain areas.',
                'source':      'Open-Meteo',
                'source_url':  'https://open-meteo.com',
                'updated':     now_sast(),
                'active':      True,
            })

        if precip > 15:
            rain_sev = 'EMERGENCY'
        elif precip > 5:
            rain_sev = 'WARNING'
        else:
            rain_sev = None

        if rain_sev:
            incidents.append({
                'id':          'om-rain-001',
                'type':        'flood',
                'title':       f'Heavy Rainfall – Cape Town ({precip} mm/hr)',
                'area':        'Cape Town Metro',
                'lat':         -33.9249,
                'lng':         18.4241,
                'severity':    rain_sev,
                'description': f'Rainfall rate of {precip} mm/hr. Avoid low-lying areas and flood-prone roads.',
                'source':      'Open-Meteo',
                'source_url':  'https://open-meteo.com',
                'updated':     now_sast(),
                'active':      True,
            })

        if max_wave > 6:
            wave_sev = 'EMERGENCY'
        elif max_wave > 4:
            wave_sev = 'WARNING'
        elif max_wave > 2.5:
            wave_sev = 'WATCH'
        else:
            wave_sev = None

        if wave_sev:
            incidents.append({
                'id':          'om-wave-001',
                'type':        'coastal',
                'title':       f'High Wave Warning – Cape Coast ({max_wave}m)',
                'area':        'Cape Town Coastal',
                'lat':         -33.9249,
                'lng':         18.4241,
                'severity':    wave_sev,
                'description': f'Wave heights up to {max_wave}m forecast. Keep clear of coastal rocks, beaches, and piers.',
                'source':      'Open-Meteo',
                'source_url':  'https://open-meteo.com',
                'updated':     now_sast(),
                'active':      True,
            })

    except Exception as exc:
        print(f'[WARN] Open-Meteo scrape failed: {exc}', file=sys.stderr)

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
        channel = root.find('channel')
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

        if wind_kmh > 80:
            sev = 'EMERGENCY'
        elif wind_kmh > 60:
            sev = 'WARNING'
        elif wind_kmh > 40:
            sev = 'WATCH'
        else:
            sev = 'ALL_CLEAR'

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


def build_data(scraped: list, existing: dict) -> dict:
    active       = [i for i in scraped if i.get('active')]
    roads_closed = sum(1 for i in active if i.get('type') in ('road', 'coastal'))
    areas        = len({i.get('area', '') for i in active})
    severity     = dominant_severity(scraped)

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
    # Preserve shelter markers from previous data
    for m in existing.get('map_markers', []):
        if m.get('type') == 'shelter':
            map_markers.append(m)

    return {
        'status':       severity,
        'last_updated': now_sast(),
        'summary':      existing.get('summary', 'Monitoring active. Check incidents for current conditions.'),
        'stats': {
            'active_incidents': len(active),
            'roads_closed':     roads_closed,
            'shelters_open':    existing.get('stats', {}).get('shelters_open', 0),
            'areas_affected':   areas,
        },
        'incidents':    scraped,
        'map_markers':  map_markers,
        'timeline':     existing.get('timeline', []),
        'contacts':     existing.get('contacts', []),
        'actions':      existing.get('actions', {}),
        'outlook':      existing.get('outlook', {}),
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
    open_meteo = scrape_open_meteo()

    print('Fetching GDACS alerts…')
    gdacs = scrape_gdacs()

    all_scraped = saws + cct + traffic + open_meteo + gdacs
    if not all_scraped:
        print('[WARN] All scrapers returned empty — retaining existing incidents.')
        all_scraped = existing.get('incidents', [])

    weather = fetch_openweathermap(api_key)
    if weather:
        print(f'OpenWeatherMap: {weather["description"]}, {weather["wind_kmh"]} km/h wind ({weather["severity"]})')

    new_data = build_data(all_scraped, existing)

    geojson = build_geojson(new_data)
    with open(GEOJSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)

    # Compare without last_updated to avoid spurious commits on time-only changes
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
