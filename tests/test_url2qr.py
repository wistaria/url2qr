import url2qr


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise url2qr.requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


def test_shorten_with_bitly_success(monkeypatch):
    def fake_post(url, headers, json, timeout):
        assert url == "https://api-ssl.bitly.com/v4/shorten"
        assert headers["Authorization"] == "Bearer token123"
        assert json["long_url"] == "https://example.com"
        assert timeout == 10
        return FakeResponse({"link": "https://bit.ly/abc123"})

    monkeypatch.setattr(url2qr.requests, "post", fake_post)

    result = url2qr.shorten_with_bitly("https://example.com", "token123")
    assert result == "https://bit.ly/abc123"


def test_make_qr_calls_save(monkeypatch, tmp_path):
    output = tmp_path / "out.png"
    called = {}

    class FakeImage:
        def save(self, path):
            called["path"] = path

    def fake_make(text):
        called["text"] = text
        return FakeImage()

    monkeypatch.setattr(url2qr.qrcode, "make", fake_make)

    url2qr.make_qr("https://bit.ly/abc123", str(output))

    assert called["text"] == "https://bit.ly/abc123"
    assert called["path"] == str(output)


def test_main_success_default_original_target(monkeypatch, capsys):
    monkeypatch.setenv("BITLY_ACCESS_TOKEN", "token123")
    monkeypatch.setattr(url2qr, "shorten_with_bitly", lambda u, t: "https://bit.ly/xyz")

    captured = {}

    def fake_make_qr(text, output):
        captured["text"] = text
        captured["output"] = output

    monkeypatch.setattr(url2qr, "make_qr", fake_make_qr)

    exit_code = url2qr.main(["https://example.com", "-o", "qr.png"])
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert captured["text"] == "https://example.com"
    assert captured["output"] == "qr.png"
    assert "Original URL: https://example.com" in stdout
    assert "Short URL:    https://bit.ly/xyz" in stdout


def test_main_uses_short_when_requested(monkeypatch):
    monkeypatch.setenv("BITLY_ACCESS_TOKEN", "token123")
    monkeypatch.setattr(url2qr, "shorten_with_bitly", lambda u, t: "https://bit.ly/xyz")

    captured = {}
    monkeypatch.setattr(
        url2qr,
        "make_qr",
        lambda text, output: captured.update({"text": text, "output": output}),
    )

    exit_code = url2qr.main(["https://example.com/path", "--qr-target", "short"])

    assert exit_code == 0
    assert captured["text"] == "https://bit.ly/xyz"
    assert captured["output"] == "qrcode.png"


def test_main_fails_without_token(monkeypatch, capsys):
    monkeypatch.delenv("BITLY_ACCESS_TOKEN", raising=False)

    exit_code = url2qr.main(["https://example.com"])
    stderr = capsys.readouterr().err

    assert exit_code == 1
    assert "BITLY_ACCESS_TOKEN is not set" in stderr
