"""Secondbrain MCP server: the vault tools Hermes saves notes with, and signin_link.

The vault is the trip2g vault as Markdown files in /opt/data/secondbrain,
kept in step with trip2g by secondbrain-sync.sh. Every tool that changes a
note syncs it before it answers, so the files and the website never part.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram_buttons import send_with_buttons  # noqa: E402

HELPER = os.environ.get("SECONDBRAIN_HELPER", "/opt/secondbrain/secondbrainhelper.py")
SYNC_CMD = os.environ.get("HERMES_SYNC_CMD", "/opt/secondbrain/secondbrain-sync.sh")

_TRIP2G_TIMEOUT_S = 15

_CREATE_HAT_LINK = """
mutation($input: CreateHatLinkInput!) {
  admin {
    createHatLink(input: $input) {
      __typename
      ... on CreateHatLinkPayload { url expiresAt }
      ... on ErrorPayload { message }
    }
  }
}
"""

mcp = MCPServer("secondbrain")


def _run(cmd_args: list[str]) -> str:
    if not os.path.exists(HELPER):
        return f"error: helper not found at {HELPER}"
    try:
        r = subprocess.run(
            [sys.executable, HELPER, *cmd_args],
            capture_output=True, text=True, timeout=120,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return out or "(done, no output)"
    except Exception as e:  # noqa: BLE001
        return f"error running helper: {e}"


@mcp.tool()
def daily(text: str) -> str:
    """Append a timestamped entry to today's daily note and sync automatically.

    This is the ONLY correct way to journal. Pass the entry text, typically the
    user's message then your note: "user: <verbatim message>\\n<your reflection>".
    The helper stamps the time, creates the daily file and its index entry if
    missing, sends the change to trip2g, and returns the note tail followed by
    the URL(s) (format: "path → URL").

    Do NOT call sync afterwards — the change is already sent.
    Do NOT edit daily files by hand.

    Record only meaningful entries: decisions made, outcomes, facts or learnings
    worth keeping. Skip routine acknowledgements, step-by-step chatter, and
    trivial observations that add no value when read later."""
    return _run(["daily", text, "--sync"])


@mcp.tool()
def write_note(path: str, content: str, overwrite: bool = False, override_frontmatter: bool = False) -> str:
    """Save a note in the knowledge base: write the file and publish it, in one call.

    This is the ONLY correct way to save a note. The knowledge base is an Obsidian
    vault — a folder of Markdown files on this machine — which trip2g serves as a
    website. This tool writes the file and syncs it, so the two views carry the
    same note. Never save a note through GraphQL or any other tool: that reaches
    the website and leaves the vault on disk without the note, and the two then
    disagree for good.

    path is relative to the vault root, like "wiki/topic" or "inbox/2026-cost.md";
    ".md" is added when it is missing.

    An existing note is refused rather than replaced — add to one with `log`, and
    pass overwrite=true only when the user asked for the note to be rewritten.

    The note's own frontmatter, if it has one, rides through untouched by
    default — content becomes the body. Pass override_frontmatter=true only
    when the frontmatter itself is what needs to change. An overwrite whose
    content starts with its own frontmatter block is refused unless
    override_frontmatter=true: either pass it to replace the frontmatter, or
    send the body alone to keep the old one.

    The change is sent to trip2g before this returns. Returns the note's tail
    followed by the URL(s) (format: "path → URL").
    Do NOT call sync afterwards — the change is already sent."""
    cmd_args = ["write", path, content, "--sync"]
    if overwrite:
        cmd_args.append("--overwrite")
    if override_frontmatter:
        cmd_args.append("--override-frontmatter")
    return _run(cmd_args)


@mcp.tool()
def upsert_frontmatter_field(file: str, field: str, value: str) -> str:
    """Set one field in a note's YAML frontmatter. Every other field, and the
    whole body, come back exactly as they were.

    Only the block between the opening and closing "---" fences is parsed; the
    field is set in it and it is re-emitted with the YAML library doing the
    quoting, so multi-line values are safe — do not hand-format "field: value"
    yourself. The body is written back byte for byte. A file with no
    frontmatter gets one.

    file is a vault-relative path, same rule write_note uses: ".md" is added
    when missing, and a path that leaves the vault, absolute or carrying "..",
    is refused.

    Use this when a specific named field has to change and the body must not.
    To write or rewrite a note, use write_note; to add a line to one, use log;
    to make a note publicly readable, use publish_note rather than setting
    `free` through here.

    The change is sent to trip2g before this returns, and the note's URL(s)
    come back with it (format: "path → URL"). Do NOT call sync afterwards."""
    return _run(["upsert-frontmatter", file, field, value, "--sync"])


@mcp.tool()
def publish_note(file: str) -> str:
    """Make a note publicly readable, so its link serves the note to anyone.

    Every note is private by default: it already has a link, and that link
    refuses the note to everyone but its owner. This sets `free: true` in the
    note's frontmatter, which is the one thing that turns the existing link
    into a public one. Nothing else about the note changes.

    Use this ONLY when the user asked for the note to be published, shared, or
    made visible. Asking for a note's link is not asking for this — hand back
    the link and leave the note private. To take a note back out of public
    view, use upsert_frontmatter_field(file, "free", "false") — though a note
    that was public may already have been read.

    file is a vault-relative path, same rule write_note uses.

    The change is sent to trip2g before this returns, and the note's URL(s)
    come back with it (format: "path → URL"). Do NOT call sync afterwards."""
    return _run(["publish", file, "--sync"])


@mcp.tool()
def log(topic: str, text: str) -> str:
    """Append a dated line under a topic/wiki note without rewriting it.
    topic is a vault path like "wiki/foo" (no .md). Use for adding a new thought
    to an existing note.

    The change is sent to trip2g in the background, so no URL comes back here
    and the website may take a moment to catch up. Do NOT call sync afterwards
    — it is already on its way."""
    return _run(["log", topic, text])


_SYNC_FAILURE_MARKERS = (
    "Failed to fetch server hashes",
    "Failed to fetch",
)

_SYNC_BROKEN = (
    "error: the sync did not reach trip2g, so nothing was saved there. The "
    "notes are still only on this machine. Do NOT report them as stored, and do "
    "not repeat the counts below — they were computed against a server this run "
    "never read, so lines like 'Server deleted: N' mean nothing here. Tell the "
    "person the sync is broken and that you are passing it to technical support, "
    "then do so. Do not retry in a loop."
)


def _sync_failed(out: str) -> bool:
    return any(marker in out for marker in _SYNC_FAILURE_MARKERS)


@mcp.tool()
def index_append(index: str, note: str) -> str:
    """Add one link to an index note, once, under today's date.

    An index is a note whose body is a list of links to other notes: a
    folder's contents, the vault's entry point, a reading list. Use this
    instead of rewriting such a note with write_note — adding a line here can
    never replace what is already in the file.

    index is the index note's vault path, note is the path of the note to
    link; both without ".md" or with it. A note already linked from that index
    is not linked twice and nothing is written.

    The note has to exist first: a link to a note nobody wrote is a dead link.
    """
    return _run(["index", index, note])


@mcp.tool()
def sync() -> str:
    """Send local changes to trip2g, pull the changes made there, and return every note's link.

    Call this only when you changed files under /opt/data/secondbrain yourself,
    or when you need what someone changed on the website. Every other tool here
    sends its own change for you — daily, write_note, upsert_frontmatter_field
    and publish_note send before returning and hand back the link, and log
    sends in the background.

    Running it anyway is safe: it can be called any number of times, and a call
    with nothing to send costs only the time it takes.

    Sending is not publishing: a private note stays private. Making one
    readable is publish_note."""
    if not os.path.exists(SYNC_CMD):
        return f"error: sync command not found at {SYNC_CMD}"
    try:
        r = subprocess.run(
            [SYNC_CMD],
            capture_output=True, text=True, timeout=180,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode != 0 or _sync_failed(out):
            return _SYNC_BROKEN + "\n\n" + (out or "(no output)")
        return out or "(sync done, no output)"
    except Exception as e:  # noqa: BLE001
        return f"error running sync: {e}"


def _create_hat_link(expires_in_minutes: int):
    base = os.environ.get("TRIP2G_URL", "").strip().rstrip("/")
    if not base:
        return None, "TRIP2G_URL is not set."
    token = os.environ.get("OWNER_TOKEN", "").strip()
    if not token:
        return None, "OWNER_TOKEN is not set."
    email = os.environ.get("OWNER_EMAIL", "").strip()
    if not email:
        return None, "OWNER_EMAIL is not set."

    variables = {"input": {"email": email, "expiresInMinutes": int(expires_in_minutes)}}
    req = urllib.request.Request(
        base + "/graphql",
        data=json.dumps({"query": _CREATE_HAT_LINK, "variables": variables}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TRIP2G_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return None, f"HTTP {exc.code} minting the sign-in link: {raw[:300] or exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return None, f"error minting the sign-in link: {exc}"

    errors = data.get("errors")
    if errors:
        return None, "; ".join(e.get("message", "unknown error") for e in errors)

    payload = ((data.get("data") or {}).get("admin") or {}).get("createHatLink") or {}
    if payload.get("__typename") == "ErrorPayload":
        return None, payload.get("message", "trip2g refused the request")
    if "url" not in payload or "expiresAt" not in payload:
        return None, "trip2g returned no url"
    return payload, None


@mcp.tool()
def signin_link(expires_in_minutes: int = 5) -> str:
    """Send the owner a one-time link that signs them in to the dashboard, as a Telegram button.

    This is the ONLY correct way to hand out a sign-in link. Use it whenever
    the owner asks for a sign-in link, a login link, or to be let into the
    dashboard or the admin panel.

    Do NOT mint a link any other way and do NOT paste a sign-in URL into a
    reply. A long opaque token in text gets silently shortened or mistyped.
    This tool mints the link and sends it to the owner's chat as a button in
    the same call, so you never see the URL and never have to type it.

    Args:
        expires_in_minutes: link lifetime, 1..60. Defaults to 5.

    Returns:
        Confirmation that the link was sent and when it expires — never the
        link itself. An "error: ..." string on failure.
    """
    payload, error = _create_hat_link(expires_in_minutes)
    if error:
        return f"error: {error}"

    expires_at = payload["expiresAt"][:16].replace("T", " ") + " UTC"
    text = f"Вход в дашборд. Ссылка одноразовая, действует до {expires_at}."
    sent = json.loads(send_with_buttons(text, [{"text": "Войти", "url": payload["url"]}]))
    if not sent.get("ok"):
        return f"error sending the sign-in link: {sent.get('error')}"
    return f"Sign-in link sent to the owner's chat as a button. Expires at {expires_at}."


if __name__ == "__main__":
    mcp.run()
