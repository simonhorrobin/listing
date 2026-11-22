"""The gig feed: Songkick events for tracked artists, as RSS.

A second feed family beside the BFI showings (loop 2026-11-gig-feed). The
events come from proctor, dynamicalsystem's internal API proxy, which joins
Songkick's calendar with the tracked-artist list. listing keeps no copy and
knows nothing about Songkick: it asks proctor, filters, and renders.

Filters live in the URL, as for showings:
    country=UK,US               events in these countries
    lineup=orbital              case-insensitive substring over the line-up,
                                support and tracked artists
    dow= dates= from= to=       as the showings feeds, on the first day
"""
from datetime import date
from html import escape
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from .filters import FilterError, date_matches, parse_filters

MAX_NAMES_IN_TITLE = 3


class GigSourceError(Exception):
    """proctor could not give us events; the feed answers 503."""


def fetch_events(base_url: str, timeout: float) -> List[Dict]:
    if not base_url:
        raise GigSourceError("the gig feed is not configured (PROCTOR_URL)")
    try:
        response = requests.get(f"{base_url}/songkick/events", timeout=timeout)
    except requests.RequestException as problem:
        raise GigSourceError(f"proctor unreachable: {type(problem).__name__}") from problem
    if response.status_code != 200:
        raise GigSourceError(f"proctor answered HTTP {response.status_code}")
    try:
        return list(response.json()["events"])
    except (ValueError, KeyError, TypeError) as problem:
        raise GigSourceError("proctor's answer was not the events we expect") from problem


def parse_gig_filters(
    country: Optional[str] = None,
    lineup: Optional[str] = None,
    dow: Optional[str] = None,
    dates: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[Dict, str]:
    """Validate raw query params; raises FilterError on a malformed value."""
    spec, description = parse_filters(None, dow, dates, date_from, date_to)
    parts = [description] if description else []
    if country is not None:
        countries = [c.strip() for c in country.split(',') if c.strip()]
        if not countries:
            raise FilterError("country must list countries, e.g. country=UK")
        spec['country'] = {c.casefold() for c in countries}
        parts.insert(0, f"country={','.join(countries)}")
    if lineup is not None:
        cleaned = lineup.strip().casefold()
        if not cleaned:
            raise FilterError("lineup must not be empty")
        spec['lineup'] = cleaned
        parts.append(f"lineup~{cleaned}")
    return spec, ' '.join(parts)


def gig_matches(event: Dict, spec: Dict) -> bool:
    if 'country' in spec and (event.get('country') or '').casefold() not in spec['country']:
        return False
    if 'lineup' in spec:
        names = list(event.get('lineup') or []) + list(event.get('support') or [])
        names += [a['name'] for a in event.get('tracked_artists') or []]
        names.append(event.get('summary') or '')
        if not any(spec['lineup'] in n.casefold() for n in names):
            return False
    return date_matches(event.get('start'), spec)


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%a} {d.day} {d:%b %Y}"


def gig_when(event: Dict) -> str:
    start, end = event['start'], event.get('end') or event['start']
    if end == start:
        return _day(start)
    return f"{_day(start)} to {_day(end)}"


def gig_title(event: Dict) -> str:
    """"My artist" and the date. The tracked artists proctor found, in
    billing order; failing that the first-named act, or the festival."""
    names = [a['name'] for a in event.get('tracked_artists') or []]
    if not names:
        lineup = event.get('lineup') or []
        names = [lineup[0]] if lineup and event.get('kind') != 'festival' else [event.get('summary') or 'Gig']
    shown = names[:MAX_NAMES_IN_TITLE]
    who = ', '.join(shown)
    if len(names) > len(shown):
        who += f" and {len(names) - len(shown)} more"
    return f"{who} - {gig_when(event)}"


def gig_body(event: Dict) -> str:
    """Line 1: the venue, linked to a map. Line 2: the line-up."""
    venue = escape(event.get('venue') or 'Venue unknown')
    address = event.get('address') or event.get('venue') or ''
    place = f'<a href="https://maps.apple.com/?q={quote(address)}">{venue}</a>' if address else venue
    if event.get('kind') == 'festival':
        place = f"{escape(event.get('summary') or 'Festival')} at {place}"
    lineup = ', '.join(event.get('lineup') or [])
    support = ', '.join(event.get('support') or [])
    if lineup and support:
        lineup = f"{lineup}, with {support}"
    body = f"<p>{place}</p>"
    if lineup:
        body += f"<p>{escape(lineup)}</p>"
    return body


def add_gig_entry(fg, event: Dict, site_url: str) -> None:
    fe = fg.add_entry()
    # Fixed to Songkick's event id: a changed line-up or venue must update the
    # item in place, never resurface it (tested with NetNewsWire, 2026-11-22).
    fe.id(f"{site_url}/gig/{event['id']}")
    fe.title(gig_title(event))
    fe.link(href=event['url'])
    fe.description(gig_body(event))
    # no published date: Songkick gives no announce time, and the reader's
    # own arrival order is what "new" means here
