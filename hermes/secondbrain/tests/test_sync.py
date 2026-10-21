"""The sync tool must never let a failed run read as a report.

The CLI it wraps catches a failed fetch of the server's hashes and carries on
against an empty server, so it prints a plausible summary and exits 0. That
summary counts local notes against nothing: on a store holding 24 notes it
says "Server deleted: 24". A model reading that answers that the notes were
synced, or worse, that the store lost them.

So the tool checks the exit code and the output, and on either it returns a
refusal that says what to do instead.
"""

import importlib.util
import os
from pathlib import Path

import pytest

SECONDBRAIN = Path(__file__).resolve().parent.parent
SERVER = SECONDBRAIN / "secondbrain_mcp.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_sync(tmp_path, body, exit_code=0):
    sync = tmp_path / "sync.sh"
    sync.write_text("#!/bin/sh\n" + body + f"\nexit {exit_code}\n")
    sync.chmod(0o755)
    os.environ["HERMES_SYNC_CMD"] = str(sync)
    return sync


@pytest.fixture(autouse=True)
def clean_env():
    yield
    os.environ.pop("HERMES_SYNC_CMD", None)


def server():
    return load(SERVER, "secondbrain_mcp_under_test_sync")


def test_a_clean_run_is_passed_through(tmp_path):
    write_sync(tmp_path, "echo 'wiki/note.md → https://calls.example/wiki/note'")

    out = server().sync()

    assert "wiki/note.md" in out
    assert not out.startswith("error:")


def test_a_nonzero_exit_is_refused(tmp_path):
    write_sync(tmp_path, "echo 'something went wrong' >&2", exit_code=1)

    out = server().sync()

    assert out.startswith("error:")
    assert "technical support" in out
    assert "something went wrong" in out, "the operator loses the reason"


def test_a_failed_hash_fetch_is_refused_even_though_the_cli_exits_zero(tmp_path):
    # Exactly what a real broken run printed: a summary that looks like a
    # report, a deletion count drawn from a store it never read, and exit 0.
    write_sync(
        tmp_path,
        "echo 'To push: 0'\n"
        "echo 'Server deleted: 24'\n"
        "echo 'Failed to fetch server hashes: HTTP 404: Not Found'",
        exit_code=0,
    )

    out = server().sync()

    assert out.startswith("error:")
    assert "technical support" in out
    assert "Server deleted: N" in out, "the model is not told to discard the counts"


def test_the_refusal_tells_the_model_not_to_claim_the_notes_are_stored(tmp_path):
    write_sync(tmp_path, "echo 'Failed to fetch server hashes: HTTP 404'")

    out = server().sync()

    assert "only on this machine" in out
    assert "Do not retry in a loop." in out


def test_a_missing_sync_command_is_still_an_error(tmp_path):
    os.environ["HERMES_SYNC_CMD"] = str(tmp_path / "nope.sh")

    out = server().sync()

    assert out.startswith("error:")
