"""Put the vault in /opt/data/secondbrain once, point it at trip2g inside compose, and sync it."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

TRIP2G_URL = os.environ.get("TRIP2G_URL", "http://trip2g:8380").rstrip("/")
VAULT = Path(os.environ.get("TRIP2G_VAULT_DIR", "/opt/data/secondbrain"))
SYNC_CMD = os.environ.get("HERMES_SYNC_CMD", "/opt/secondbrain/secondbrain-sync.sh")
DATA_JSON = Path(".obsidian/plugins/trip2g/data.json")


def download_vault():
    token = os.environ["OWNER_TOKEN"]
    req = urllib.request.Request(
        TRIP2G_URL + "/_system/onboarding-vault?name=secondbrain",
        headers={"Authorization": f"Bearer {token}"},
    )
    tmp = Path(tempfile.mkdtemp(dir=VAULT.parent, prefix=".secondbrain-seed-"))
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            (tmp / "vault.zip").write_bytes(resp.read())
        with zipfile.ZipFile(tmp / "vault.zip") as archive:
            archive.extractall(tmp)
        if not (tmp / "secondbrain").is_dir():
            sys.exit("secondbrain-seed: the archive did not unpack to secondbrain/")
        if VAULT.is_dir():
            VAULT.rmdir()
        (tmp / "secondbrain").rename(VAULT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("secondbrain-seed: the vault is in place")


def point_at_trip2g():
    path = VAULT / DATA_JSON
    data = json.loads(path.read_text())
    moved = False
    for entry in data.get("syncDirs", []):
        if entry.get("apiUrl") != TRIP2G_URL:
            entry["apiUrl"] = TRIP2G_URL
            moved = True
    if moved:
        path.write_text(json.dumps(data, indent=2) + "\n")
    print("secondbrain-seed: the vault syncs to " + TRIP2G_URL)


def main():
    if not VAULT.is_dir() or not any(VAULT.iterdir()):
        download_vault()
    point_at_trip2g()
    result = subprocess.run([SYNC_CMD], capture_output=True, text=True)
    print(result.stdout + result.stderr)
    if result.returncode != 0 or "Failed to fetch" in result.stdout + result.stderr:
        sys.exit(f"secondbrain-seed: the sync did not reach {TRIP2G_URL} (exit {result.returncode})")
    print("secondbrain-seed: the vault is synced")


if __name__ == "__main__":
    main()
