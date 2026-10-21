"""Tests for publish_note — the one thing that turns a note's existing link
into one that serves the note.

trip2g decides public access with `pp.Free = pp.RawMeta["free"] == true`, a
comparison against a YAML boolean. That single line is why this tool exists
rather than the model calling upsert_frontmatter_field(file, "free", "true"):
that path takes its value off a command line, where every value is a string,
so the dumper has to quote it or lose it, and `free: 'true'` is not `true`. The
note would stay private while every layer reported success — so the proofs
here are:

  (a) the flag lands as a YAML boolean, not the quoted string that reads as
      private, and the file still parses;
  (b) upsert_frontmatter_field on the same field still writes the string, so
      the two are not accidentally the same call;
  (c) an already-public note stays public rather than gaining a second key;
  (d) every other frontmatter key, and the body, come back untouched;
  (e) a path outside the vault is refused, the same as write_note;
  (f) the sync runs inline, so the link works when the call returns.

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

NOTE = "---\ntitle: A note\ntags:\n  - one\n  - two\n---\n\nBody text.\n\n  indented, and trailing space here: \n"


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
        "echo 'wiki/note.md → https://calls.example/wiki/note'\n"
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
    return load(SERVER, "secondbrain_mcp_under_test_publish")


def synced(vault):
    log = vault.parent.parent / "sync.log"
    return log.read_text().count("ran") if log.exists() else 0


def frontmatter(note):
    return _yaml.load(note.read_text().split("---")[1])


def test_the_tool_is_registered_taking_only_the_file(server):
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert "publish_note" in tools

    schema = tools["publish_note"].input_schema
    assert schema["required"] == ["file"]
    assert schema["properties"]["file"]["type"] == "string"


def test_the_flag_lands_as_a_boolean_not_the_string_that_reads_as_private(server, vault):
    note = vault / "wiki" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE)

    server.publish_note("wiki/note")

    assert frontmatter(note)["free"] is True
    assert "free: true" in note.read_text()


def test_setting_the_same_field_by_hand_still_writes_the_string(server, vault):
    note = vault / "wiki" / "byhand.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE)

    server.upsert_frontmatter_field("wiki/byhand", "free", "true")

    assert frontmatter(note)["free"] == "true"
    assert "free: 'true'" in note.read_text()


def test_publishing_twice_leaves_one_boolean(server, vault):
    note = vault / "wiki" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE)

    server.publish_note("wiki/note")
    server.publish_note("wiki/note")

    assert note.read_text().count("free:") == 1
    assert frontmatter(note)["free"] is True


def test_every_other_key_and_the_body_survive(server, vault):
    note = vault / "wiki" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE)

    server.publish_note("wiki/note")

    data = frontmatter(note)
    assert data["title"] == "A note"
    assert data["tags"] == ["one", "two"]
    assert note.read_text().split("---\n", 2)[2] == NOTE.split("---\n", 2)[2]


def test_a_note_with_no_frontmatter_gains_a_well_formed_block(server, vault):
    note = vault / "wiki" / "bare.md"
    note.parent.mkdir(parents=True)
    note.write_text("Just a body.\n")

    server.publish_note("wiki/bare")

    assert frontmatter(note)["free"] is True
    assert note.read_text().endswith("Just a body.\n")


def test_a_path_that_leaves_the_vault_is_refused(server, vault):
    answer = server.publish_note("../escaped")

    assert "secondbrainhelper:" in answer
    assert list(vault.rglob("*.md")) == []


def test_the_sync_runs_inline_so_the_link_works_on_return(server, vault):
    note = vault / "wiki" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE)

    answer = server.publish_note("wiki/note")

    assert synced(vault) == 1
    assert "https://calls.example/wiki/note" in answer
