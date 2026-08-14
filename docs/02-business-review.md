# DutchPal business review

> Purpose: decide which product flows and endpoints should stay, merge, or go away.

## Positioning

DutchPal should be a book-grounded Dutch study tool.

Primary use case:

```text
Open a real Dutch section
  -> inspect words/sentences
  -> get explanation or translation
  -> practice with sentences or quiz
```

Do not make it a generic AI chat clone. Chat can stay, but it should not be the main product.

## Endpoint decisions

### Keep

| Endpoint | Keep because | Required change |
| --- | --- | --- |
| `GET /dutchpal-api/bootstrap` | UI needs book list | keep |
| `GET /dutchpal-v2-api/books/{bookId}/section-options` | required for study-book flow | keep |
| `GET /dutchpal-v2-api/books/{bookId}/sections/{sectionId}` | core content reading endpoint | keep |
| `GET /dutchpal-v2-api/books/{bookId}/sections/{sectionId}/sentences` | useful for section-level study | keep |
| `POST /dutchpal-api/translate-word` | fast word helper | keep as lightweight markdown response |
| `POST /dutchpal-api/translate-word-as-json` | UI selection/options needs structured result | keep, but make schema strict |
| `POST /dutchpal-api/explain` | selection/options explanation | keep, but rename later to explicit grammar/meaning endpoint |
| `POST /dutchpal-api/sentences` | sentence practice | keep, but return structured data later, not markdown |
| `POST /dutchpal-api/quiz` | practice flow | keep, but split quiz types if behavior diverges |

### Merge

| Current endpoints | Merge into | Why |
| --- | --- | --- |
| `/vocabulary` and `/translate-word` | `/word/lookup` | both answer “what is this word?”; current split is confusing |
| `/explain` and `/explain-grammar` | `/text/explain` | both explain Dutch text; request should choose mode |
| `/ask` and `/chat` | `/chat` | `/ask` duplicates chat with page-specific prompt building |
| FastAPI `/sentences` and .NET section sentences | keep both only if names are explicit | one is random practice, one is section content; current naming hides that |

### Remove or hide

| Endpoint | Decision | Reason |
| --- | --- | --- |
| `POST /dutchpal-api/ask` | remove from UI, then delete | duplicate of `/chat`; page prompt logic belongs in explicit endpoints |
| `POST /dutchpal-v2-api/vocabulary` | delete or implement properly | currently calls `agent.Chat("Say hi")`; this is placeholder behavior |
| `POST /dutchpal-v2-api/vocabulary/verb/export` | hide/protect | admin/export behavior, not public product |
| `POST /dutchpal-v2-api/vocabulary/noun/upsert-to-notion` | protect or disable | public external write |
| `POST /dutchpal-v2-api/vocabulary/verb/upsert-to-notion` | protect or disable | public external write |

### Add

| New endpoint | Purpose | Replaces/uses |
| --- | --- | --- |
| `POST /dutchpal-api/word/lookup` | one structured word lookup | replaces UI use of `/vocabulary`, `/translate-word`, `/translate-word-as-json` where possible |
| `POST /dutchpal-api/text/explain` | one text explanation endpoint | replaces `/explain` and `/explain-grammar` |
| `POST /dutchpal-api/section/study` | section-aware AI answer using selected book/section | avoids generic chat for study-book page |
| `POST /dutchpal-api/practice/sentences` | structured sentence practice | eventual replacement for markdown `/sentences` |
| `POST /dutchpal-api/practice/quiz` | structured quiz response | eventual replacement for markdown `/quiz` |

## Target API shape

### `POST /word/lookup`

Request:

```json
{
  "word": "lopen",
  "book_id": 9,
  "section_id": 12,
  "format": "json"
}
```

Response:

```json
{
  "word": "lopen",
  "type": "VERB",
  "translation": "to walk",
  "forms": {
    "present": ["loop", "loopt", "lopen"],
    "past": ["liep", "liepen"],
    "perfect": ["gelopen"]
  },
  "examples": [
    {
      "sentence": "Ik loop naar school.",
      "translation": "I walk to school.",
      "source": "dataset"
    }
  ]
}
```

### `POST /text/explain`

Request:

```json
{
  "text": "Ik loop naar school.",
  "mode": "grammar",
  "level": "A2"
}
```

Modes:

- `grammar`
- `meaning`
- `translation`
- `correction`

### `POST /section/study`

Request:

```json
{
  "book_id": 9,
  "section_id": 12,
  "question": "Explain the first paragraph."
}
```

This should be the study-book AI endpoint. It must use selected section context, not generic chat.

## UI decisions

| UI area | Decision |
| --- | --- |
| Study Book | make this the primary screen |
| Chat | keep as secondary utility |
| Vocabulary page | keep, but back it with `/word/lookup` |
| Translation page | keep if it remains simple text translation |
| Selection popup | use `/word/lookup` and `/text/explain` |
| Notion save buttons | hide unless auth is added |

## Product priorities

| Priority | Work |
| --- | --- |
| P0 | Fix OpenAI quota/key |
| P0 | Protect or disable Notion write endpoints |
| P0 | Remove `/ask` from UI usage |
| P0 | Delete or fix .NET placeholder `POST /vocabulary` |
| P1 | Add `/word/lookup` |
| P1 | Add `/text/explain` |
| P1 | Add `/section/study` |
| P1 | Return structured JSON for sentence and quiz practice |
| P2 | Add user-facing provider error messages |
| P2 | Add feedback buttons for answer quality |

## What not to build now

- Do not add accounts.
- Do not add payment.
- Do not add more generic chat features.
- Do not add provider fallback without a product decision.
