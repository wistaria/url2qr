import box2qr
import pytest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def raise_for_status(self):
        if self.status_code >= 400:
            raise box2qr.requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


def test_normalize_box_path_from_local_path():
    path = "/Users/test/Library/CloudStorage/Box/MyFolder/file.txt"
    assert box2qr.normalize_box_path(path) == "/MyFolder/file.txt"


def test_normalize_box_path_from_box_personal_path():
    path = "/Users/test/Library/CloudStorage/Box (Personal)/MyFolder/file.txt"
    assert box2qr.normalize_box_path(path) == "/MyFolder/file.txt"


def test_normalize_box_path_from_relative_input():
    assert box2qr.normalize_box_path("MyFolder/file.txt") == "/MyFolder/file.txt"


def test_resolve_box_folder_id(monkeypatch):
    calls = []

    def fake_request(method, endpoint, token, params=None, json=None):
        calls.append((method, endpoint, params))
        if endpoint == "folders/0/items":
            return FakeResponse(
                {
                    "entries": [{"id": "123", "name": "MyFolder", "type": "folder"}],
                    "total_count": 1,
                    "offset": 0,
                    "limit": 1000,
                }
            )
        if endpoint == "folders/123/items":
            return FakeResponse(
                {
                    "entries": [{"id": "456", "name": "Sub", "type": "folder"}],
                    "total_count": 1,
                    "offset": 0,
                    "limit": 1000,
                }
            )
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(box2qr, "_box_api_request", fake_request)

    result = box2qr.resolve_box_folder_id("/MyFolder/Sub", "token")
    assert result == "456"
    assert calls[0][1] == "folders/0/items"
    assert calls[1][1] == "folders/123/items"


def test_get_or_create_shared_url_create_success(monkeypatch):
    def fake_request(method, endpoint, token, params=None, json=None):
        if method == "GET" and endpoint == "folders/0/items":
            return FakeResponse(
                {
                    "entries": [{"id": "123", "name": "MyFolder", "type": "folder"}],
                    "total_count": 1,
                    "offset": 0,
                    "limit": 1000,
                }
            )
        if method == "PUT" and endpoint == "folders/123":
            return FakeResponse({"shared_link": {"url": "https://box.com/s/abc"}})
        raise AssertionError(f"unexpected call: {method} {endpoint}")

    monkeypatch.setattr(box2qr, "_box_api_request", fake_request)

    result = box2qr.get_or_create_shared_url("/MyFolder", "token")
    assert result == "https://box.com/s/abc"


def test_get_or_create_shared_url_falls_back_to_get(monkeypatch):
    def fake_request(method, endpoint, token, params=None, json=None):
        if method == "GET" and endpoint == "folders/0/items":
            return FakeResponse(
                {
                    "entries": [{"id": "123", "name": "MyFolder", "type": "folder"}],
                    "total_count": 1,
                    "offset": 0,
                    "limit": 1000,
                }
            )
        if method == "PUT" and endpoint == "folders/123":
            return FakeResponse({"type": "error"}, status_code=200)
        if method == "GET" and endpoint == "folders/123":
            return FakeResponse({"shared_link": {"url": "https://box.com/s/existing"}})
        raise AssertionError(f"unexpected call: {method} {endpoint}")

    monkeypatch.setattr(box2qr, "_box_api_request", fake_request)

    result = box2qr.get_or_create_shared_url("/MyFolder", "token")
    assert result == "https://box.com/s/existing"


def test_get_or_create_shared_url_includes_permission_hint(monkeypatch):
    def fake_request(method, endpoint, token, params=None, json=None):
        if method == "GET" and endpoint == "folders/0/items":
            return FakeResponse(
                {
                    "entries": [{"id": "123", "name": "MyFolder", "type": "folder"}],
                    "total_count": 1,
                    "offset": 0,
                    "limit": 1000,
                }
            )
        if method == "PUT" and endpoint == "folders/123":
            return FakeResponse(
                {
                    "error": {
                        "code": "access_denied_insufficient_permissions",
                        "message": "not permitted",
                    }
                },
                status_code=403,
            )
        if method == "GET" and endpoint == "folders/123":
            return FakeResponse(
                {
                    "error": {
                        "code": "access_denied_insufficient_permissions",
                        "message": "not permitted",
                    }
                },
                status_code=403,
            )
        raise AssertionError(f"unexpected call: {method} {endpoint}")

    monkeypatch.setattr(box2qr, "_box_api_request", fake_request)

    with pytest.raises(ValueError) as exc_info:
        box2qr.get_or_create_shared_url("/MyFolder", "token")

    message = str(exc_info.value)
    assert "Box token is missing required permissions" in message


def test_main_success_public_qr(monkeypatch):
    monkeypatch.setenv("BITLY_ACCESS_TOKEN", "bitly-token")
    monkeypatch.setenv("BOX_ACCESS_TOKEN", "box-token")
    monkeypatch.setattr(
        box2qr, "get_or_create_shared_url", lambda p, t: "https://box.com/s/abc"
    )
    monkeypatch.setattr(box2qr, "shorten_with_bitly", lambda u, t: "https://bit.ly/abc")

    captured = {}
    monkeypatch.setattr(
        box2qr,
        "make_qr",
        lambda text, output: captured.update({"text": text, "output": output}),
    )

    exit_code = box2qr.main(["/MyFolder/file.txt", "-o", "box.png"])

    assert exit_code == 0
    assert captured["text"] == "https://box.com/s/abc"
    assert captured["output"] == "box.png"


def test_main_fails_without_box_token(monkeypatch, capsys):
    monkeypatch.setenv("BITLY_ACCESS_TOKEN", "bitly-token")
    monkeypatch.delenv("BOX_ACCESS_TOKEN", raising=False)

    exit_code = box2qr.main(["/MyFolder/file.txt"])
    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "BOX_ACCESS_TOKEN is not set" in stderr
