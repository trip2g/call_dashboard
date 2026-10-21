"""write_note writes the exact bytes at the exact path, syncs in the same call,
refuses to replace an existing note unless asked, refuses a path that leaves
the vault, and carries a note's frontmatter through a body-only overwrite."""

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
        "echo 'wiki/topic.md → https://calls.example/wiki/topic'\n"
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
    return load(SERVER, "secondbrain_mcp_under_test")


def synced(vault):
    log = vault.parent.parent / "sync.log"
    return log.read_text().count("ran") if log.exists() else 0


def test_the_tool_is_registered_with_the_arguments_a_note_needs(server):
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert "write_note" in tools

    schema = tools["write_note"].input_schema
    assert sorted(schema["required"]) == ["content", "path"]
    assert schema["properties"]["path"]["type"] == "string"
    assert schema["properties"]["content"]["type"] == "string"
    assert schema["properties"]["overwrite"] == {
        "default": False, "title": "Overwrite", "type": "boolean"
    }
    assert schema["properties"]["override_frontmatter"] == {
        "default": False, "title": "Override Frontmatter", "type": "boolean"
    }


def test_a_write_lands_on_disk_verbatim_and_is_published_in_the_same_call(server, vault):
    out = server.write_note("kb-e2e-04ca487b.md", "kb-e2e-04ca487b")

    assert (vault / "kb-e2e-04ca487b.md").read_text() == "kb-e2e-04ca487b\n"
    assert synced(vault) == 1
    assert "https://calls.example/wiki/topic" in out


def test_the_md_extension_is_added_and_folders_are_created(server, vault):
    server.write_note("wiki/nested/topic", "# Topic\n\nBody with `code` and no stamp.\n")

    note = vault / "wiki" / "nested" / "topic.md"
    assert note.read_text() == "# Topic\n\nBody with `code` and no stamp.\n"


def test_an_existing_note_is_refused_and_left_exactly_as_it_was(server, vault):
    (vault / "wiki").mkdir()
    (vault / "wiki" / "topic.md").write_text("first\n")

    out = server.write_note("wiki/topic", "second")

    assert (vault / "wiki" / "topic.md").read_text() == "first\n"
    assert "already exists" in out
    assert "`log`" in out
    assert synced(vault) == 0


def test_overwrite_is_the_one_way_past_an_existing_note(server, vault):
    (vault / "wiki").mkdir()
    (vault / "wiki" / "topic.md").write_text("first\n")

    server.write_note("wiki/topic", "second", overwrite=True)

    assert (vault / "wiki" / "topic.md").read_text() == "second\n"
    assert synced(vault) == 1


@pytest.mark.parametrize("path", [
    "../escape.md",
    "wiki/../../escape.md",
    "/etc/passwd",
    "   ",
])
def test_a_path_that_leaves_the_vault_is_refused_before_anything_is_written(
    server, vault, path
):
    out = server.write_note(path, "content")

    assert "secondbrainhelper:" in out
    assert synced(vault) == 0
    assert list(vault.rglob("*.md")) == []


def test_an_underscore_path_is_no_longer_refused(server, vault):
    out = server.write_note("_notes/thought.md", "content")

    assert "secondbrainhelper:" not in out
    assert (vault / "_notes" / "thought.md").read_text() == "content\n"


def test_the_existing_note_refusal_still_guards_an_underscore_path(server, vault):
    (vault / "_about.md").write_text("first\n")

    out = server.write_note("_about.md", "second")

    assert (vault / "_about.md").read_text() == "first\n"
    assert "already exists" in out
    assert synced(vault) == 0

    server.write_note("_about.md", "second", overwrite=True)
    assert (vault / "_about.md").read_text() == "second\n"


def test_write_note_preserves_frontmatter_by_default(server, vault):
    note = vault / "_about.md"
    note.write_text("---\nowner_name: olga\n---\n# Old body\n")

    server.write_note("_about.md", "# New body\n", overwrite=True)

    text = note.read_text()
    assert text.startswith("---\nowner_name: olga\n---\n")
    assert text.endswith("# New body\n")


def test_write_note_override_frontmatter_replaces_the_whole_file(server, vault):
    note = vault / "_about.md"
    note.write_text("---\nowner_name: olga\n---\n# Old body\n")

    server.write_note("_about.md", "# New body\n", overwrite=True, override_frontmatter=True)

    assert note.read_text() == "# New body\n"


def test_an_overwrite_whose_content_brings_its_own_frontmatter_is_refused(server, vault):
    note = vault / "goals" / "launch.md"
    note.parent.mkdir()
    old = '---\noutcome: ""\n---\n# Launch\n'
    note.write_text(old)

    out = server.write_note("goals/launch", "---\noutcome: confirmed\n---\n# Launch\n", overwrite=True)

    assert note.read_text() == old
    assert "secondbrainhelper:" in out
    assert "override_frontmatter=true" in out
    assert "without a frontmatter block" in out
    assert synced(vault) == 0


def test_an_overwrite_with_a_body_only_keeps_the_old_frontmatter(server, vault):
    note = vault / "goals" / "launch.md"
    note.parent.mkdir()
    note.write_text('---\noutcome: ""\n---\n# Launch\n')

    server.write_note("goals/launch", "# Launch, rewritten\n", overwrite=True)

    assert note.read_text() == '---\noutcome: ""\n---\n# Launch, rewritten\n'
    assert synced(vault) == 1


def test_override_frontmatter_takes_the_new_block_whole(server, vault):
    note = vault / "goals" / "launch.md"
    note.parent.mkdir()
    note.write_text('---\noutcome: ""\n---\n# Launch\n')

    server.write_note(
        "goals/launch", "---\noutcome: confirmed\n---\n# Launch\n",
        overwrite=True, override_frontmatter=True,
    )

    assert note.read_text() == "---\noutcome: confirmed\n---\n# Launch\n"
    assert synced(vault) == 1


def test_a_new_note_with_frontmatter_is_written_as_given(server, vault):
    server.write_note("goals/launch", "---\noutcome: confirmed\n---\n# Launch\n")

    assert (vault / "goals" / "launch.md").read_text() == "---\noutcome: confirmed\n---\n# Launch\n"
    assert synced(vault) == 1


def test_the_helper_write_command_stands_on_its_own(vault):
    helper = load(HELPER, "secondbrainhelper_under_test")
    helper.main(["write", "inbox/raw", "note body", "--no-sync"])

    assert (vault / "inbox" / "raw.md").read_text() == "note body\n"
    assert synced(vault) == 0


def test_a_page_with_a_route_is_refused_by_log_and_left_exactly_as_it_was(server, vault):
    page = "---\ntitle: Главная\nroute: calls.example/\n---\n\n# Один ИИ‑ассистент на всю команду.\n"
    (vault / "site").mkdir()
    (vault / "site" / "index.md").write_text(page)

    out = server.log("site/index", "[[2026-09-18]] 13:44 — cron для заявок")

    assert (vault / "site" / "index.md").read_text() == page
    assert "secondbrainhelper:" in out
    assert "route" in out
    assert not (vault / "_notes.md").exists()


def test_a_note_without_a_route_still_takes_a_log_line(server, vault, monkeypatch):
    monkeypatch.setenv("HERMES_TIMEZONE", "Europe/Moscow")
    (vault / "topics").mkdir()
    (vault / "topics" / "Сайт site.md").write_text("---\nfree: true\n---\n\nСайт агентства.\n")

    out = server.log("topics/Сайт site", "cron для заявок")

    assert "secondbrainhelper:" not in out
    assert "cron для заявок" in (vault / "topics" / "Сайт site.md").read_text()
