"""send_with_buttons puts the URL only in reply_markup, never in the text,
sends to the owner's chat, groups buttons into rows, and refuses a malformed
list or a missing token before any request."""

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

SECONDBRAIN = Path(__file__).resolve().parent.parent
MODULE = SECONDBRAIN / "telegram_buttons.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def buttons(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "555444333")
    return load(MODULE, "telegram_buttons_under_test")


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok_send_response():
    return FakeResponse({"ok": True, "result": {"message_id": 42}})


def capture(captured):
    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return ok_send_response()

    return fake_urlopen


def test_the_url_never_lands_in_the_text_field_only_in_reply_markup(buttons):
    captured = {}
    link = "https://calls.example/_system/hat?token=eyVeryLongOpaqueTokenXYZ"
    with patch("urllib.request.urlopen", side_effect=capture(captured)):
        out = buttons.send_with_buttons("Here is your link", [{"text": "Sign in", "url": link}])

    assert json.loads(out) == {"ok": True, "message_id": 42}
    assert "eyVeryLongOpaqueTokenXYZ" not in captured["payload"]["text"]
    assert captured["payload"]["reply_markup"]["inline_keyboard"] == [[{"text": "Sign in", "url": link}]]


def test_the_request_goes_to_api_telegram_org(buttons):
    captured = {}
    with patch("urllib.request.urlopen", side_effect=capture(captured)):
        buttons.send_with_buttons("hi", [{"text": "Open", "url": "https://x.example"}])

    assert captured["url"] == "https://api.telegram.org/bottest-token-123/sendMessage"


def test_the_chat_is_the_home_channel_and_a_thread_suffix_is_tolerated(buttons, monkeypatch):
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "555444333,7")
    captured = {}
    with patch("urllib.request.urlopen", side_effect=capture(captured)):
        buttons.send_with_buttons("hi", [{"text": "Open", "url": "https://x.example"}])

    assert captured["payload"]["chat_id"] == 555444333


def test_columns_groups_buttons_into_rows(buttons):
    captured = {}
    rows = [{"text": f"b{i}", "url": f"https://x.example/{i}"} for i in range(3)]
    with patch("urllib.request.urlopen", side_effect=capture(captured)):
        buttons.send_with_buttons("hi", rows, columns=2)

    keyboard = captured["payload"]["reply_markup"]["inline_keyboard"]
    assert [len(r) for r in keyboard] == [2, 1]


def test_an_empty_buttons_list_is_refused_before_any_request(buttons):
    with patch("urllib.request.urlopen") as mocked:
        out = buttons.send_with_buttons("hi", [])

    assert json.loads(out)["ok"] is False
    mocked.assert_not_called()


def test_a_button_missing_url_is_refused_before_any_request(buttons):
    with patch("urllib.request.urlopen") as mocked:
        out = buttons.send_with_buttons("hi", [{"text": "Open"}])

    assert json.loads(out)["ok"] is False
    mocked.assert_not_called()


def test_a_missing_bot_token_is_refused_before_any_request(buttons, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    with patch("urllib.request.urlopen") as mocked:
        out = buttons.send_with_buttons("hi", [{"text": "Open", "url": "https://x.example"}])

    assert json.loads(out) == {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    mocked.assert_not_called()


def test_an_http_failure_from_telegram_comes_back_as_a_clean_error(buttons):
    def raise_http_error(req, timeout=None):
        raise HTTPError(req.full_url, 400, "Bad Request", None, None)

    with patch("urllib.request.urlopen", side_effect=raise_http_error):
        out = buttons.send_with_buttons("hi", [{"text": "Open", "url": "https://x.example"}])

    result = json.loads(out)
    assert result["ok"] is False
    assert "400" in result["error"]
