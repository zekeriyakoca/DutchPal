# DutchPal code quality review

> Purpose: identify engineering problems that make the system fragile, hard to debug, or hard to extend.

## Summary

The system works, but the codebase still looks like a learning project that grew into production. The biggest risks are scattered AI calls, unclear ownership between FastAPI/.NET/UI, weak error handling, and missing tests.

## Critical issues

| Priority | Area | Problem | Required fix |
| --- | --- | --- | --- |
| P0 | Provider handling | OpenAI/Groq calls are scattered across routes, services, tools, and scripts | create one AI client wrapper with provider/model/error policy |
| P0 | Public writes | .NET Notion write endpoints are public | add auth or disable in production |
| P0 | Secrets/config | `.env.production` and local secret files exist near source | keep secrets out of images and commits; audit history before public sharing |
| P1 | Error handling | Some routes normalize OpenAI errors, others do not | apply one exception middleware/error mapper |
| P1 | DB sessions | FastAPI creates sessions manually and often does not close them | use FastAPI dependency with `try/finally db.close()` |
| P1 | Duplicate responsibilities | FastAPI and .NET both expose learning-related APIs without a clear boundary | define ownership: FastAPI AI, .NET content/Notion |
| P1 | Mutable image tags | deploy relies on `current` and forced rollouts | use immutable SHA tags |
| P1 | Tests | no endpoint/provider regression tests | add smoke tests and mocked provider tests |
| P2 | Prompt code | prompts are embedded in route/service functions | move prompts to versioned files |
| P2 | Legacy files | local scripts, data, and generated files live beside runtime code | split runtime app from ingestion/tools |

## FastAPI review

Current issues:

- `tools/agent.py` owns runtime agent setup, DB engine, tools, and local CLI behavior.
- `services/app_service.py` mixes DB queries, OpenAI embeddings, Groq calls, translation writes, grammar explanation, and RAG logic.
- routes sometimes call AI directly, sometimes call services, sometimes call the agent.
- some DB sessions are not closed.
- provider failures are partially normalized only in selected routes.

Target structure:

```text
app/
  main.py
  api/
    routes/
  core/
    config.py
    errors.py
  db/
    session.py
    models.py
  ai/
    client.py
    providers.py
    endpoint_config.py
    prompts/
  learning/
    vocabulary_service.py
    sentence_service.py
    quiz_service.py
    rag_service.py
  agent/
    agent.py
    tools.py
```

Immediate FastAPI fixes:

1. Add a single DB session dependency.
2. Add global exception handling for provider errors.
3. Move AI calls behind `ai/client.py`.
4. Move prompts out of code.
5. Add endpoint tests with mocked provider responses.

## .NET API review

Current issues:

- `VocabularyController.Get` ignores request and calls `agent.Chat("Say hi")`.
- Notion write endpoints are exposed without auth.
- Swagger is intentionally open, but write endpoints should still be protected.
- `bin/obj` generated files appear dirty in the repo.
- Several build warnings exist and are not tracked.

Required fixes:

1. Delete or implement the placeholder vocabulary endpoint.
2. Add auth for Notion endpoints.
3. Add request validation models.
4. Clean generated files from git state and `.gitignore`.
5. Add integration tests for books/sections endpoints.

## Angular UI review

Current issues:

- UI treats most API failures generically.
- Provider-specific failures are not surfaced clearly to users.
- production API origin is patched at Docker build time.
- workflow is spread across pages; core learning loop is not dominant.

Required fixes:

1. Add API error mapping:
   - provider unavailable
   - validation error
   - server error
2. Move UI production config to runtime config instead of Docker string replacement.
3. Make `Study Book` the primary workflow.
4. Add loading/error states per panel, not only global toast.

## DevOps review

Good:

- one Helm chart
- namespace isolation
- Traefik `IngressRoute`
- readiness/liveness probes
- resource requests/limits
- repeatable deploy script

Gaps:

- mutable `current` tag
- manual DB restore
- no DB backup/restore test
- no release artifact manifest
- no automated smoke suite for real user workflows

Required fixes:

1. Use git SHA image tags.
2. Write a release manifest with image digests.
3. Add `kubectl`/curl smoke checks for:
   - UI
   - `/chat`
   - `/bootstrap`
   - `/books/{id}/section-options`
   - provider failure path
4. Add scheduled Postgres backup.

## Testing roadmap

| Layer | Tests |
| --- | --- |
| FastAPI unit | prompt builders, provider error mapping, JSON parsing |
| FastAPI integration | `/chat`, `/vocabulary`, `/translate-word-as-json`, `/explain` |
| .NET integration | books, sections, sentences, Notion disabled/authorized behavior |
| UI e2e | study section, translate word, save word, quiz |
| Deploy smoke | Helm lint, rollout, public endpoint checks |

## Refactor order

1. AI client wrapper and error mapping.
2. DB session cleanup.
3. Notion auth.
4. Prompt extraction.
5. Runtime config for UI.
6. Tests around current behavior.
7. Code structure cleanup.

Do not start with broad folder reshuffling. First pin behavior with tests and provider contracts.
