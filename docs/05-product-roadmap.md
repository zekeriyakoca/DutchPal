# DutchPal product roadmap

> Last updated: 2026-10-16
> Goal: a high-quality, stable Dutch study tool built on the owner's own textbooks.
> Order: **stable MVP → stable features → richer features**. Security hardening comes last.

## Product shape (MVP)

Core loop:

```text
Open a chapter of a real textbook
  -> read dialogue / text, see the book's own word list and grammar
  -> look up a word or sentence
  -> practise with the chapter's exercises and generated quizzes
```

- Primary screen: **Study Book**. Secondary: word/sentence help, Practice. Chat is a utility.
- The books are for the owner's personal use. Book content stays out of git and images
  (`content/` is gitignored and dockerignored).

## Principle: precompute facts, generate only what must be generated

Everything that can be known in advance (book text, word lists, translations, verb forms,
exercise answers) is extracted once, validated, and stored. At runtime the app renders
that data directly. AI is used only where generation is the point: explanations, new
quiz items, chat. Small models must never reformat stored facts (gpt-oss-20b turned the
correct `noemde` into `genoemde` when formatting the vocabulary table).

## Findings that drive Phase 1 (2026-10-16 audit)

| Area | Finding |
| --- | --- |
| Book data | Built from a 2-year-old OCR run. NL in Gang = 221 fragment "sections" with duplicate names, OCR errors (`bescelc iecs` = `bestelt iets`), wrong order. The PDF text layer is misaligned and duplicated per page pair; the page **images** are correct. |
| Books table | `short stories` imported twice (ids 20, 23); CEFR labels wrong (`appel b1`, `B1 Examen` = A1). Source for `appel b1` not found locally. |
| Vocabulary | 32,901 rows, only ~2,200 have a CEFR level; ~30k are noise (names, inflected forms, English). No stored translations. |
| Sentences | 10,582 rows, 270 translated, 55% without CEFR. |
| Vocab Game | Not a game: a markdown table produced by an LLM from DB rows (introduces errors). |
| Practice | Markdown text, not interactive; answers printed at the bottom; some wrong items (`naar de ___ … films` → answer "film"). |
| Chat | Enter key does not submit; no loading state; no history. |
| Engineering | No tests; FastAPI DB sessions not closed in 5 routes; no backup of `dutchpal-postgres`. |

## Phase 1 — stable MVP

### 1.1 Book content extraction (foundation)
Method and schema: [06-content-extraction.md](06-content-extraction.md).

| Book | Source | Pages | Status |
| --- | --- | ---: | --- |
| NL in Gang | `repo-for-books/NL in Gang/NL in Gang.pdf` | 271 | ch01–ch15 done (pdf 1–183, book 17–199); ch16 starts pdf 184 |
| Delftse A1/A2 | `repo-for-books/Delftse a1-a2/*.png` | 42 images | todo |
| Short stories in Dutch | `reading-books/short stories in dutch (first 4 story).pdf` (same as the 4 split PDFs) | 83 | todo |
| Er waren eens twee duifjes | `repo-for-books/aalberse_theo_er_waren_eens_twee_duifjes.pdf` | 16 | todo |
| Grammar in Use (partial) | `repo-for-books/partial-grammar-in-use.pdf` | 18 | todo |
| Teach Yourself (partial) | `repo-for-books/teach_yourself/…pdf` | 7 | todo |
| B1 Examen 2024 | `data/B1 Examen 2024.md` | text | todo (restructure only) |
| appel b1 | **source missing** | — | ask owner |

- [ ] Extract every book chapter into `content/<book>/chXX.json`, validated with `tools/content/validate.py`.
- [ ] Owner reviews generated answer keys (`answers_source: generated_needs_review`).
- [ ] New DB tables (`chapters`, `dialogues`, `vocab_entries`, `grammar_topics`, `exercises`) + importer script. Old tables stay until the UI is switched.
- [ ] Fix book metadata: drop duplicate short stories, correct CEFR labels.

### 1.2 Render stored data directly (no LLM)
- [ ] `/vocabulary` and `/sentences` return JSON; the UI renders tables. Removes LLM formatting errors, ~0.5 s, free.
- [ ] Study Book reads the new chapter structure: goals, dialogue with speakers, word list, grammar, exercises.

### 1.3 Interactive practice
- [ ] Book exercises of type `fill_gap` / `choose_option` playable in the UI with feedback and score.
- [ ] Generated quiz: strict JSON schema, answer and distractors validated against stored vocabulary and the selected level before showing.

### 1.4 UX basics
- [ ] Enter submits in Chat; loading state per panel; readable error per panel (not only the 3 s toast).

### 1.5 Safety net
- [ ] Smoke/e2e tests for the core loop (open chapter, look up word, play exercise, generate quiz).
- [ ] FastAPI DB session dependency with `try/finally close()`.
- [ ] Nightly backup of `dutchpal-postgres` (add to `/opt/k3s-backup/backup.sh` on the VM).

## Phase 2 — stable features
- [ ] One AI client layer + per-endpoint config (provider, model, prompt version, timeout, fallback).
- [ ] Prompts in versioned files; eval sets for translate-word JSON, explain, quiz.
- [ ] Merge endpoints: `/word/lookup`, `/text/explain`; delete `/ask` and the .NET placeholder `POST /vocabulary`.
- [ ] Metrics in Grafana: latency, errors, tokens/cost per route.
- [ ] Update `04-ai-engineering-review.md` model map (still lists llama / gpt-3.5).

## Phase 3 — richer features
- [ ] Section study: ask questions about the open chapter, answer with citations to the book.
- [ ] Progress tracking and spaced repetition (FSRS: `py-fsrs` / `ts-fsrs`).
- [ ] Chat history; answer-quality feedback buttons.
- [ ] Audio: map book CD tracks (e.g. `1-1`, `1-2`) to dialogues; optional local TTS (Piper Dutch voices).
- [ ] Open datasets to complement the books (later, not instead of them): Wiktionary/Kaikki (forms, IPA), NT2Lex (CEFR levels), Tatoeba (example sentences + audio).
- [ ] Notion save, once auth exists.

## Phase 4 — security (last)
- [ ] Auth for Notion write endpoints (or disable).
- [ ] Rotate Postgres passwords.
