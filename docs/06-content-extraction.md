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

## Schema (v1)

Top level: `schema_version`, `book {id, title, cefr}`, `chapter`, `dialogues`, `vocabulary`,
`grammar`, `exercises`, `culture`, `reflection`. Look at `ch01.json` for a full example.

| Field | Shape |
| --- | --- |
| `chapter` | `number`, `title`, `pdf_pages [first,last]`, `book_pages [first,last]`, `goals []` (from the cover box) |
| `dialogues[]` | `id`, `title`, `audio_tracks []` (CD track labels like `1-1`), `book_page`, `lines [{speaker, text}]` |
| `vocabulary[]` | one entry per printed list: `list`, `book_page`, `items [{nl, lemma, article?, form?, en}]`. `nl` = as printed, `lemma` = dictionary form, `form` = inflected form when the list shows `form (lemma)` |
| `grammar[]` | `id`, `title`, `book_page`, plus whatever fits: `pairs [{q,a}]`, `table {columns, rows}`, `examples []`, `conjugation {verbs, rows [{pronoun, forms}]}`, `numbers {}`, `note` |
| `exercises[]` | `id`, `label` (e.g. `Opdracht 2`), `book_page`, `type`, `instruction`, and per type: `items`, `prompts`, `example`, `fields` |
| `culture[]` | culture / "In de praktijk" boxes |
| `reflection` | `book_page`, `can_do []` |

Exercise types (see `EXERCISE_TYPES` in the validator): `speaking_pair`, `speaking_roleplay`,
`fill_gap`, `choose_option`, `personal_questions`, `teacher_material`, `classroom_activity`,
`form_fill`, `listening_stress`, `matching`, `ordering`, `reading`, `listening`, `writing`.

- `fill_gap`: `text` uses `___` per gap; `answers` has one entry per gap; alternatives joined with `|` (`"Zij|Ze"`).
- `choose_option`: `text` with `{a/b}`, `options [a,b]`, `answer` (must be one of the options).

New types or fields: add them to the validator and this table in the same change.
