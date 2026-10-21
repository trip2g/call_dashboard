#!/usr/bin/env python3
"""Daily-note, log-note and note-writing CLI for the Hermes vault.

  daily "<text>"                              append a HH:MM entry to today's daily note
  log <file> "<text>"                         append a HH:MM line under today's ### [[date]] section
  write <file> "<text>"                       write a whole note at a vault path
  index <file> <note>                         add one link to an index note, once
  upsert-frontmatter <file> <field> <value>   set one YAML frontmatter field, body untouched
  publish <file>                              set free: true, body untouched
"""
import argparse
import io
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from ruamel.yaml import YAML

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9 not supported by Hermes
    ZoneInfo = None  # type: ignore


def resolve_now():
    """Current timezone-aware datetime in the client's zone."""
    try:
        _install_dir = os.environ.get("INSTALL_DIR", "/opt/hermes")
        if _install_dir not in sys.path:
            sys.path.insert(0, _install_dir)
        from hermes_time import now  # type: ignore
        return now()
    except Exception:
        tz = os.environ.get("HERMES_TIMEZONE", "").strip()
        if tz and ZoneInfo is not None:
            try:
                return datetime.now(ZoneInfo(tz))
            except Exception as exc:
                sys.stderr.write(
                    f"secondbrainhelper: invalid HERMES_TIMEZONE={tz!r}: {exc}\n")
        if not tz:
            sys.stderr.write("secondbrainhelper: TZ not set, using UTC\n")
        return datetime.now().astimezone()


def build_parser():
    p = argparse.ArgumentParser(prog="secondbrainhelper.py")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("daily", help="append a HH:MM entry to today's daily note")
    d.add_argument("text")

    lg = sub.add_parser("log", help="append under today's ### [[date]] section")
    lg.add_argument("file")
    lg.add_argument("text")

    w = sub.add_parser("write", help="write a whole note at a vault path")
    w.add_argument("file")
    w.add_argument("text")
    w.add_argument("--overwrite", action="store_true",
                   help="replace an existing note instead of refusing")
    w.add_argument("--override-frontmatter", action="store_true",
                   help="replace the note's frontmatter too, instead of carrying it through untouched")

    uf = sub.add_parser("upsert-frontmatter",
                        help="set one YAML frontmatter field, body untouched")
    uf.add_argument("file")
    uf.add_argument("field")
    uf.add_argument("value")

    ix = sub.add_parser("index", help="add one link to an index note, once")
    ix.add_argument("file", help="the index note's vault path")
    ix.add_argument("note", help="the vault path of the note to link")

    pub = sub.add_parser("publish",
                         help="set free: true, the boolean the store reads, body untouched")
    pub.add_argument("file")

    for sp in (d, lg, w, uf, ix, pub):
        sp.add_argument("--vault", default=os.environ.get(
            "HERMES_HOME", "/opt/data") + "/secondbrain")
        sp.add_argument("--context", type=int, default=15)
        grp = sp.add_mutually_exclusive_group()
        grp.add_argument("--sync", action="store_true",
                         help="run sync synchronously and print URLs")
        grp.add_argument("--no-sync", action="store_true",
                         help="skip vault sync entirely")
    return p


def atomic_write(path: Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".sbh-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def tail_lines(path: Path, n: int) -> str:
    path = Path(path)
    text = path.read_text() if path.exists() else ""
    lines = text.splitlines()
    return "\n".join(lines[-n:]) if n > 0 else ""


def _timestamp(now) -> str:
    return now.strftime("%H:%M")


def _stamp_block(text: str, now) -> str:
    """Prefix the first line with HH:MM, leave the rest verbatim.

    A literal ``\\n`` (backslash-n) in the argument is treated as a line
    break: when the agent calls this through a shell, double-quoted ``\\n``
    arrives as two characters, not a newline. Normalizing here makes the
    documented `daily "user: msg\\nnote"` pattern produce two lines on any shell.
    """
    text = text.replace("\\n", "\n")
    lines = text.splitlines() or [""]
    lines[0] = f"{_timestamp(now)} {lines[0]}"
    return "\n".join(lines)


def _ensure_daily_index(vault: Path, day: str) -> None:
    idx = vault / "daily" / "_index.md"
    if not idx.exists():
        atomic_write(idx, "- [[_index|Home]]\n- [[daily/_index|Daily]]\n\n# Daily\n")
    text = idx.read_text()
    if f"[[{day}]]" in text:
        return
    out, inserted = [], False
    for line in text.splitlines():
        out.append(line)
        if not inserted and line.strip() == "# Daily":
            out.append(f"- [[{day}]]")
            inserted = True
    if not inserted:
        out.append(f"- [[{day}]]")
    atomic_write(idx, "\n".join(out) + "\n")


NOTES_INDEX = "_notes.md"

_yaml = YAML(typ="safe", pure=True)
_yaml.default_flow_style = False
_yaml.allow_unicode = True
_yaml.representer.sort_base_mapping_type_on_output = False


def _append_under_today(note: Path, entry: str, now, separator: str = "\n\n") -> None:
    """Append a block under today's `### [[date]]` heading, creating it once.

    Assumes today's section, if present, is the last section in the file
    (append-only invariant). A list index passes separator="\n" so its items
    stay one tight list rather than a paragraph each.
    """
    day = now.strftime("%Y-%m-%d")
    header = f"### [[{day}]]"
    existing = note.read_text() if note.exists() else ""
    base = existing.rstrip("\n")
    if header in existing.splitlines():
        atomic_write(note, f"{base}{separator}{entry}\n")
        return
    prefix = (base + "\n\n") if base else ""
    atomic_write(note, f"{prefix}{header}\n\n{entry}\n")


def _index_link(vault: Path, note: Path) -> str:
    rel = note.relative_to(vault)
    return f"[[{rel.as_posix()}|{rel.stem}]]"


def _index_append(vault: Path, index: Path, note: Path, now) -> bool:
    """Put one link to `note` in `index`, once. True when it was added.

    The link carries the note's whole path and shows its name, because two
    folders may hold a note of the same name and only the path says which one
    is meant, while only the name reads as a sentence.
    """
    link = _index_link(vault, note)
    if index.exists() and link in index.read_text():
        return False
    _append_under_today(index, f"- {link}", now, separator="\n")
    return True


def _log_topic(vault: Path, note: Path, now) -> None:
    """Record a subject note in the vault's topic index, once.

    Both writers, `write` and `log`, come through this helper, so the index
    lists the notes of both. Daily notes keep their own index, and a name
    starting with "_" is bookkeeping rather than a subject.
    """
    rel = note.relative_to(vault)
    if rel.parts[0] == "daily" or rel.name.startswith("_"):
        return
    _index_append(vault, vault / NOTES_INDEX, note, now)


def _tz_label(now) -> str:
    """IANA timezone name for the daily-note frontmatter (tracks movements)."""
    tz = os.environ.get("HERMES_TIMEZONE", "").strip()
    if tz:
        return tz
    return getattr(now.tzinfo, "key", None) or now.strftime("%z") or "UTC"


def cmd_daily(args, now) -> Path:
    vault = Path(args.vault)
    day = now.strftime("%Y-%m-%d")
    note = vault / "daily" / f"{day}.md"
    entry = _stamp_block(args.text, now)
    if not note.exists():
        frontmatter = f"---\ntimezone: {_tz_label(now)}\n---\n"
        header = f"- [[_index|Home]]\n- [[daily/_index|Daily]]\n\n# {day}\n"
        atomic_write(note, f"{frontmatter}{header}\n{entry}\n")
    else:
        existing = note.read_text().rstrip("\n")
        atomic_write(note, f"{existing}\n\n{entry}\n")
    _ensure_daily_index(vault, day)
    return note


def _resolve_note_path(vault: Path, name: str) -> Path:
    if not name.endswith(".md"):
        name = name + ".md"
    return vault / name


def cmd_log(args, now) -> Path:
    """Append a timestamped entry under today's ### [[date]] section.

    A note with a `route` in its frontmatter is a page whose body is served to
    whoever opens that address, so it is refused.

    Assumes today's section, if present, is the last section in the file
    (append-only invariant). Manual edits that add content after today's
    section will cause entries to be appended after that content instead.
    """
    vault = Path(args.vault)
    note = _resolve_note_path(vault, args.file)
    if note.exists() and "route" in split_frontmatter(note.read_text())[0]:
        refuse(
            str(note.relative_to(vault)) + " is a page served at its `route`, and"
            " its body is what visitors read. A dated line does not belong there;"
            " log it into a note about the subject instead."
        )
    entry = _stamp_block(args.text, now)

    _append_under_today(note, entry, now)
    _log_topic(vault, note, now)
    return note


def refuse(message: str):
    sys.stderr.write("secondbrainhelper: " + message + "\n")
    raise SystemExit(2)


def _vault_path(vault: Path, name: str) -> Path:
    """Resolve a path inside the vault, refusing anything that leaves it."""
    raw = name.strip()
    if not raw:
        refuse("a note needs a path, like wiki/topic.md.")
    parts = PurePosixPath(raw).parts
    if raw.startswith("/") or ".." in parts:
        refuse(
            repr(raw) + " leaves the vault; give a path relative to it, like wiki/topic.md."
        )
    return _resolve_note_path(vault, raw)


def cmd_write(args, now) -> Path:
    """Write a whole note at a vault path, refusing to clobber one that is there.

    Append-only is the vault's rule and `log` is the tool for it, so an existing
    note is a refusal naming that tool rather than a silent replacement. The
    caller says --overwrite when the user asked for the note to be replaced.

    By default the note's own frontmatter, if it has one, rides through
    untouched and args.text becomes the body, so a plain write cannot erase
    the note's metadata. --override-frontmatter is the one way past that: the
    whole file becomes args.text, frontmatter included.

    An overwrite whose args.text opens with a frontmatter block of its own is
    refused without that flag: carried through, the old block would sit first
    and the new one under it as body, and trip2g reads only the first.
    """
    vault = Path(args.vault)
    note = _vault_path(vault, args.file)
    if note.exists() and not args.overwrite:
        refuse(
            str(note.relative_to(vault)) + " already exists. Add to it with `log`, or"
            " pass --overwrite when the user asked to replace what it says."
        )
    text = args.text.rstrip("\n") + "\n"
    if note.exists() and not args.override_frontmatter:
        if frontmatter_block(text):
            refuse(
                str(note.relative_to(vault)) + " exists and the new text opens with a"
                " frontmatter block; an overwrite keeps the note's own frontmatter, so"
                " this block would land in the body and be ignored. Pass"
                " override_frontmatter=true to replace the frontmatter, or send the"
                " body without a frontmatter block to keep the existing one."
            )
        text = frontmatter_block(note.read_text()) + text
    atomic_write(note, text)
    _log_topic(vault, note, now)
    return note


def cmd_index(args, now) -> Path:
    """Add one link to an index note, once, under today's heading.

    An index is a note whose body is a list of links to other notes, and it is
    written this way rather than with `write` so that adding a line can never
    replace what is already there. A link that is in the file already is not
    added a second time and nothing is written.
    """
    vault = Path(args.vault)
    index = _vault_path(vault, args.file)
    note = _vault_path(vault, args.note)
    if not note.exists():
        refuse(
            str(note.relative_to(vault)) + " is not in the vault, so a link to it"
            " would be dead. Write the note first, then index it."
        )
    _index_append(vault, index, note, now)
    return index


def _frontmatter_fence_end(lines: list) -> int:
    """Index of the line closing the note's opening frontmatter fence, or -1.

    Only "---" as the very first line opens a block; only a later "---" alone
    on its own line closes it. Anything else means the note has no
    frontmatter at all.
    """
    if not lines or lines[0].rstrip("\n") != "---":
        return -1
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n") == "---":
            return i
    return -1


def frontmatter_block(content: str) -> str:
    """The note's frontmatter block verbatim, fences included, or "" if it has none.

    Unlike split_frontmatter, this never hands the block to the YAML parser —
    it is for carrying an existing block through a write byte for byte, not for
    reading it.
    """
    lines = content.splitlines(keepends=True)
    end = _frontmatter_fence_end(lines)
    return "".join(lines[:end + 1]) if end >= 0 else ""


def split_frontmatter(content: str) -> tuple:
    """Split a note into (frontmatter dict, body), the body untouched.

    Only the fenced block at the very top — opening "---" as the first line,
    closing "---" alone on its own line — is ever handed to the YAML parser.
    Everything from the closing fence onward is sliced out as plain text and
    never parsed, so a note's prose can never be reformatted, re-escaped or
    reordered by round-tripping through the parser. A file with no such block,
    or a "---" with nothing closing it, is treated as having no frontmatter at
    all: the whole thing is the body.
    """
    lines = content.splitlines(keepends=True)
    end = _frontmatter_fence_end(lines)
    if end < 0:
        return {}, content
    data = _yaml.load("".join(lines[1:end])) or {}
    if not isinstance(data, dict):
        data = {}
    return data, "".join(lines[end + 1:])


def render_frontmatter(data: dict) -> str:
    """Re-emit a frontmatter block, letting the YAML library quote the values."""
    buf = io.StringIO()
    _yaml.dump(data, buf)
    return f"---\n{buf.getvalue()}---\n"


def cmd_upsert_frontmatter(args) -> Path:
    """Set one frontmatter field on a vault note; every other field, and the
    whole body, come back exactly as they were.

    file follows write's vault-relative rule: relative to the vault root,
    ".md" added when missing, refused if it leaves the vault.
    """
    vault = Path(args.vault)
    note = _vault_path(vault, args.file)
    content = note.read_text() if note.exists() else ""
    data, body = split_frontmatter(content)
    data[args.field] = args.value
    atomic_write(note, render_frontmatter(data) + body)
    return note


def cmd_publish(args) -> Path:
    """Set the note's `free` flag to a YAML boolean, body untouched.

    Separate from upsert-frontmatter because that one takes its value off the
    command line, where every value is a string: it writes `free: 'true'`, and
    the store reads `free` by comparing against a boolean, so the quoted form
    leaves the note private while reporting success.
    """
    vault = Path(args.vault)
    note = _vault_path(vault, args.file)
    content = note.read_text() if note.exists() else ""
    data, body = split_frontmatter(content)
    data["free"] = True
    atomic_write(note, render_frontmatter(data) + body)
    return note


def _sync_cmd() -> str:
    return os.environ.get("HERMES_SYNC_CMD", "/opt/secondbrain/secondbrain-sync.sh")


def run_sync(blocking: bool) -> str:
    """Run the vault sync. Returns printable URL lines when blocking."""
    cmd = _sync_cmd()
    if blocking:
        try:
            proc = subprocess.run([cmd], capture_output=True, text=True, timeout=120)
        except Exception as exc:
            sys.stderr.write(f"secondbrainhelper: sync failed: {exc}\n")
            return ""
        if proc.returncode != 0:
            sys.stderr.write(f"secondbrainhelper: sync exited {proc.returncode}\n")
        urls = [ln for ln in proc.stdout.splitlines() if "->" in ln or "→" in ln]
        return "\n".join(urls)
    try:
        subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception as exc:
        sys.stderr.write(f"secondbrainhelper: async sync failed to start: {exc}\n")
    return ""


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "daily":
        target = cmd_daily(args, resolve_now())
    elif args.command == "log":
        target = cmd_log(args, resolve_now())
    elif args.command == "write":
        target = cmd_write(args, resolve_now())
    elif args.command == "index":
        target = cmd_index(args, resolve_now())
    elif args.command == "upsert-frontmatter":
        target = cmd_upsert_frontmatter(args)
    elif args.command == "publish":
        target = cmd_publish(args)
    else:
        raise SystemExit(2)

    url_lines = ""
    if not args.no_sync:
        url_lines = run_sync(blocking=args.sync)

    sys.stdout.write(tail_lines(target, args.context) + "\n")
    if url_lines:
        sys.stdout.write(url_lines + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
