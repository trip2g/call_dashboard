---
description: "call_edits/<id>.md with all four marks verified -> one chronology line in each thread the owner picked"
fleet_id: codex
tools: [read_note, patch_note]
read_patterns: ["call_edits/**", "calls/**", "topics/**", "transcripts/**", "threads/**", "people/**"]
write_patterns: ["threads/**"]
mode: change
trigger_on: [create, update]
trigger_include: ["call_edits/**"]
for_each: changed_files
max_depth: 2
concurrency: queue_one
retries: 0
max_steps: 12
max_tokens: 60000
---
The owner has checked a call on the call page. The page saved the owner's
answers in this edits note:

Edits note: `{{ change_file.Path }}`

```
{{ change_file.Content }}
```

## Step 1. Is the call fully verified?

`verified:` in the frontmatter must list all four of `speakers`, `category`,
`threads` and `topics`. If any is missing, the owner is still checking: call
`finish` with `not verified <id>` and write nothing. If `threads:` is empty,
call `finish` with `no threads <id>` and write nothing.

## Step 2. Read what the call said

The call id is `call:` in the frontmatter. Read `calls/<id>.md` (the review),
`topics/<id>.md` (the summary and topics) and the transcript named by
`transcript:` in the review. The owner's corrections win over the review: a
speaker in the edits note's `speakers:` map replaces the review's guess, and
`outcome:` — when it is not empty — is the owner's own words for what was
decided and what stays open.

## Step 3. One line per thread

For each path in `threads:`, read the thread note. If its `## Хронология`
section already has a line that links `calls/<id>`, skip that thread: the line
is there, and a second one would make the thread contradict itself.

Otherwise add one line at the end of the `## Хронология` list with
`patch_note`. `find` is the last line of that list exactly as it is, followed
by a blank line and `## ` — the start of the next heading. `replace` is that
last line, a newline, the new line, a blank line and `## `. Never change a line
that is already there.

Another run may be adding the same line at the same moment. If `patch_note`
says `find` does not match, the thread has changed under you: read it again
and repeat this step for it from the start.

The new line, in the language of the call:

```
- [[calls/<id>|<YYYY-MM-DD>]]: <what happened in this call for this thread, one or two sentences>. Решили: <what was decided>. Открыто: <what stays open>.
```

- The date is the one in the transcript's file name.
- Leave out `Решили:` or `Открыто:` when the call had nothing of that kind.
- A person the line names links to their note:
  `[[people/<name>|<name as written>]]`, only for a note that exists.
- Write only what the call, the topics or the owner's outcome say. No advice,
  no guesses about the future.

## Step 4. Finish

Call `finish` with one line per thread: `<thread path>: added` or
`<thread path>: already there`.
