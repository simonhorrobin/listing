# BFI IMAX Listings

Scrapes the BFI IMAX schedule daily and serves it as a web page and RSS
feeds. Live at https://listing.dynamicalsystem.com.

The RSS feed is the primary interface: point a feed reader at it and new
showings arrive as unread items after the nightly scrape. Each item carries
the film, date/time, ticket availability, and a link straight to the
showing's seat-selection page.

## Feeds

| URL | Contents |
|---|---|
| `/rss/current` | every upcoming showing |
| `/rss/daily` | showings added in the last 24 hours |

### Filtering

Both feeds accept query parameters; a "subscription" is just a bookmarked
URL. Filters compose as intersection. Invalid values return a 400 so a bad
bookmark fails when you create it, not silently forever.

| Parameter | Example | Meaning |
|---|---|---|
| `title` | `?title=dune` | case-insensitive substring on the film title |
| `dow` | `?dow=fri,sat` | day-of-week set (`mon`..`sun`) |
| `dates` | `?dates=2026-12-15,2026-12-19` | explicit dates (YYYY-MM-DD) |
| `from` / `to` | `?from=2026-12-01&to=2026-12-31` | inclusive date range |

Examples:

    https://listing.dynamicalsystem.com/rss/current?title=dune
    https://listing.dynamicalsystem.com/rss/current?dow=fri,sat
    https://listing.dynamicalsystem.com/rss/current?title=odyssey&dates=2026-09-19

## Gig feed

A second feed family: upcoming gigs by the artists tracked on Songkick.

| Feed | Contents |
|---|---|
| `/gigs/rss/current?key=...` | every upcoming gig, one item per event |

The events come from proctor, dynamicalsystem's internal API proxy, which
joins Songkick's calendar with the tracked-artist list. listing keeps no copy
and holds no Songkick credentials; it asks proctor (`PROCTOR_URL`), filters
and renders. If proctor cannot be reached the gig feed answers 503 and the
BFI feeds are unaffected.

The feed names the artists being tracked, so it is not public. The URL must
carry `key=` matching `GIGS_FEED_KEY`; without it the route answers 404, and
with no key configured the route is off.

Each item is titled with the tracked artists that caused the event and the
date, and links to the Songkick event page. The body is the venue, linked to
a map, then the line-up. Where proctor found no tracked artist the title
falls back to the first-named act. The item id is fixed to Songkick's event
id, so a changed line-up or venue updates the item in place.

Filters, composed as intersection; a malformed value is a 400:

| Parameter | Meaning |
|---|---|
| `country=UK,US` | events in these countries |
| `lineup=orbital` | case-insensitive substring over the line-up, support and tracked artists |
| `dow`, `dates`, `from`, `to` | as the showings feeds, on the event's first day |

## Other endpoints

- `/` - HTML view of all upcoming showings
- `/health` - JSON health and freshness info

## Development

Python 3.13, managed with uv:

    uv sync
    uv run pytest              # offline suite (live probes live in experiments/)
    uv run uvicorn dynamicalsystem.listing.webserver.main:app

Daily maintenance (scrape + prune) runs as a one-shot:

    uv run python -m dynamicalsystem.listing.maintenance.daily --dry-run

Deployment: merges to main build a multi-arch image to GHCR
(.github/workflows/release.yml); the gateway box pulls it via podman
auto-update as tinsnip-managed Quadlet units. Planning happens on the
`ooda` orphan branch (control plane); see that branch for loops and
decisions.
