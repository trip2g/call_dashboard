#!/usr/bin/env node
// Amanu on_stop hook: one meeting folder -> <vault>/transcripts/<YYYY-MM-DD>-<id>.md,
// then trip2g-sync from the vault root.
//
// Lives in <vault>/.obsidian/plugins/trip2g/ next to trip2g-sync.mjs; the vault root is
// three levels up from this file. Amanu passes the meeting folder as the last argument
// (macOS: appended to the shell command; Windows: "{session}") and starts the hook with
// the meeting folder as cwd, so nothing here relies on cwd.
//
//   node amanu-to-trip2g.mjs <meeting-folder> [--no-sync] [--vault <dir>]

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const args = { sync: true, vault: path.resolve(here, "..", "..", ".."), session: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--no-sync") args.sync = false;
    else if (argv[i] === "--vault") args.vault = path.resolve(argv[++i]);
    else args.session = path.resolve(argv[i]);
  }
  if (!args.session) throw new Error("usage: amanu-to-trip2g.mjs <meeting-folder> [--no-sync] [--vault <dir>]");
  return args;
}

function readJSON(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (err) {
    if (err.code === "ENOENT") return fallback;
    throw new Error(`${path.basename(file)}: ${err.message}`);
  }
}

// "[1:02:03]" / "[12:34]" -> seconds
function seconds(stamp) {
  return stamp.split(":").map(Number).reduce((acc, n) => acc * 60 + n, 0);
}

// Krisp style: total minutes, so a 109-minute call reads 109:00, which the calls roles accept.
function mmss(total) {
  const m = Math.floor(total / 60);
  const s = Math.floor(total % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// Amanu writes `**[MM:SS] Name:** text`; a turn may continue on following lines until the
// next header or a blank line.
const TURN_RE = /^\*\*\[(\d{1,2}(?::\d{2}){1,2})\] (.+?):\*\*\s*(.*)$/;

function parseTranscript(md) {
  const turns = [];
  let current = null;
  for (const line of md.split(/\r?\n/)) {
    const m = line.match(TURN_RE);
    if (m) {
      current = { at: seconds(m[1]), name: m[2].trim(), text: m[3].trim() };
      turns.push(current);
    } else if (current && line.trim()) {
      current.text += " " + line.trim();
    } else if (!line.trim()) {
      current = null;
    }
  }
  return turns;
}

// speakers.json maps raw labels ("me", "them A") to names. transcript.md prints the name
// when there is one, so undo it: the label stays the label, the name becomes a hint.
function speakerMaps(speakers) {
  const byName = new Map();
  const hints = {};
  for (const [label, entry] of Object.entries(speakers?.speakers ?? {})) {
    if (!entry?.name) continue;
    byName.set(entry.name, label);
    hints[label] = { name: entry.name, source: entry.source, confidence: entry.confidence ?? null };
  }
  return { byName, hints };
}

function yamlStr(s) {
  return JSON.stringify(String(s));
}

function localDate(iso) {
  const d = iso ? new Date(iso) : new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// The kept recording, as a vault-relative path for `![[...]]`, or null. Amanu keeps one
// stereo audio.m4a when keep_audio is on (an import keeps its normalized source.m4a); with
// keep_audio off the audio is gone by the time this hook runs.
function audioEmbed(session, meta, vault) {
  const named = Object.values(meta.files ?? {}).filter((f) => /\.(m4a|mp3)$/i.test(f));
  const candidates = [...new Set(["audio.m4a", ...named])];
  const found = candidates.map((f) => path.join(session, f)).find((f) => fs.existsSync(f));
  if (!found) return null;
  const rel = path.relative(vault, found);
  if (rel.startsWith("..") || path.isAbsolute(rel)) return null; // not inside the vault: nothing to upload
  return rel.split(path.sep).join("/");
}

function render({ session, meta, turns, hints, engine, audio }) {
  const date = localDate(meta.started);
  const id = createHash("sha256").update(path.basename(session)).digest("hex").slice(0, 8);
  const labels = [...new Set(turns.map((t) => t.label))];
  const fm = [
    "---",
    `title: ${yamlStr(meta.title ? `${meta.title} ${date}` : `Созвон ${date}`)}`,
    "type: transcript",
    // _layouts/calls/transcript.html: player + clickable timecodes.
    "layout: calls/transcript",
    `date: ${date}`,
    `duration: ${mmss(meta.duration_seconds ?? 0)}`,
    // The call page (trip2g/call_dashboard, _layouts/calls/call.html) reads whole minutes.
    `duration_min: ${Math.round((meta.duration_seconds ?? 0) / 60)}`,
    "source: amanu",
    `engine: ${yamlStr(engine)}`,
    `amanu_session: ${yamlStr(path.basename(session))}`,
    `labels: [${labels.map(yamlStr).join(", ")}]`,
    "timecodes: true",
  ];
  const hinted = Object.entries(hints);
  if (hinted.length) {
    fm.push("speakers_hint:");
    for (const [label, h] of hinted) {
      fm.push(`  ${yamlStr(label)}: { name: ${yamlStr(h.name)}, source: ${yamlStr(h.source)}, confidence: ${yamlStr(h.confidence ?? "")} }`);
    }
  }
  if (audio) fm.push(`audio: ${yamlStr(audio)}`);
  fm.push("---", "");
  // The embed makes trip2g-sync upload the recording and the page render a player.
  if (audio) fm.push(`![[${audio}]]`, "");
  const body = turns.map((t) => `${t.label} | ${mmss(t.at)}\n${t.text}\n`).join("\n");
  return { name: `${date}-${id}.md`, text: fm.join("\n") + body };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const log = (msg) => {
    const line = `${new Date().toISOString()} amanu-to-trip2g: ${msg}\n`;
    process.stderr.write(line);
    try { fs.appendFileSync(path.join(args.session, "trip2g.log"), line); } catch {}
  };
  try {
    const md = fs.readFileSync(path.join(args.session, "transcript.md"), "utf8");
    const meta = readJSON(path.join(args.session, "meta.json"), {});
    const speakers = readJSON(path.join(args.session, "speakers.json"), null);
    const transcript = readJSON(path.join(args.session, "transcript.json"), {});
    const { byName, hints } = speakerMaps(speakers);

    const turns = parseTranscript(md).map((t) => ({ ...t, label: byName.get(t.name) ?? t.name }));
    if (!turns.length) throw new Error("no `**[MM:SS] Name:**` lines in transcript.md");

    const engine = [transcript.engine, transcript.model].filter(Boolean).join(" / ") || "unknown";
    const audio = audioEmbed(args.session, meta, args.vault);
    if (!audio) log("no audio inside the vault (keep_audio off?) — transcript only");
    const out = render({ session: args.session, meta, turns, hints, engine, audio });
    const dir = path.join(args.vault, "transcripts");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, out.name), out.text);
    log(`wrote transcripts/${out.name} (${turns.length} turns)`);

    if (args.sync) {
      const sync = path.join(args.vault, ".obsidian", "plugins", "trip2g", "trip2g-sync.mjs");
      const res = spawnSync(process.execPath, [sync, "--folder", "."], { cwd: args.vault, encoding: "utf8" });
      if (res.stdout) log(`sync: ${res.stdout.trim()}`);
      if (res.stderr) log(`sync stderr: ${res.stderr.trim()}`);
      if (res.status !== 0) throw new Error(`trip2g-sync exited ${res.status ?? res.error}`);
      log("sync done");
    }
  } catch (err) {
    log(`failed: ${err.message}`);
    process.exit(1);
  }
}

main();
