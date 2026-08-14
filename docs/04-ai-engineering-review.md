# DutchPal AI engineering review

> Purpose: review the current AI integration and define what must change before this is a reliable AI product.

## Current AI map

| Flow | Provider/model | Problem |
| --- | --- | --- |
| Agent chat | Groq `llama-3.3-70b-versatile` | tools can call OpenAI, so failures are not obvious from the endpoint |
| Semantic lookup | OpenAI `text-embedding-ada-002` | legacy model and current quota failure |
| Explain | OpenAI `gpt-5-mini` | no eval, no schema, provider failure must be explicit |
| Explain grammar | OpenAI `gpt-3.5-turbo` | legacy model, provider failure must be explicit |
| Translate word JSON | OpenAI `gpt-5-mini` | JSON parsing is fragile |
| Translate / markdown formatting | Groq `llama-3.1-8b-instant` | no schema, no quality evaluation |
| Missing sentence translation | Groq `llama-3.1-8b-instant` | writes generated translation back to DB |

## Main critique

The app connects models, but it does not yet manage AI behavior as a system.

Problems:

- provider/model choice is hardcoded
- prompts are embedded in Python functions
- no prompt versions
- no eval suite
- no quality gates
- no token/cost/latency metrics
- no consistent provider error contract
- no clear fallback policy
- agent tools can trigger nested AI calls
- RAG retrieval has no citations or score reporting

## Rules going forward

- No silent provider fallback.
- Every endpoint must declare provider, model, prompt, output shape, timeout, retry, and fallback policy.
- Fallback is allowed only if documented and accepted.
- Provider outage must be visible as a provider error, not hidden as a generic 500.
- Structured output must use schema validation.
- Prompt/model changes must run evals before release.

## P0 fixes

| Fix | Why |
| --- | --- |
| Fix OpenAI quota/key | OpenAI-dependent endpoints currently cannot work |
| One AI client wrapper | stop scattered provider calls |
| Provider error mapper for all AI routes | consistent 503/429/502 behavior |
| Endpoint config file | make provider/model choice visible |
| Prompt files with versions | enable review and rollback |
| Basic eval dataset | prevent accidental regression |

## Endpoint config target

Example:

```yaml
chat:
  provider: groq
  model: llama-3.3-70b-versatile
  prompt: chat_system:v1
  output: markdown
  fallback: none

translate_word_json:
  provider: openai
  model: gpt-5-mini
  prompt: translate_word_json:v1
  output: WordTranslation
  fallback: none

translate_word_markdown:
  provider: groq
  model: llama-3.1-8b-instant
  prompt: translate_word_markdown:v1
  output: markdown
  fallback: none
```

## Evaluation plan

Create:

```text
evals/
  datasets/
    translate_word_json.jsonl
    vocabulary_markdown.jsonl
    grammar_explain.jsonl
    chat_tools.jsonl
    rag_grounding.jsonl
    prompt_injection.jsonl
  run_eval.py
```

Minimum first dataset:

| Dataset | Cases | Checks |
| --- | ---: | --- |
| `translate_word_json` | 25 | valid JSON, word/type/translation/examples |
| `vocabulary_markdown` | 25 | table shape, example relevance |
| `grammar_explain` | 25 | correctness, concise explanation |
| `chat_tools` | 20 | no tool leakage, useful answer |
| `rag_grounding` | 25 | answer grounded in retrieved section/sentence |
| `prompt_injection` | 10 | no internal prompt/tool exposure |

## Observability plan

Metrics:

- `ai_request_total{route,provider,model,status}`
- `ai_request_duration_seconds{route,provider,model}`
- `ai_provider_error_total{provider,error_type}`
- `ai_invalid_json_total{route,provider,model,prompt_version}`
- `ai_tool_call_total{tool,status}`
- `ai_tokens_input_total{route,provider,model}`
- `ai_tokens_output_total{route,provider,model}`
- `ai_cost_usd_total{route,provider,model}`
- `rag_empty_result_total{route}`
- `rag_top_k_similarity{route}`

Tracing:

- one span per HTTP request
- one span per AI provider call
- one span per agent tool call
- one correlation id across request, provider call, tool call, and DB query

Do not log full prompt/response by default.

## Tool governance

Every agent tool needs:

- name
- allowed endpoints
- read/write classification
- provider dependency
- timeout
- retry policy
- max result size
- audit requirement

Current risky tools:

| Tool | Risk |
| --- | --- |
| `find_lesson` | OpenAI embedding dependency hidden inside Groq agent flow |
| `find_sentences` | OpenAI embedding dependency and possible DB translation update |
| `get_vocabularies_from_dataset` | OpenAI embedding dependency |
| `explain_grammar` | nested OpenAI chat call |

## RAG improvements

Current retrieval uses pgvector but does not expose enough context.

Required:

- chunk/source id
- book id/title
- section id
- CEFR
- embedding model
- similarity score
- retrieval mode: vector/full-text/hybrid
- citations in response metadata

## JSON reliability

Apply to `/translate-word-as-json` first:

1. strict Pydantic schema
2. one repair attempt max
3. `502 invalid provider response` if still invalid
4. metric increment
5. eval coverage

## Implementation order

1. Fix OpenAI quota/key.
2. Add AI endpoint config.
3. Add AI client wrapper.
4. Normalize provider errors for every AI route.
5. Move prompts to files.
6. Add first eval datasets.
7. Add metrics/tracing.
8. Add tool registry.
9. Add RAG metadata/citations.
