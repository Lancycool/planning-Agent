import json
from http.server import HTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from content_agent import web


@pytest.fixture
def service(tmp_path, monkeypatch):
    original = web.Store
    monkeypatch.setattr(web, "Store", lambda _: original(tmp_path / "web.sqlite3"))
    server = HTTPServer(("127.0.0.1", 0), web.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_assets_and_record(service):
    for path in ("/", "/app.js", "/style.css", "/api/example/replan"):
        with urlopen(service + path) as response:
            assert response.status == 200 and response.read()


def test_secret_file_is_not_served(service):
    with pytest.raises(HTTPError) as error:
        urlopen(service + "/.env")
    assert error.value.code == 404


def test_cross_origin_is_rejected(service):
    request = Request(service + "/api/run", data=b"{}", headers={"Origin": "https://example.com"})
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 403


def test_offline_run(service):
    from datetime import datetime, timedelta, timezone
    payload = {"request_id": "web-test", "theme": "字幕产品活动", "budget": 10, "mode": "mock",
               "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    request = Request(service + "/api/run", data=json.dumps(payload).encode(),
                      headers={"Origin": service, "Content-Type": "application/json"})
    with urlopen(request) as response:
        output = json.load(response)
    assert output["status"] == "completed" and output["model_mode"] == "mock"
    assert output["cost"]["spent"] == 8


def test_duplicate_submission_replays_without_model_calls(service, monkeypatch):
    from datetime import datetime, timedelta, timezone

    calls = []
    original = web.MockModel.choose

    def choose(self, state):
        calls.append(state["request"]["request_id"])
        return original(self, state)

    monkeypatch.setattr(web.MockModel, "choose", choose)
    payload = {"request_id": "web-stable", "theme": "字幕活动", "budget": 10, "mode": "mock",
               "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}

    def submit(fields):
        request = Request(service + "/api/run", data=json.dumps(fields).encode(),
                          headers={"Origin": service, "Content-Type": "application/json"})
        with urlopen(request) as response:
            return json.load(response)

    first = submit(payload)
    count = len(calls)
    second = submit(payload)
    assert second["replayed"] and second["run_id"] == first["run_id"]
    assert len(calls) == count
    assert second["saved"] == first["saved"] and second["cost"] == first["cost"]
    conflict = submit({**payload, "budget": 9})
    assert conflict["reason_code"] == "REQUEST_CONFLICT" and len(calls) == count
    new = submit({**payload, "request_id": "web-new"})
    assert not new["replayed"] and len(calls) > count
