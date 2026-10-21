"""signin_link mints a sign-in link for OWNER_EMAIL and sends it as a button in
the same call. The model gets a confirmation and the expiry, never the URL:
a model that relays a long opaque URL in its reply shortens it.

  (a) the tool takes only the lifetime; the email is never the model's to choose;
  (b) the confirmation never contains the minted url;
  (c) Telegram receives the url in reply_markup and never in the text;
  (d) the mutation goes to TRIP2G_URL/graphql under admin, with OWNER_TOKEN as a bearer;
  (e) a missing setting, trip2g's ErrorPayload, a GraphQL error, an HTTP
      failure and a failed Telegram send each come back as an "error: ..."
      string, never an exception and never a partial send.
"""

import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

SECONDBRAIN = Path(__file__).resolve().parent.parent
SERVER = SECONDBRAIN / "secondbrain_mcp.py"

OWNER_TOKEN = "t2g_test-owner-token"
OWNER_EMAIL = "owner@example.com"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("TRIP2G_URL", "http://trip2g:8380")
    monkeypatch.setenv("OWNER_TOKEN", OWNER_TOKEN)
    monkeypatch.setenv("OWNER_EMAIL", OWNER_EMAIL)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "555444333")
    return load(SERVER, "secondbrain_mcp_under_test_signin")


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


HAT_URL = "https://calls.example/_system/hat?token=eyVeryLongOpaqueHatTokenABCDEF123456"
EXPIRES_AT = "2026-08-13T13:05:00.123456789Z"


def hat_link_success():
    payload = {"__typename": "CreateHatLinkPayload", "url": HAT_URL, "expiresAt": EXPIRES_AT}
    return FakeResponse({"data": {"admin": {"createHatLink": payload}}})


def hat_link_error_payload(message):
    return FakeResponse({"data": {"admin": {"createHatLink": {"__typename": "ErrorPayload", "message": message}}}})


def telegram_ok():
    return FakeResponse({"ok": True, "result": {"message_id": 7}})


def router(trip2g_response=None, telegram_response=None, requests=None):
    def fake_urlopen(req, timeout=None):
        if requests is not None:
            requests.append(req)
        if req.full_url.endswith("/graphql"):
            return trip2g_response
        return telegram_response

    return fake_urlopen


def test_the_tool_takes_only_the_lifetime(server):
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert "signin_link" in tools

    schema = tools["signin_link"].input_schema
    assert schema.get("required", []) == []
    assert list(schema["properties"]) == ["expires_in_minutes"]
    assert schema["properties"]["expires_in_minutes"]["default"] == 5


def test_the_confirmation_never_contains_the_minted_url(server):
    with patch("urllib.request.urlopen", side_effect=router(hat_link_success(), telegram_ok())):
        out = server.signin_link()

    assert HAT_URL not in out
    assert "2026-08-13 13:05 UTC" in out
    assert "sent" in out.lower()


def test_the_url_reaches_telegram_only_in_reply_markup_never_in_text(server):
    requests = []
    with patch("urllib.request.urlopen", side_effect=router(hat_link_success(), telegram_ok(), requests)):
        server.signin_link()

    telegram_req = next(r for r in requests if "sendMessage" in r.full_url)
    payload = json.loads(telegram_req.data.decode("utf-8"))
    assert HAT_URL not in payload["text"]
    assert payload["chat_id"] == 555444333
    assert payload["reply_markup"]["inline_keyboard"] == [[{"text": "Войти", "url": HAT_URL}]]


def test_the_mutation_is_for_the_owner_and_carries_the_owner_token(server):
    requests = []
    with patch("urllib.request.urlopen", side_effect=router(hat_link_success(), telegram_ok(), requests)):
        server.signin_link(expires_in_minutes=30)

    graphql_req = next(r for r in requests if r.full_url.endswith("/graphql"))
    assert graphql_req.full_url == "http://trip2g:8380/graphql"
    assert graphql_req.get_header("Authorization") == f"Bearer {OWNER_TOKEN}"

    body = json.loads(graphql_req.data.decode("utf-8"))
    assert "admin" in body["query"]
    assert body["variables"]["input"] == {"email": OWNER_EMAIL, "expiresInMinutes": 30}


@pytest.mark.parametrize("missing", ["TRIP2G_URL", "OWNER_TOKEN", "OWNER_EMAIL"])
def test_a_missing_setting_is_a_clean_error_with_no_request_sent(server, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with patch("urllib.request.urlopen") as mocked:
        out = server.signin_link()

    assert out.startswith("error:")
    assert missing in out
    mocked.assert_not_called()


def test_trip2gs_own_error_payload_is_surfaced_and_telegram_is_never_called(server):
    requests = []
    response = hat_link_error_payload("expiresInMinutes: must be between 1 and 60")
    with patch("urllib.request.urlopen", side_effect=router(response, None, requests)):
        out = server.signin_link(expires_in_minutes=90)

    assert out == "error: expiresInMinutes: must be between 1 and 60"
    assert not any("sendMessage" in r.full_url for r in requests)


def test_a_graphql_level_error_is_surfaced(server):
    response = FakeResponse({"errors": [{"message": "unauthorized"}], "data": None})
    with patch("urllib.request.urlopen", side_effect=router(response, None, [])):
        out = server.signin_link()

    assert out == "error: unauthorized"


def test_an_http_failure_from_trip2g_is_a_clean_error(server):
    def raise_http_error(req, timeout=None):
        if req.full_url.endswith("/graphql"):
            raise HTTPError(req.full_url, 503, "Service Unavailable", None, None)
        return telegram_ok()

    with patch("urllib.request.urlopen", side_effect=raise_http_error):
        out = server.signin_link()

    assert out.startswith("error:")
    assert "503" in out


def test_a_failed_telegram_send_is_surfaced_and_not_silently_ok(server):
    def fail_telegram(req, timeout=None):
        if req.full_url.endswith("/graphql"):
            return hat_link_success()
        raise HTTPError(req.full_url, 400, "Bad Request", None, None)

    with patch("urllib.request.urlopen", side_effect=fail_telegram):
        out = server.signin_link()

    assert out.startswith("error sending the sign-in link:")
    assert HAT_URL not in out
