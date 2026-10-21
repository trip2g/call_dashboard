---
name: calls
description: The owner's recorded calls and the long-running threads they belong to live in the vault (MCP server `vault`). Use whenever the owner asks about a call, a person they talked to, what was decided, what is still open, or how a thread is going. Every answer about a call or a thread ends with its dashboard link.
version: 1.0.0
---

# Calls and threads

The owner records calls. Each call becomes notes in the vault, which you reach
through the `vault` MCP server (`search`, `note_html`, `expand`):

| Folder | What it holds |
|---|---|
| `transcripts/` | The verbatim transcript, `Label \| MM:SS` lines. File name `YYYY-MM-DD-<id>.md` |
| `calls/<id>.md` | The review: who spoke (`speakers`), the agenda (first line of the body), a category guess. `assumed: true` means nobody has checked it yet |
| `topics/<id>.md` | A short summary and the topics with timecodes |
| `call_edits/<id>.md` | The owner's corrections from the call page. `verified:` lists what the owner confirmed |
| `threads/<slug>.md` | A long-running thread: a client, a supplier, a project. `## Хронология` has one line per call, `## Открытые обязательства` what is still owed |
| `people/` | One note per person |

The call id is the six hex characters at the end of the transcript's file
name, and the file name of its review.

## Answering

1. Find the notes with `search` (a name, a topic, a date, an id), then read
   them with `note_html`. Answer from the notes only. If the notes do not say,
   say so; never fill a gap from memory.
2. A review with `assumed: true` and no `call_edits/<id>.md` is a guess the
   owner has not checked. Say so when you rely on who spoke or on the category.
3. When the owner's edits name a speaker differently from the review, the
   edits win.
4. A question about how a relationship or a project is going is a thread
   question: read the thread note and walk its chronology, newest last.

## Links — always

Every answer that is about a call ends with that call's page:

    {PUBLIC_URL}/call#<id>

Every answer that is about a thread ends with the threads page:

    {PUBLIC_URL}/threads

`{PUBLIC_URL}` is the vault's web address from your instructions. Put the
link on its own line as a bare URL, never inside a markdown link: Telegram
drops a link whose address it does not accept, such as `localhost`, and the
owner is left with no link at all. An answer that covers several calls lists
each call's link. The owner checks and corrects calls on that page, so the link is the point of
the answer, not decoration.

## What you do not do

- Do not edit `transcripts/`, `calls/`, `topics/`, `call_edits/`, `threads/`
  or `roles/`. The review, the topic map and the chronology lines are written
  by the vault's own roles; corrections are made on the call page.
- Other notes the owner asks you to keep, you save with the `secondbrain`
  tools: `write_note` for a new note, `log` to add a line to one, `daily` for
  the journal. Never through GraphQL.
- A sign-in link goes out only through `signin_link`, as a button. Never type
  one into a reply.
- Do not message anyone but the owner.

## The new-call message

A scheduled script (`calls_notify.py`) sends the owner one message per new
review with the call's link. You do not send it yourself. If the owner replies
to it, the call it names is the one they mean.
