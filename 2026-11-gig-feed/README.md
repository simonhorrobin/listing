---
loop: 2026-11-gig-feed
product: listing
owner: dynamicalsystem
status: Act
parent: null
blocked-by: []
worktrees: []
prs: ["simonhorrobin/listing#3", "simonhorrobin/listing#4", "simonhorrobin/tinsnip#31"]
triggers: []
---

# Gig Feed

## Status

Act

**Owner:** dynamicalsystem

## Context

Opened 2026-11-22. listing already serves RSS as its primary interface for
BFI IMAX showings. Simon wants the same for gigs: a feed of upcoming shows
by the artists he follows on Songkick, so that a newly announced gig
reaches his feed reader without opening Songkick.

This README was rewritten on 2026-11-22. listing's repo is public and the
first version recorded account detail that does not belong here. The full
record, with the evidence behind the numbers below, is kept in the private
proctor repo's control plane (`2026-11-songkick-calendar/`).

## Observations

### The source

- Songkick publishes an account's calendar of followed artists as an
  iCalendar feed. It has no RSS or Atom equivalent.
- Each event has a stable id, all-day dates, one summary string holding
  line-up, venue and date, a location string, and a link to the event
  page. There is no artist field, no area key, no announce time and no
  ticket link.
- The location string ends in the country on every event observed, and
  venue names can contain commas, so it has to be read from the right.
  Town is an inconsistent mix of city and district and is not usable as a
  filter. Country lines up with the areas the account follows while there
  is one followed area per country.
- Festivals appear with a name only; their line-up is not in the feed.
- Residencies appear as one event per night.
- The feed does not say which act on a bill is the followed one. In a
  sample, the followed act was first-named on about seven bills in ten;
  otherwise it was a later act or the support.
- Songkick's edge caches the feed for six hours.

### The reader (experiment A1, 2026-11-22)

A throwaway feed was served to NetNewsWire on iOS, with items that had a
non-permalink guid, a title, a link and a description, and no published
date. After the items were read, one item's title and description were
changed under the same guid and a new item was added.

- The new guid arrived unread.
- The changed item showed its new title and stayed read.
- The reader paces its own fetches: a manual refresh did not fetch for
  some minutes (more than about 3, less than 15).
- Not covered: an item that disappears from the feed, and a changing
  published date.

### listing as it was

- `/rss/current` and `/rss/daily` for BFI IMAX showings. Loop
  `2026-09-query-alerts` decided RSS-first: a stable guid per item,
  filters in the URL, "a subscription is a bookmarked URL".
- `webserver/filters.py`: `parse_filters` validates `title`, `dow`,
  `dates`, `from`, `to` into a plain dict and does not touch the showings
  model. Only `matches(showing, spec)` does, and its date logic is
  model-independent.
- `Showing`, the database and the scraper are specific to the BFI source.

## Orientation

**The pattern fits; the model does not.** Gigs are a second source of
"things I could attend" and the RSS-first decision applies unchanged. But
gigs do not flow through `Showing`, the database or the scraper. This is a
second feed family in the same service, not a generalisation of the
showings model.

**"New" means a guid the reader has not seen.** With no announce time in
the source, the reader's unread state is the only definition available,
and A1 shows it works: fix the guid to Songkick's event id and a changed
event updates in place.

**Place is a filter in the URL.** "Near me" cannot be computed from the
feed. `country` is the handle that matches how the account follows areas.

**"My artist" is the point, and listing cannot know it.** Simon defined
it as the followed artist that caused the event to appear. Working that
out needs the account's followed-artist list, which is private and needs a
signed-in session, and for festivals a read of the festival page. None of
that belongs in a public repo or in listing.

**So the join lives behind an internal API proxy.** Simon's direction:
sites that need a session, user actions or scraping sit behind a
dynamicalsystem API proxy with routes shaped around our domain, and
products talk either to a supported API or to the proxy. That product is
proctor (private). It serves upcoming events with the followed artists
already resolved. listing asks it, filters and renders, and is back to a
single fetch with no store and no private data.

**Assumptions.**
- A1: the reader does not resurface a changed item. Holds (experiment).
- A2: load on Songkick is light. It is proctor's to keep; listing never
  calls Songkick.
- A3: location parses well enough for a place filter. Holds for country.
- A4: terms and consent for reading Songkick. Tracked in proctor's loop.

## Decision

Made 2026-11-22.

**Source.** listing asks proctor (`PROCTOR_URL`) for its Songkick events
on each feed request. listing keeps no copy, no store and no Songkick
knowledge or credentials. If proctor cannot be reached or is not
configured, the gig feed answers 503 with a clear error and the BFI feeds
are unaffected.

**Route.** `GET /gigs/rss/current`.

**Filters**, composed as intersection; a bad value is a 400: `country`
(one or more), `lineup` (substring over the line-up, support and followed
artists), and the existing `dow`, `dates`, `from`, `to`, applied to the
event's first day. No postcode or town filter. `filters.py` is reused: its
date checks move into a helper both feeds call; `matches(showing, spec)`
keeps its behaviour and its tests.

**Item.**
- guid: fixed to Songkick's event id; one item per event; residencies are
  not collapsed.
- Title: "my artist" (every followed artist proctor found, in billing
  order) and the date. Where proctor found none, the first-named act, or
  the festival's name.
- The title links to the Songkick event page.
- Body line 1: the venue name, linked to a map (a festival's name goes
  before it). Body line 2: the line-up, with support.
- No published date, as tested in A1.

**The feed is open.** The first release required a key in the URL,
because a feed titled by followed artist shows who is followed. Simon
decided the same day that it does not need one; the key was removed
(listing#4).

**Deploy.** listing's unit joins proctor's network and gains `PROCTOR_URL`
in its env file.

## Action

- 2026-11-22: proctor built and deployed (its own loop, in the proctor
  repo).
- 2026-11-22: simonhorrobin/listing#3 merged after the offline tests
  passed in CI: `webserver/gigs.py`, the route, the `date_matches` helper
  in `filters.py`, configuration, README, 20 new tests (214 in all).
  `matches(showing, spec)` and its tests are unchanged.
- 2026-11-22: simonhorrobin/tinsnip#31: listing's unit joins proctor's
  network. listing restarted once on the gateway; healthy.
- 2026-11-22: checked live straight after: the gig feed returned 110
  items, 71 with `country=UK` and none of those outside the UK; a
  malformed filter returned 400; `/rss/current`, `/rss/daily`, a filtered
  `/rss/current` and `/health` answered as before.
- 2026-11-22: simonhorrobin/listing#4 removes the key from the feed.
- 2026-11-22: this branch's history for the loop was rewritten to remove
  account detail; the full record moved to proctor's private control
  plane.

Not done yet:
- The outcome tests that need a real newly announced show and a real
  changed event, observed over the coming days.
- Some titles fall back to the first-named act until proctor has read the
  whole followed-artist list. Those titles change in place; the guid does
  not.

## Outcomes

### Outcome 1: Simon sees a newly announced gig near him without opening Songkick

Tests:
- [ ] A feed reader subscribed to the gig feed shows a show announced for
      a followed artist as a new unread item within two days of it
      appearing on Songkick.
- [/] The item gives the line-up, date, venue and a link to the concert.
      (Live, 2026-11-22.)
- [ ] An item is not shown as new a second time when its details change.

### Outcome 2: "Near me" is Simon's to tune without a release

Tests:
- [/] A filtered feed URL excludes events outside the chosen country and
      keeps those inside it. (Live, 2026-11-22.)
- [/] A malformed filter value returns a 400, as the showings feeds do.
      (Live, 2026-11-22.)

### Outcome 3: The gig feed is a light, well-behaved client of Songkick

Tests:
- [/] listing holds no copy of Songkick's data and no Songkick
      credentials; proctor keeps the request limits.
- [~] With proctor unreachable the gig feed answers a clear 503 and the
      BFI feeds still work. (Passes in the offline tests; not induced on
      the box.)
