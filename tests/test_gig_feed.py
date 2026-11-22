"""Tests for the gig feed (loop 2026-11-gig-feed). proctor is a stand-in."""

import xml.etree.ElementTree as ET

import pytest
import requests
from fastapi.testclient import TestClient

from dynamicalsystem.listing.config import Config
from dynamicalsystem.listing.webserver import gigs
from dynamicalsystem.listing.webserver.filters import FilterError
from dynamicalsystem.listing.webserver.gigs import (
    gig_body, gig_matches, gig_title, parse_gig_filters,
)
from dynamicalsystem.listing.webserver.main import app

def event(**over):
    base = {
        "id": "1001", "kind": "concert", "start": "2027-01-12", "end": "2027-01-12",
        "summary": "Alpha, Beta, and Gamma Ray at The Windmill, Brixton (12 Jan 27)",
        "lineup": ["Alpha", "Beta", "Gamma Ray"], "support": [],
        "venue": "The Windmill, Brixton",
        "address": "The Windmill, 22 Blenheim Gardens, SW2 5BZ, London, UK",
        "postcode": "SW2 5BZ", "town": "London", "region": None, "country": "UK",
        "url": "https://www.songkick.com/concerts/1001-alpha",
        "tracked_artists": [{"id": "13", "name": "Gamma Ray"}], "tracked_found_by": "name",
    }
    base.update(over)
    return base


EVENTS = [
    event(),
    event(id="1002", start="2027-02-20", end="2027-02-20", summary="Delta at Baby's All Right (20 Feb 27) with Epsilon",
          lineup=["Delta"], support=["Epsilon"], venue="Baby's All Right",
          address="Baby's All Right, 146 Broadway, 11211, Brooklyn, NY, US", country="US", region="NY",
          url="https://www.songkick.com/concerts/1002-delta",
          tracked_artists=[{"id": "14", "name": "Epsilon"}]),
    event(id="1003", kind="festival", start="2027-03-05", end="2027-03-06", summary="Example Assembly 2027",
          lineup=["Theta", "Gamma Ray", "Iota"], venue="The Cause", address="The Cause, 60 Dock Rd, E16 1YZ, London, UK",
          url="https://www.songkick.com/festivals/77/id/1003",
          tracked_artists=[{"id": "13", "name": "Gamma Ray"}, {"id": "33", "name": "Iota"}], tracked_found_by="festival page"),
    event(id="1004", start="2027-04-01", end="2027-04-01", summary="Zeta & <Eta> at Barbican (01 Apr 27)",
          lineup=["Zeta & <Eta>", "Kappa"], venue="Barbican", address="Barbican, London, UK", postcode=None,
          url="https://www.songkick.com/concerts/1004-zeta", tracked_artists=[], tracked_found_by="none"),
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(Config, "PROCTOR_URL", "http://proctor:8000")
    monkeypatch.setattr(gigs, "fetch_events", lambda base, timeout: [dict(e) for e in EVENTS])
    monkeypatch.setattr("dynamicalsystem.listing.webserver.main.fetch_events", lambda base, timeout: [dict(e) for e in EVENTS])
    return TestClient(app)


def items(response):
    assert response.status_code == 200, response.text
    return ET.fromstring(response.content).findall("./channel/item")


def test_title_is_my_artist_and_the_date():
    assert gig_title(EVENTS[0]) == "Gamma Ray - Tue 12 Jan 2027"  # not the first-named act
    assert gig_title(EVENTS[1]) == "Epsilon - Sat 20 Feb 2027"  # the support act is mine
    assert gig_title(EVENTS[2]) == "Gamma Ray, Iota - Fri 5 Mar 2027 to Sat 6 Mar 2027"  # festival: my artists


def test_title_falls_back_knowingly_when_proctor_found_no_artist():
    assert gig_title(EVENTS[3]) == "Zeta & <Eta> - Thu 1 Apr 2027"
    assert gig_title(event(kind="festival", summary="Some Fest 2027", lineup=[], tracked_artists=[])).startswith("Some Fest 2027 - ")


def test_many_artists_are_cut_in_the_title():
    many = event(tracked_artists=[{"id": str(i), "name": f"A{i}"} for i in range(5)])
    assert gig_title(many) == "A0, A1, A2 and 2 more - Tue 12 Jan 2027"


def test_body_is_venue_with_a_map_link_then_the_lineup():
    body = gig_body(EVENTS[1])
    assert body == (
        '<p><a href="https://maps.apple.com/?q=Baby%27s%20All%20Right%2C%20146%20Broadway%2C%2011211%2C%20Brooklyn%2C%20NY%2C%20US">'
        "Baby&#x27;s All Right</a></p><p>Delta, with Epsilon</p>"
    )
    assert "Tue 12 Jan" not in gig_body(EVENTS[0]) and "Gamma Ray - " not in gig_body(EVENTS[0])  # no repeat of the title
    assert gig_body(EVENTS[2]).startswith("<p>Example Assembly 2027 at <a href=")
    assert "Zeta &amp; &lt;Eta&gt;, Kappa" in gig_body(EVENTS[3])  # names are escaped


def test_the_feed_is_open_and_ignores_a_leftover_key(client):
    assert len(items(client.get("/gigs/rss/current"))) == 4
    assert len(items(client.get("/gigs/rss/current?key=anything"))) == 4  # an old bookmark still works


def test_items_carry_guid_link_title_and_no_published_date(client):
    found = {i.findtext("guid"): i for i in items(client.get(f"/gigs/rss/current"))}
    item = found[f"{Config.SITE_URL}/gig/1001"]
    assert item.findtext("title") == "Gamma Ray - Tue 12 Jan 2027"
    assert item.findtext("link") == "https://www.songkick.com/concerts/1001-alpha"
    assert item.find("pubDate") is None
    assert "maps.apple.com" in item.findtext("description")


def test_the_guid_does_not_change_when_the_details_do(client, monkeypatch):
    changed = [dict(EVENTS[0], lineup=["Alpha", "Beta", "Gamma Ray", "New Support"], venue="Moved Hall",
                    tracked_artists=[{"id": "13", "name": "Gamma Ray"}, {"id": "16", "name": "Beta"}])]
    monkeypatch.setattr("dynamicalsystem.listing.webserver.main.fetch_events", lambda base, timeout: changed)
    (item,) = items(client.get(f"/gigs/rss/current"))
    assert item.findtext("guid") == f"{Config.SITE_URL}/gig/1001"


def test_soonest_first(client):
    guids = [i.findtext("guid").rsplit("/", 1)[1] for i in items(client.get(f"/gigs/rss/current"))]
    assert guids == ["1001", "1002", "1003", "1004"]


def test_country_filter_keeps_london_and_drops_new_york(client):
    kept = [i.findtext("guid").rsplit("/", 1)[1] for i in items(client.get(f"/gigs/rss/current?country=uk"))]
    assert kept == ["1001", "1003", "1004"]  # 1004 has no postcode and is kept
    both = items(client.get(f"/gigs/rss/current?country=UK,US"))
    assert len(both) == 4


def test_lineup_and_date_filters_compose(client):
    assert len(items(client.get(f"/gigs/rss/current?lineup=gamma"))) == 2
    assert len(items(client.get(f"/gigs/rss/current?lineup=gamma&from=2027-02-01"))) == 1
    assert len(items(client.get(f"/gigs/rss/current?dow=sat"))) == 1
    assert len(items(client.get(f"/gigs/rss/current?dates=2027-01-12,2027-04-01"))) == 2


@pytest.mark.parametrize("query", ["country=", "country=,", "lineup=%20", "dow=funday", "from=tomorrow", "dates=12/01/2027"])
def test_a_malformed_filter_is_a_400(client, query):
    assert client.get(f"/gigs/rss/current?{query}").status_code == 400


def test_filter_parsing_and_matching_units():
    spec, description = parse_gig_filters(country="UK, us", lineup="Orb", dow="fri")
    assert spec["country"] == {"uk", "us"} and spec["lineup"] == "orb" and description == "country=UK,us dow=fri lineup~orb"
    assert gig_matches(event(country=None), {}) is True
    assert gig_matches(event(country=None), {"country": {"uk"}}) is False
    with pytest.raises(FilterError):
        parse_gig_filters(country=" ")


def test_proctor_unreachable_is_a_clear_503_and_bfi_feeds_still_work(monkeypatch, tmp_path):
    from dynamicalsystem.listing.storage.db import Database
    db_path = str(tmp_path / "test.db")
    Database(db_path)
    monkeypatch.setattr(Config, "DB_PATH", db_path)
    monkeypatch.setattr(Config, "PROCTOR_URL", "http://proctor:8000")

    def refuse(*args, **kwargs):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(gigs.requests, "get", refuse)
    c = TestClient(app)
    answer = c.get(f"/gigs/rss/current")
    assert answer.status_code == 503 and "proctor unreachable" in answer.text
    assert c.get("/rss/current").status_code == 200


def test_unconfigured_proctor_and_bad_answers_are_503(monkeypatch):
    monkeypatch.setattr(Config, "PROCTOR_URL", "")
    assert TestClient(app).get(f"/gigs/rss/current").status_code == 503

    class Answer:
        status_code = 503
        def json(self):
            return {}

    monkeypatch.setattr(gigs.requests, "get", lambda *a, **k: Answer())
    with pytest.raises(gigs.GigSourceError):
        gigs.fetch_events("http://proctor:8000", 5)
