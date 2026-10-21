"""Tests for upsert_frontmatter_field — setting one YAML frontmatter key
without disturbing anything else in the note.

A note's prose must never be reformatted by a round trip through a YAML
parser, so the proofs here are:

  (a) a file with no frontmatter gains a well-formed block;
  (b) an existing block gains a new key, or has one replaced, with every
      other key in it surviving unchanged;
  (c) a multi-line value round-trips
      through the YAML dumper and re-parses back to the same string;
  (d) the body, in every case, comes back byte for byte;
  (e) a path outside the vault is refused, the same as write_note; a
      leading underscore is not refused, the same as write_note.

"""

import asyncio
import importlib.util
import os
from pathlib import Path

import pytest
from ruamel.yaml import YAML

_yaml = YAML(typ="safe", pure=True)

SECONDBRAIN = Path(__file__).resolve().parent.parent
HELPER = SECONDBRAIN / "secondbrainhelper.py"
SERVER = SECONDBRAIN / "secondbrain_mcp.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def vault(tmp_path):
    """A throwaway HERMES_HOME whose sync records that it ran and prints a URL."""
    home = tmp_path / "data"
    (home / "secondbrain").mkdir(parents=True)
    sync = tmp_path / "sync.sh"
    sync.write_text(
        "#!/bin/sh\n"
        f'echo ran >> "{tmp_path}/sync.log"\n'
        "echo '_about.md → https://calls.example/_about'\n"
    )
    sync.chmod(0o755)
    os.environ["HERMES_HOME"] = str(home)
    os.environ["HERMES_SYNC_CMD"] = str(sync)
    os.environ["SECONDBRAIN_HELPER"] = str(HELPER)
    yield home / "secondbrain"
    for var in ("HERMES_HOME", "HERMES_SYNC_CMD", "SECONDBRAIN_HELPER"):
        os.environ.pop(var, None)


@pytest.fixture
def server(vault):
    return load(SERVER, "secondbrain_mcp_under_test_frontmatter")


def synced(vault):
    log = vault.parent.parent / "sync.log"
    return log.read_text().count("ran") if log.exists() else 0


def test_the_tool_is_registered_with_the_arguments_it_needs(server):
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert "upsert_frontmatter_field" in tools

    schema = tools["upsert_frontmatter_field"].input_schema
    assert sorted(schema["required"]) == ["field", "file", "value"]
    assert schema["properties"]["file"]["type"] == "string"
    assert schema["properties"]["field"]["type"] == "string"
    assert schema["properties"]["value"]["type"] == "string"


def test_a_file_with_no_frontmatter_gains_one(server, vault):
    note = vault / "_about.md"
    note.write_text("# About\n\nBe direct.\n")

    server.upsert_frontmatter_field("_about.md", "owner_name", "olga")

    text = note.read_text()
    assert text.startswith("---\n")
    body_start = text.index("---\n", 4) + len("---\n")
    assert text[body_start:] == "# About\n\nBe direct.\n"


def test_an_existing_block_gains_a_key_and_keeps_the_others(server, vault):
    note = vault / "_about.md"
    note.write_text("---\ntimezone: UTC\n---\n# About\n\nBe direct.\n")

    server.upsert_frontmatter_field("_about.md", "owner_name", "olga")

    text = note.read_text()
    assert text.endswith("# About\n\nBe direct.\n")
    fm_text = text.split("---\n", 2)[1]
    data = _yaml.load(fm_text)
    assert data == {"timezone": "UTC", "owner_name": "olga"}


def test_an_existing_key_is_replaced_not_duplicated(server, vault):
    note = vault / "_about.md"
    note.write_text("---\nowner_name: old-name\ntimezone: UTC\n---\nBody text.\n")

    server.upsert_frontmatter_field("_about.md", "owner_name", "new-name")

    text = note.read_text()
    fm_text = text.split("---\n", 2)[1]
    data = _yaml.load(fm_text)
    assert data == {"owner_name": "new-name", "timezone": "UTC"}
    assert text.endswith("Body text.\n")


def test_a_multiline_value_round_trips_and_reparses(server, vault):
    note = vault / "_about.md"
    note.write_text("# About\n\nBe direct.\n")
    value = "line one\nline two, with: a colon\nline three"

    server.upsert_frontmatter_field("_about.md", "summary", value)

    text = note.read_text()
    fm_text = text.split("---\n", 2)[1]
    data = _yaml.load(fm_text)
    assert data["summary"] == value
    assert text.endswith("# About\n\nBe direct.\n")


def test_setting_a_field_twice_is_idempotent(server, vault):
    note = vault / "_about.md"
    note.write_text("# About\n\nBe direct.\n")

    server.upsert_frontmatter_field("_about.md", "owner_name", "olga")
    first = note.read_text()
    server.upsert_frontmatter_field("_about.md", "owner_name", "olga")
    second = note.read_text()

    assert first == second


def test_the_body_is_unaffected_when_the_frontmatter_contains_body_like_text(server, vault):
    note = vault / "_about.md"
    body = "# About\n\n---\nthis dashed line is body text, not a fence\n"
    note.write_text("---\ntimezone: UTC\n---\n" + body)

    server.upsert_frontmatter_field("_about.md", "owner_name", "olga")

    text = note.read_text()
    assert text.endswith(body)


@pytest.mark.parametrize("path", [
    "../escape.md",
    "wiki/../../escape.md",
    "/etc/passwd",
    "   ",
])
def test_a_path_outside_the_vault_is_refused(server, vault, path):
    out = server.upsert_frontmatter_field(path, "field", "value")

    assert "secondbrainhelper:" in out
    assert list(vault.rglob("*.md")) == []


def test_an_underscore_path_is_not_refused(server, vault):
    out = server.upsert_frontmatter_field("_about.md", "owner_name", "olga")

    assert "secondbrainhelper:" not in out
    assert (vault / "_about.md").exists()


def test_upsert_publishes_in_the_same_call(server, vault):
    note = vault / "_about.md"
    note.write_text("# About\n\nBe direct.\n")

    out = server.upsert_frontmatter_field("_about.md", "owner_name", "olga")

    assert synced(vault) == 1
    assert "https://calls.example/_about" in out


def test_the_helper_command_stands_on_its_own(vault):
    helper = load(HELPER, "secondbrainhelper_under_test_frontmatter")
    note = vault / "_memories" / "MEMORY.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Memories\n\nfirst entry\n")

    helper.main(["upsert-frontmatter", "_memories/MEMORY.md", "reviewed", "true", "--no-sync"])

    text = note.read_text()
    assert text.endswith("# Memories\n\nfirst entry\n")
    fm_text = text.split("---\n", 2)[1]
    assert _yaml.load(fm_text) == {"reviewed": "true"}
