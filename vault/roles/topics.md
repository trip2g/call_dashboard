---
description: "calls/<id>.md (new review) -> topics/<id>.md: summary and a topic map with timecodes"
fleet_id: codex
tools: [read_note, write_note]
read_patterns: ["transcripts/**", "calls/**", "topics/**"]
write_patterns: ["topics/**"]
mode: change
trigger_on: [create]
trigger_include: ["calls/**"]
for_each: changed_files
max_depth: 3
concurrency: queue_one
retries: 1
max_steps: 6
max_tokens: 60000
---
A call has a new review note. Your job is only its topic map: a short summary
and the moments where the subject changes. Small output, no retelling, no
quotes.

Review note: `{{ change_file.Path }}`

```
{{ change_file.Content }}
```

Steps:

1. The call id is the review's file name without `.md`. If `topics/<id>.md`
   exists, call `finish` with `exists <id>` and write nothing.
2. `read_note` the transcript named by `transcript:` in the review. Lines are
   `Label | MM:SS`, then what was said.
3. Split the call into topics: only real changes of subject; small talk at the
   start belongs to the first topic. A topic line states its takeaway, not a
   label («Цена с доставкой на два адреса», not «Цены»).
4. Write `topics/<id>.md`, everything in the language of the call:

```
---
title: "<the review's title>"
type: topics
---
<2-3 sentences: what was decided and what is next. Use the names from the
review's speakers map, never the raw labels.>

## Темы

MM:SS | <first topic>
MM:SS | <next topic>
```

Every timecode is copied from a transcript line, never invented or rounded.
The first one is the transcript's first timecode, and they strictly increase.

Then call `finish` with `topics <id>: <number of topics>`.
