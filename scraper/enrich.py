#!/usr/bin/env python3
"""
Cape Storm Monitor enrichment agent.
Reads data.json, calls Claude Haiku to clean and enrich incident data,
then writes the result back. Falls back to original data on any failure.

Trigger: run standalone or via the enrich.yml workflow.
Switch:  set ENABLE_ENRICHMENT=true in repo variables to auto-run after scraping.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

SAST      = ZoneInfo('Africa/Johannesburg')
ROOT_DIR  = os.path.join(os.path.dirname(__file__), '..')
DATA_FILE = os.path.join(ROOT_DIR, 'data', 'data.json')

ENRICH_FIELDS = ('title', 'description', 'severity', 'area', 'actions', 'alternate_route')
VALID_SEVERITIES = {'EMERGENCY', 'WARNING', 'WATCH', 'ALL_CLEAR'}


def now_sast() -> str:
    return datetime.now(SAST).isoformat(timespec='seconds')


def load_data() -> dict:
    with open(DATA_FILE, encoding='utf-8') as f:
        return json.load(f)


def call_claude(incidents: list, current_summary: str, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are an emergency management assistant for Cape Town, South Africa.

Active incidents scraped from official sources:
{json.dumps(incidents, indent=2)}

Current summary: {current_summary}

Enrich each incident with:
- title: concise factual label, max 60 chars
- description: specific, max 220 chars, include numbers/times where present
- severity: EMERGENCY | WARNING | WATCH | ALL_CLEAR  (re-assess from content)
- area: specific Cape Town suburb or named road — not "Cape Town Metro"
- actions: 2–4 specific steps a resident should take right now
- alternate_route: for road/coastal closures only, null otherwise

Also produce:
- summary: single sentence, max 120 chars, worst active conditions overall
- status: highest severity level among active incidents

Return ONLY valid JSON — no prose, no markdown fences:
{{
  "summary": "...",
  "status": "...",
  "incidents": [
    {{
      "id": "...",
      "title": "...",
      "description": "...",
      "severity": "...",
      "area": "...",
      "actions": ["..."],
      "alternate_route": "..." or null
    }}
  ]
}}"""

    response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2048,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return json.loads(response.content[0].text.strip())


def validate(enriched: dict) -> bool:
    if not isinstance(enriched.get('incidents'), list):
        return False
    if enriched.get('status') not in VALID_SEVERITIES:
        return False
    for inc in enriched['incidents']:
        if inc.get('severity') not in VALID_SEVERITIES:
            return False
    return True


def merge(original: dict, enriched: dict) -> dict:
    enriched_map = {i['id']: i for i in enriched.get('incidents', [])}

    merged_incidents = []
    for inc in original.get('incidents', []):
        e = enriched_map.get(inc['id'])
        if e:
            updated = dict(inc)
            for field in ENRICH_FIELDS:
                val = e.get(field)
                if val is not None:
                    updated[field] = val
            merged_incidents.append(updated)
        else:
            merged_incidents.append(inc)

    result = dict(original)
    result['incidents']    = merged_incidents
    result['summary']      = enriched.get('summary') or original.get('summary', '')
    result['status']       = enriched.get('status')  or original.get('status', 'WATCH')
    result['last_updated'] = now_sast()
    return result


def git_commit_and_push():
    subprocess.run(['git', 'config', 'user.name',  'klein-dade-bot'],           check=False)
    subprocess.run(['git', 'config', 'user.email', 'bot@klein-dade.github.io'], check=False)
    subprocess.run(['git', 'add', DATA_FILE], check=False)
    result = subprocess.run(
        ['git', 'commit', '-m', 'chore: agent enrichment [skip ci]'],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        subprocess.run(['git', 'push'], check=False)
        print('Enriched data committed and pushed.')
    else:
        print('No changes after enrichment — skipping commit.')


def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('[ERROR] ANTHROPIC_API_KEY not set.', file=sys.stderr)
        sys.exit(1)

    print('Loading data.json…')
    original = load_data()

    active = [i for i in original.get('incidents', []) if i.get('active')]
    if not active:
        print('No active incidents — nothing to enrich.')
        return

    print(f'Enriching {len(active)} active incidents with Claude Haiku…')
    try:
        enriched = call_claude(active, original.get('summary', ''), api_key)
    except Exception as exc:
        print(f'[WARN] Claude call failed — retaining original data: {exc}', file=sys.stderr)
        return

    if not validate(enriched):
        print('[WARN] Response failed validation — retaining original data.', file=sys.stderr)
        return

    merged = merge(original, enriched)

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f'Done. Status: {merged["status"]} | Summary: {merged["summary"]}')
    git_commit_and_push()


if __name__ == '__main__':
    main()
