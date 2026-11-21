import pytest

from devseed.streaming import seed_streaming

pytestmark = pytest.mark.django_db


@pytest.fixture
def live():
    seed_streaming(lambda m: None)


def test_home_rails_and_live_channels(api, live):
    d = api.get("/api/v1/live/home").json()
    assert d["featured"]["slug"] == "open-movie-shorts"
    assert [r["id"] for r in d["rails"]][:2] == ["series", "films"]
    assert d["live"][0]["slug"] == "click-test-live" and "streamUrl" not in d["live"][0]
    assert d["continueWatching"] == [] and d["watchlist"] == []


def test_title_seasons_play_next_and_resume(auth_api, live):
    t = auth_api.get("/api/v1/live/titles/open-movie-shorts").json()
    eps = t["seasons"][0]["episodes"]
    assert [e["name"] for e in eps] == ["Elephants Dream", "Big Buck Bunny"] and t["playNext"]["id"] == eps[0]["id"]
    p = auth_api.get(f"/api/v1/live/play/{eps[0]['id']}").json()
    assert p["videoUrl"].endswith(".mp4") and p["next"]["name"] == "Big Buck Bunny" and p["resumeAt"] == 0
    assert auth_api.post("/api/v1/customer/live/progress", {"episode": eps[0]["id"], "position": 120, "duration": 654}).json()["finished"] is False
    assert auth_api.get(f"/api/v1/live/play/{eps[0]['id']}").json()["resumeAt"] == 120
    home = auth_api.get("/api/v1/live/home").json()
    assert home["continueWatching"][0]["episode"]["name"] == "Elephants Dream" and home["continueWatching"][0]["percent"] == 18
    # Finishing an episode moves "play next" on.
    auth_api.post("/api/v1/customer/live/progress", {"episode": eps[0]["id"], "position": 640, "duration": 654})
    assert auth_api.get("/api/v1/live/titles/open-movie-shorts").json()["playNext"]["name"] == "Big Buck Bunny"


def test_watchlist_toggle_and_search(auth_api, live, api):
    assert auth_api.post("/api/v1/customer/live/watchlist/sintel").json() == {"inWatchlist": True}
    assert [w["slug"] for w in auth_api.get("/api/v1/live/home").json()["watchlist"]] == ["sintel"]
    assert auth_api.post("/api/v1/customer/live/watchlist/sintel").json() == {"inWatchlist": False}
    assert [r["slug"] for r in auth_api.get("/api/v1/live/search", {"q": "dragon"}).json()["results"]] == ["sintel"]
    ch = auth_api.get("/api/v1/live/channels/click-test-live").json()
    assert ch["streamUrl"].endswith(".m3u8")
