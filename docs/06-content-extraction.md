# Book content extraction

> How book chapters are turned into structured, validated JSON.
> Reference result: `content/nl-in-gang/ch01.json` (local only, gitignored).

## Why this method

The 2024 pipeline (PDF text layer / OCR → regex → DB) produced fragmented, misordered,
error-ridden text. The PDF text layers are unreliable (NL in Gang's text layer is shifted
and duplicated per page pair), but the page **images** are clean. Claude reads the page
images directly and writes structured JSON: it understands layout (two-column word lists,
speaker labels, numbered exercises, tables), fixes nothing that is not in the book, and
keeps the book's own translations. No API tokens are used; the work runs on the owner's
Claude subscription.

## Rules

- Content goes to `content/<book-id>/chNN.json`. `content/` is gitignored and dockerignored — never commit it or ship it in an image.
- Transcribe what the book says. Keep the book's own English translations. Do not invent vocabulary or translations.
- Anything Claude adds that is not printed in the book (exercise answers) is marked `"answers_source": "generated_needs_review"`.
- One chapter per file. Record `pdf_pages` and `book_pages` (printed page numbers).
- Run the validator after every chapter; fix all errors before moving on.
- Start each extraction session fresh: long conversations make every page much more expensive.
- Skip what costs a lot and teaches little (owner's decision, 2026-10-16): teacher hand-outs, classroom games, audio-only
  discrimination tasks whose words are not printed, decorative images, and anything unreadable in the scan. Keep a short
  stub (`id`, `label`, `book_page`, `type`, one-line `instruction`) or drop it entirely; never guess unreadable text.

## Steps per chapter

1. Render the chapter's pages (100 dpi is enough):
   ```bash
   pdftoppm -f <first> -l <last> -r 100 -png "repo-for-books/NL in Gang/NL in Gang.pdf" <scratch>/p
   ```
   The chapter cover page shows the chapter number, title and goals; the next cover marks the end.
2. Read each page image and fill the schema below.
3. Write `content/<book-id>/chNN.json`.
4. Validate:
   ```bash
   python3 tools/content/validate.py content/<book-id>/chNN.json
   ```
5. Update the book's status in [05-product-roadmap.md](05-product-roadmap.md).

## Loading into the database

Tables are defined in `tools/content/models.py` (own SQLAlchemy `Base`, created with
`create_all`; the old tables are not touched): `chapters` (one row per `book_id` + `number`,
with `goals`, `culture`, `reflection` as JSONB), `dialogues`, `vocab_entries` (one row per word),
`grammar_topics` (the flexible fields in `content`) and `exercises` (`type`, `answers_source`
as columns, everything else per type in `payload`).

```bash
python tools/content/import.py content/<book-id>/ch*.json
```

Run from the repo root (reads `DATABASE_URL` from `.env`). Chapters with validation errors are
refused. Re-running is safe: rows are upserted on their JSON ids (vocabulary on list/item
position), rows removed from the JSON are deleted, and row ids stay stable. A non-local
database needs `--allow-remote`; ask the owner first.

## Schema (v1)

Top level: `schema_version`, `book {id, title, cefr}`, `chapter`, `dialogues`, `vocabulary`,
`grammar`, `exercises`, `culture`, `reflection`. Look at `ch01.json` for a full example.

| Field | Shape |
| --- | --- |
| `chapter` | `number`, `title`, `pdf_pages [first,last]`, `book_pages [first,last]`, `goals []` (from the cover box) |
| `dialogues[]` | `id`, `title`, `audio_tracks []` (CD track labels like `1-1`), `book_page`, `lines [{speaker, text}]`; stage directions like `(een poosje later)` are `{speaker: null, text, stage: true}` |
| `vocabulary[]` | one entry per printed list: `list`, `book_page`, `items [{nl, lemma, article?, form?, en}]`. `nl` = as printed, `lemma` = dictionary form, `form` = inflected form when the list shows `form (lemma)` |
| `grammar[]` | `id`, `title`, `book_page`, plus whatever fits: `pairs [{q,a}]`, `table {columns, rows}`, `examples []`, `highlight []` (words the book prints in colour), `phrases []`, `conjugation {verbs, rows [{pronoun, forms}]}`, `numbers {}`, `times {}`, `months []`, `seasons []`, `scale` / `responses [{polarity, text}]`, `note` |
| `exercises[]` | `id`, `label` (e.g. `Opdracht 2`), `book_page`, `type`, `instruction`, and per type: `items`, `prompts`, `example`, `fields`, `parts [{label, instruction}]` (A/B sub-tasks), `steps [{role, text}]` (role-play script), `words []`, `lines [[...]]` (pronunciation rows), `source_text`, `menu` |
| `culture[]` | culture / "In de praktijk" boxes |
| `reflection` | `book_page`, `can_do []` |

Exercise types (see `EXERCISE_TYPES` in the validator): `speaking_pair`, `speaking_roleplay`,
`fill_gap`, `choose_option`, `personal_questions`, `teacher_material`, `classroom_activity`,
`form_fill`, `listening_stress`, `matching`, `ordering`, `reading`, `listening`, `writing`,
`comprehension_questions`, `puzzle`, `pronunciation`, `rewrite`, `word_stress`, `dialogue_completion`.

- `fill_gap`: `text` uses `___` per gap; `answers` has one entry per gap; alternatives joined with `|` (`"Zij|Ze"`).
- `fill_gap` items may carry `response` (the printed answer sentence the gap is checked against) or `cue` (the printed prompt); the exercise may carry a word bank in `options`.
- `choose_option`: `text` with `{a/b}`, `options [a,b]`, `answer` (must be one of the options).
- `comprehension_questions` (Vragen bij de dialoog), `puzzle`, `reading`: `items [{n, q, a, options?}]`; with `options`, `a` must be one of them (true/false = `["waar", "niet waar"]`). `puzzle` also has `given` (the printed grid/clues).
- `rewrite`: `items [{n, text, focus? | cue?, a}]` — rewrite `text` (start with `focus`, or answer using `cue`).
- `word_stress`: `items [{n, word, stressed}]`; `stressed` must be a substring of `word`.
- `dialogue_completion`: `lines [{speaker, text, model?}]`; every line whose `text` has `___` needs a `model` answer.
- `pronunciation`: `audio_tracks`, `lines [[word, ...]]` to listen and repeat. Audio-only discrimination tasks (words not printed) are `listening` with `rows` / `columns`.

New types or fields: add them to the validator and this table in the same change.
