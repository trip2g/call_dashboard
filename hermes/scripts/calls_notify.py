import json
import os
import pathlib
import re
import urllib.request

GRAPHQL = os.environ.get("VAULT_GRAPHQL", "http://trip2g:8380/graphql")
API_KEY = os.environ["VAULT_API_KEY"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
STATE = pathlib.Path(os.environ.get("HERMES_HOME", "/opt/data")) / "calls_notify.json"
QUERY = 'query { notePaths(filter: { like: "calls/%" }) { value content } }'


def fetch_reviews():
    body = json.dumps({"query": QUERY}).encode()
    req = urllib.request.Request(GRAPHQL, data=body, headers={"Content-Type": "application/json", "X-API-Key": API_KEY})
    with urllib.request.urlopen(req, timeout=30) as resp:
        answer = json.load(resp)
    if answer.get("errors"):
        raise SystemExit("vault query failed: " + json.dumps(answer["errors"], ensure_ascii=False))
    return answer["data"]["notePaths"]


def frontmatter(content):
    match = re.match(r"---\n(.*?)\n---\n", content, re.S)
    return match.group(1) if match else ""


def field(fm, key):
    match = re.search(r"^" + key + r":\s*\"?(.*?)\"?\s*$", fm, re.M)
    return match.group(1) if match else ""


def unknown_labels(fm):
    block = re.search(r"^speakers_confidence:\n((?:\s+.*\n?)*)", fm, re.M)
    if not block:
        return []
    return re.findall(r"^\s+\"?(.*?)\"?:\s*\"?unknown\"?\s*$", block.group(1), re.M)


def message(note):
    fm = frontmatter(note["content"])
    call_id = pathlib.PurePosixPath(note["value"]).stem
    date = re.search(r"\d{4}-\d{2}-\d{2}", field(fm, "transcript"))
    when = " (" + date.group(0) + ")" if date else ""
    lines = ["Разобрал созвон «" + field(fm, "title") + "»" + when + ".", "Проверьте, кто говорил и о чём: " + PUBLIC_URL + "/call#" + call_id]
    unknown = unknown_labels(fm)
    if unknown:
        lines.append("Не понял, кто: " + ", ".join(unknown) + ".")
    return "\n".join(lines)


def main():
    reviews = [n for n in fetch_reviews() if field(frontmatter(n["content"]), "type") == "review"]
    seen = set(json.loads(STATE.read_text())) if STATE.exists() else None
    fresh = [] if seen is None else [n for n in reviews if n["value"] not in seen]
    STATE.write_text(json.dumps(sorted(n["value"] for n in reviews)))
    print("\n\n".join(message(n) for n in fresh))


main()
