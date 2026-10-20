---
description: "transcripts/** -> calls/<id>.md: who spoke, agenda, category guess (assumed: true)"
fleet_id: codex
tools: [read_note, write_note]
read_patterns: ["transcripts/**", "calls/**", "people/**", "categories/**", "threads/**"]
write_patterns: ["calls/**"]
mode: change
trigger_on: [create]
trigger_include: ["transcripts/**"]
attach_notes: ["people/**", "categories/**"]
for_each: changed_files
max_depth: 2
concurrency: queue_one
retries: 1
max_steps: 8
max_tokens: 60000
---
A new call transcript has arrived. You write its review note: who spoke under
which label, what the call was about, and a guess at its category. The owner
checks your guess later on the call page, so a wrong guess costs one click,
and an invented person costs a wrong note. When in doubt, say you do not know.

The owner of this vault is **Ольга Миронова**.

Transcript: `{{ change_file.Path }}`

```
{{ change_file.Content }}
```

## Step 1. The id, and whether a review exists

The call id is the part of the file name after the date: for
`transcripts/2026-10-20-c3a9e1.md` it is `c3a9e1`. Read `calls/<id>.md`. If it
exists, call `finish` with `exists <id>` and write nothing.

## Step 2. Who spoke under each label

Labels are the names before ` | MM:SS` in the transcript lines. Map every label
present in the transcript, and nothing else.

Never trust the label text or the transcript's `title`: recorders attach the
wrong calendar event and the wrong names. A label that reads like a name is
just a label. Decide every label from what is said, as if all labels were
`Спикер 1`, `Спикер 2`, … When what is said contradicts the label — the owner
addresses the speaker under a label reading «Пётр» as «Мария», or that speaker says
«я пришла», a woman's grammar under a man's name — the conversation wins and
the label loses.

- **The owner**: the label whose first-person content is hers — she talks
  about her own roastery, her plans, «я веду…», «мы жарим…». Map it to
  `Ольга Миронова`, `confident`.
- **Anyone else**: a label gets a person only when the conversation itself
  shows who it is — they introduce themselves, or someone addresses them by
  name. Then find the person among the attached `people/` notes; the value is
  the note's title exactly. A first name that matches several notes, or none,
  is not confident.
- **Otherwise**: map the label to `"?"` and mark it `unknown`.

Never invent a person and never write a name that has no note under `people/`.
You cannot create people notes; the owner adds new people on the call page.

## Step 3. Category

Pick the one attached `categories/` note that fits the call best. It is a
guess; name it in the body, the owner confirms it on the page.

## Step 4. Write calls/<id>.md

Everything in the language of the call. The agenda is one or two sentences:
what the call was about and what came out of it, from the content only. Keep
this format character for character; every value in `speakers` and
`speakers_confidence` is a double-quoted string, the keys are the labels
exactly as in the transcript:

```
---
title: "<a short title of the call>"
type: review
transcript: "{{ change_file.Path }}"
speakers:
  "<label 1>": "<name or ?>"
  "<label 2>": "<name or ?>"
assumed: true
speakers_confidence:
  "<label 1>": "confident"
  "<label 2>": "unknown"
---
<agenda>

Транскрипт: [[<transcript path without .md>|дословно]]
Кто говорил: <one entry per label, comma-separated>
Категория (предположение): [[categories/<file name without .md>|<category title>]]
```

Each `Кто говорил` entry is `[[people/<name>|<name>]] (<label>)` for a person
with a note, and plain `<name> (<label>)` for the owner and for `?`.

The agenda line must not contain `[[`: the call page takes the first line
without a link as the agenda.

## Step 5. Finish

Call `finish` with one line: `review <id>: <label>=<name>, …; category <title>`.
