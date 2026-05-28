import dropbox2qr_cli as dropbox2qr
import pytest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def raise_for_status(self):
        if self.status_code >= 400:
            raise dropbox2qr.requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


def test_normalize_dropbox_path_from_local_path():
    path = "/Users/test/Library/CloudStorage/Dropbox/MyFolder/file.txt"
    assert dropbox2qr.normalize_dropbox_path(path) == "/MyFolder/file.txt"


def test_normalize_dropbox_path_from_cloudstorage_personal_path():
    path = "/Users/test/Library/CloudStorage/Dropbox (Personal)/MyFolder/file.txt"
    assert dropbox2qr.normalize_dropbox_path(path) == "/MyFolder/file.txt"


def test_normalize_dropbox_path_strips_trailing_slash_from_local_folder():
    path = "/Users/test/Dropbox/Public/PhotoTodo/"
    assert dropbox2qr.normalize_dropbox_path(path) == "/Public/PhotoTodo"


def test_normalize_dropbox_path_strips_trailing_slash_from_api_path():
    assert (
        dropbox2qr.normalize_dropbox_path("/Public/PhotoTodo/") == "/Public/PhotoTodo"
    )


def test_normalize_dropbox_path_from_relative_input():
    assert (
        dropbox2qr.normalize_dropbox_path("MyFolder/file.txt") == "/MyFolder/file.txt"
    )


def test_get_or_create_shared_url_create_success(monkeypatch):
    monkeypatch.setattr(
        dropbox2qr,
        "_post_dropbox_api",
        lambda endpoint, token, payload: FakeResponse(
            {"url": "https://www.dropbox.com/s/abc/file"}
        ),
    )

    result = dropbox2qr.get_or_create_shared_url("/MyFolder/file.txt", "token")
    assert result == "https://www.dropbox.com/s/abc/file"


def test_get_or_create_shared_url_fallback_to_list(monkeypatch):
    calls = {"count": 0}

    def fake_post(endpoint, token, payload):
        calls["count"] += 1
        if endpoint == "sharing/create_shared_link_with_settings":
            return FakeResponse(
                {"error_summary": "shared_link_already_exists"}, status_code=409
            )
        return FakeResponse(
            {"links": [{"url": "https://www.dropbox.com/s/existing/file"}]}
        )

    monkeypatch.setattr(dropbox2qr, "_post_dropbox_api", fake_post)

    result = dropbox2qr.get_or_create_shared_url("/MyFolder/file.txt", "token")
    assert result == "https://www.dropbox.com/s/existing/file"
    assert calls["count"] == 2


def test_get_or_create_shared_url_fallback_to_list_on_400(monkeypatch):
    calls = {"count": 0}

    def fake_post(endpoint, token, payload):
        calls["count"] += 1
        if endpoint == "sharing/create_shared_link_with_settings":
            return FakeResponse(
                {"error_summary": "settings_error/not_authorized"}, status_code=400
            )
        return FakeResponse(
            {"links": [{"url": "https://www.dropbox.com/s/existing/folder"}]}
        )

    monkeypatch.setattr(dropbox2qr, "_post_dropbox_api", fake_post)

    result = dropbox2qr.get_or_create_shared_url("/MyFolder", "token")
    assert result == "https://www.dropbox.com/s/existing/folder"
    assert calls["count"] == 2


def test_get_or_create_shared_url_includes_error_details(monkeypatch):
    def fake_post(endpoint, token, payload):
        if endpoint == "sharing/create_shared_link_with_settings":
            return FakeResponse({"error_summary": "path/not_found"}, status_code=400)
        return FakeResponse({"error_summary": "path/not_found"}, status_code=409)

    monkeypatch.setattr(dropbox2qr, "_post_dropbox_api", fake_post)

    with pytest.raises(ValueError) as exc_info:
        dropbox2qr.get_or_create_shared_url("/DoesNotExist", "token")

    message = str(exc_info.value)
    assert "create_shared_link_with_settings" in message
    assert "list_shared_links" in message
    assert "error_summary=path/not_found" in message


def test_extract_missing_scopes():
    message1 = "status=400, body=...required scope 'sharing.write'..."
    message2 = "status=400, body=...required scope 'sharing.read'..."
    result = dropbox2qr._extract_missing_scopes(message1, message2)
    assert result == ["sharing.read", "sharing.write"]


def test_has_missing_scope_error():
    assert dropbox2qr._has_missing_scope_error(
        "status=401, error_summary=missing_scope/"
    )
    assert not dropbox2qr._has_missing_scope_error(
        "status=400, error_summary=path/not_found"
    )


def test_get_or_create_shared_url_includes_scope_hint(monkeypatch):
    required_write = (
        'Error in call to API function "sharing/create_shared_link_with_settings": '
        "required scope 'sharing.write'"
    )
    required_read = (
        'Error in call to API function "sharing/list_shared_links": '
        "required scope 'sharing.read'"
    )

    def fake_post(endpoint, token, payload):
        if endpoint == "sharing/create_shared_link_with_settings":
            return FakeResponse(required_write, status_code=400)
        return FakeResponse(required_read, status_code=400)

    monkeypatch.setattr(dropbox2qr, "_post_dropbox_api", fake_post)

    with pytest.raises(ValueError) as exc_info:
        dropbox2qr.get_or_create_shared_url("/MyFolder", "token")

    message = str(exc_info.value)
    assert "Required Dropbox app scopes are missing" in message
    assert "sharing.write" in message
    assert "sharing.read" in message


def test_get_or_create_shared_url_includes_generic_missing_scope_hint(monkeypatch):
    def fake_post(endpoint, token, payload):
        return FakeResponse({"error_summary": "missing_scope/"}, status_code=401)

    monkeypatch.setattr(dropbox2qr, "_post_dropbox_api", fake_post)

    with pytest.raises(ValueError) as exc_info:
        dropbox2qr.get_or_create_shared_url("/MyFolder", "token")

    message = str(exc_info.value)
    assert "missing required app scopes" in message
    assert "sharing.read" in message
    assert "sharing.write" in message


def test_main_success_default_public_qr(monkeypatch):
    monkeypatch.setattr(
        dropbox2qr,
        "acquire_dropbox_token",
        lambda port, no_browser, configure=False: "dropbox-token",
    )
    monkeypatch.setattr(
        dropbox2qr,
        "acquire_bitly_token",
        lambda port, no_browser, configure=False: "bitly-token",
    )
    monkeypatch.setattr(
        dropbox2qr, "get_or_create_shared_url", lambda p, t: "https://dropbox.com/s/abc"
    )
    monkeypatch.setattr(
        dropbox2qr, "shorten_with_bitly", lambda u, t: "https://bit.ly/abc"
    )

    captured = {}
    monkeypatch.setattr(
        dropbox2qr,
        "make_qr",
        lambda text, output: captured.update({"text": text, "output": output}),
    )

    exit_code = dropbox2qr.main(["/MyFolder/file.txt", "-o", "dropbox.png"])

    assert exit_code == 0
    assert captured["text"] == "https://dropbox.com/s/abc"
    assert captured["output"] == "dropbox.png"


def test_main_uses_cached_oauth_credentials(monkeypatch):
    monkeypatch.setattr(dropbox2qr, "_load_dropbox_tokens", lambda: None)
    monkeypatch.setattr(
        dropbox2qr,
        "load_cached_fields",
        lambda path, fields: {
            "client_id": "client-id",
            "client_secret": "client-secret",
        },
    )
    monkeypatch.setattr(
        dropbox2qr,
        "get_dropbox_access_token",
        lambda cid, cs, port, no_browser: "oauth-token",
    )
    monkeypatch.setattr(
        dropbox2qr, "get_or_create_shared_url", lambda p, t: "https://dropbox.com/s/abc"
    )

    captured = {}
    monkeypatch.setattr(
        dropbox2qr,
        "make_qr",
        lambda text, output: captured.update({"text": text, "output": output}),
    )

    exit_code = dropbox2qr.main(["/MyFolder/file.txt", "--no-bitly"])

    assert exit_code == 0
    assert captured["text"] == "https://dropbox.com/s/abc"


def test_main_generates_public_qr_without_prompting_for_bitly(monkeypatch, capsys):
    seen = {}

    def no_bitly_token(port, no_browser, configure=False):
        seen["configure"] = configure
        return None

    monkeypatch.setattr(
        dropbox2qr,
        "acquire_dropbox_token",
        lambda port, no_browser, configure=False: "dropbox-token",
    )
    monkeypatch.setattr(dropbox2qr, "acquire_bitly_token", no_bitly_token)
    monkeypatch.setattr(
        dropbox2qr, "get_or_create_shared_url", lambda p, t: "https://dropbox.com/s/abc"
    )

    captured = {}
    monkeypatch.setattr(
        dropbox2qr,
        "make_qr",
        lambda text, output: captured.update({"text": text, "output": output}),
    )

    exit_code = dropbox2qr.main(["/MyFolder/file.txt", "--qr-target", "short"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert captured["text"] == "https://dropbox.com/s/abc"
    assert "Bitly URL:" not in output.out
    assert "Warning:" not in output.err
    assert seen["configure"] is False


def test_main_configures_bitly_when_requested(monkeypatch):
    seen = {}

    def configured_bitly_token(port, no_browser, configure=False):
        seen["configure"] = configure
        return "bitly-token"

    monkeypatch.setattr(
        dropbox2qr, "acquire_dropbox_token", lambda port, no_browser: "dropbox-token"
    )
    monkeypatch.setattr(dropbox2qr, "acquire_bitly_token", configured_bitly_token)
    monkeypatch.setattr(
        dropbox2qr, "get_or_create_shared_url", lambda p, t: "https://dropbox.com/s/abc"
    )
    monkeypatch.setattr(
        dropbox2qr, "shorten_with_bitly", lambda u, t: "https://bit.ly/abc"
    )
    monkeypatch.setattr(dropbox2qr, "make_qr", lambda text, output: None)

    exit_code = dropbox2qr.main(["/MyFolder/file.txt", "--bitly"])

    assert exit_code == 0
    assert seen["configure"] is True


def test_main_no_bitly_skips_shortening(monkeypatch, capsys):
    monkeypatch.setattr(
        dropbox2qr,
        "acquire_dropbox_token",
        lambda port, no_browser, configure=False: "dropbox-token",
    )
    monkeypatch.setattr(
        dropbox2qr,
        "acquire_bitly_token",
        lambda port, no_browser, configure=False: (_ for _ in ()).throw(
            AssertionError("unexpected")
        ),
    )
    monkeypatch.setattr(
        dropbox2qr, "get_or_create_shared_url", lambda p, t: "https://dropbox.com/s/abc"
    )

    captured = {}
    monkeypatch.setattr(
        dropbox2qr,
        "make_qr",
        lambda text, output: captured.update({"text": text, "output": output}),
    )

    exit_code = dropbox2qr.main(["/MyFolder/file.txt", "--no-bitly"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert captured["text"] == "https://dropbox.com/s/abc"
    assert "Bitly URL:" not in output.out
    assert "Warning:" not in output.err


def test_main_fails_when_dropbox_authentication_is_unavailable(monkeypatch, capsys):
    def fail_auth(port, no_browser):
        raise ValueError("Dropbox OAuth credentials are not configured")

    monkeypatch.setattr(dropbox2qr, "acquire_dropbox_token", fail_auth)
    exit_code = dropbox2qr.main(["/MyFolder/file.txt"])
    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "Dropbox authentication failed" in stderr
