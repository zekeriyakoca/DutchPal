# DutchPal product roadmap

> Last updated: 2026-10-18
> Goal: a high-quality, stable Dutch study tool built on the owner's own textbooks.
> Live: https://dutchpal.lontray.art

## Principles

- Precompute facts, generate only what must be generated. Book text, word lists, answers
  and verb forms are extracted once, validated and stored; the LLM is used for
  explanations, new quiz items and chat, and never reformats stored facts.
- Simple code that follows existing patterns. Never break the page layout or the
  text-selection buttons.
- Book content and media stay out of git (`content/`, `media/` are gitignored).
  Extraction method: [06-content-extraction.md](06-content-extraction.md).

## Done

**Content** (9 books, 195 chapters in prod, every chapter with a word list incl. English)

| Category | Books |
| --- | --- |
| Learning | NL in Gang ch01–16, Delftse A1/A2 (Les 1–42), Teach Yourself (2 units) |
| Reading | Short Stories in Dutch, Er waren eens twee duifjes |
| Grammar | Nederlandse grammatica in gebruik (authored, 79 units) |
| Exams | Staatsexamen B1 and B2 2023–2025 (official keys + audio), Inburgering A2 |

Exam media (~800 MB) on PVC `dutchpal-media`, served at `/dutchpal-api/media`.

**Features**

- Study Book: sidebar layout, book categories, markdown texts, collapsible word lists,
  playable `fill_gap` / `choose_option` exercises.
- Exams: A2/B1/B2 section by section; exam mode (official timer + reminders), free mode, review.
- Writing feedback: Schrijven answers scored on the official criteria, with corrections,
  an improved text and links to grammar units (`POST /writing/evaluate`, not stored yet).
- Vocab Game: words from the books, one-sentence examples, table + flashcards.
- Practice: LLM quiz as validated JSON, interactive with score.
- Chat: history in the session, Enter to send, loading and error states.
- Translation: word lookup (book → vocabulary table → LLM fills only empty fields).
- Text selection: translate / explain / save to Notion.
- Google sign-in, Profile, Settings (Integrations → per-user Notion; default Notion otherwise).
- Redesign, error modal, CI with pytest.

**Engineering**: new content tables + importer (`tools/content/import.py`), read-only
`/content` API, closed DB sessions, k3s deploy on the Oracle VM.

## Now

- [ ] My Words: save a word from the text selection; list per user.
- [ ] Spaced repetition on My Words (FSRS: `py-fsrs` / `ts-fsrs`).
- [ ] Progress tracking per user: chapters read, exercise and exam scores.
- [ ] Ops: nightly `dutchpal-postgres` backup (only manual dumps in `~/dutchpal-backups` today).
- [ ] Owner review of ~390 generated answers (`answers_source: generated_needs_review`).

## Next

- [ ] Daily practice session (due words + one exercise + one short text).
- [ ] Listening: 🔊 on words, dialogue lines and the text selection. Words always use Azure Speech
      (`/tts`, `nl-NL-FennaNeural`, cached on `dutchpal-media` by text hash); longer text uses the
      browser voice unless Settings → General "Use advanced paid voice service" is on. In review;
      needs `AZURE_SPEECH_KEY` (F0 tier) before deploy, see
      [01-production-deployment.md](01-production-deployment.md#text-to-speech).
- [ ] Word lookup: English meanings, part of speech and examples from the Azure Translator
      dictionary (free F0) before the LLM; the LLM only fills what is still empty. In review; needs
      `AZURE_TRANSLATOR_KEY` before deploy, see
      [01-production-deployment.md](01-production-deployment.md#translator-dictionary).
- [ ] "Ask the chapter": questions about the open chapter, answers with citations.
- [ ] Admin page to review and fix generated content.
- [ ] Ops: remove the unused .NET core API from the deploy.
- [ ] Builders write the book `category` and chapter `duration_minutes` fields
      (now added to the JSON by hand).

## Later

- [ ] Placement test (A1–B2).
- [ ] Streaks and daily goals.
- [ ] Anki export of My Words.
- [ ] Speaking practice.
- [ ] Metrics in Grafana: latency, errors, tokens per route.
- [ ] Open datasets as a complement: Wiktionary/Kaikki, NT2Lex, Tatoeba.
- [ ] Security: rotate Postgres passwords.
