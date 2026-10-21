"""Send a Telegram message whose link sits in an inline URL button.

A URL a model composes into message text can come back shortened: a 398-char
sign-in link once reached the chat as 283 chars. A button's url is set here by
code, so the link never passes through the model.
"""
import json
import os
import urllib.error
import urllib.request

_API = "https://api.telegram.org/bot"
_TIMEOUT_S = 10


def _err(msg) -> str:
    return json.dumps({"ok": False, "error": str(msg)})


def _home_chat():
    chat_id = os.environ.get("TELEGRAM_HOME_CHANNEL", "").split(",")[0].strip()
    if chat_id.startswith("@"):
        return chat_id
    return int(chat_id)


def _keyboard(buttons, columns) -> list:
    row = []
    keyboard = []
    cols = max(1, int(columns))
    for b in buttons:
        if not isinstance(b, dict) or not b.get("text") or not b.get("url"):
            raise ValueError("each button needs 'text' and 'url'")
        row.append({"text": b["text"], "url": b["url"]})
        if len(row) >= cols:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return keyboard


def _send(payload: dict) -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return _err("TELEGRAM_BOT_TOKEN not set")
    req = urllib.request.Request(
        f"{_API}{token}/sendMessage",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return json.dumps({"ok": True, "message_id": data["result"]["message_id"]})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            desc = json.loads(raw).get("description") or raw[:300]
        except Exception:
            desc = raw[:300] or exc.reason
        return _err(f"HTTP {exc.code}: {desc}")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def send_with_buttons(text: str, buttons: list, columns: int = 1) -> str:
    """Send text with inline URL buttons to the owner's chat (TELEGRAM_HOME_CHANNEL).

    Returns JSON {"ok": true, "message_id": N} or {"ok": false, "error": "..."}.
    """
    if not isinstance(buttons, list) or not buttons:
        return _err("buttons must be a non-empty list of {text, url}")
    try:
        keyboard = _keyboard(buttons, columns)
    except ValueError as exc:
        return _err(str(exc))
    try:
        chat_id = _home_chat()
    except ValueError as exc:
        return _err(f"bad TELEGRAM_HOME_CHANNEL: {exc}")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": keyboard},
    }
    return _send(payload)
