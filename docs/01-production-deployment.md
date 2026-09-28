# DutchPal production deployment

> Last updated: 2026-09-28  
> Source of truth: `DutchPal` repo  
> Target: Oracle VM k3s  
> Public URL: `https://dutchpal.lontray.art`

## Production shape

```text
Internet
  -> existing Traefik in k3s
    -> /                  -> dutchpal-ui
    -> /dutchpal-api      -> dutchpal-agent-api
    -> /dutchpal-v2-api   -> dutchpal-core-api

namespace/dutchpal
  -> deployment/dutchpal-ui
  -> deployment/dutchpal-agent-api
  -> deployment/dutchpal-core-api
  -> statefulset/dutchpal-postgres
```

There is one DutchPal `IngressRoute`. There is no second Traefik.

## Repos

| Repo | Role | Production source |
| --- | --- | --- |
| `DutchPal` | FastAPI agent API and deploy orchestration | yes |
| `DutchPal-API` | .NET API for books, sections, Notion writes | built by `DutchPal/DevOps/generate-images.sh` |
| `DutchPal-UI` | Angular UI | built by `DutchPal/DevOps/generate-images.sh` |

## Images

| Image | Source |
| --- | --- |
| `docker.io/zekeriyakoca/dutchpal-agent-api:current` | `DutchPal/Dockerfile` |
| `docker.io/zekeriyakoca/dutchpal-core-api:current` | `DutchPal-API/DutchPal_API/Dockerfile` |
| `docker.io/zekeriyakoca/dutchpal-ui:current` | `DutchPal/DevOps/docker/Dockerfile.ui` |

`current` is used today. Production-ready next step: switch to immutable git SHA tags.

## Kubernetes resources

| Resource | Name |
| --- | --- |
| namespace | `dutchpal` |
| release | `dutchpal` |
| deployments | `dutchpal-agent-api`, `dutchpal-core-api`, `dutchpal-ui` |
| statefulset | `dutchpal-postgres` |
| services | `dutchpal-agent-api`, `dutchpal-core-api`, `dutchpal-ui`, `dutchpal-postgres` |
| ingress | `ingressroute/dutchpal` |
| middlewares | `strip-dutchpal-agent-api`, `strip-dutchpal-core-api` |
| secret | `dutchpal-secrets` |
| configmap | `dutchpal-config` |

## Database

Current production DB:

- service: `dutchpal-postgres`
- image: `pgvector/pgvector:pg16`
- PVC: `postgres-data-dutchpal-postgres-0`
- storage class: `local-path`

Restored data:

| Table | Rows |
| --- | ---: |
| `books` | 7 |
| `sections` | 333 |
| `sentences` | 10582 |
| `vocabulary` | 32901 |
| `question_groups` | 8 |
| `question_items` | 49 |

Production gap: restore/seed is not automated yet.

## Deploy commands

Build and push:

```bash
bash DevOps/generate-images.sh --tag current
```

Deploy:

```bash
bash DevOps/k3s/deploy-to-vm.sh --image-tag current
```

The deploy script:

- copies the Helm chart to the VM
- creates/updates `dutchpal-secrets`
- runs `helm lint`
- runs `helm upgrade --install --wait --cleanup-on-fail`
- restarts app deployments to pull `current`
- waits for rollouts
- runs internal and external smoke checks

## Smoke checks

```bash
curl -fsS https://dutchpal.lontray.art/
curl -fsS https://dutchpal.lontray.art/dutchpal-api/health
curl -fsS https://dutchpal.lontray.art/dutchpal-v2-api/health
curl -fsS -X POST https://dutchpal.lontray.art/dutchpal-api/chat \
  -H 'content-type: application/json' \
  --data '{"message":"hello"}'
```

## Endpoint/model matrix

| Endpoint | Used by | Main call | Extra AI calls | Failure behavior |
| --- | --- | --- | --- | --- |
| `POST /dutchpal-api/chat` | Chat UI | OpenAI `gpt-5-mini` agent (reasoning `low`) | tools can call OpenAI embeddings or OpenAI `gpt-5-mini` | OpenAI failure -> `503` |
| `POST /dutchpal-api/ask` | older generic UI flow | OpenAI `gpt-5-mini` agent | same tools as `/chat` | not normalized |
| `POST /dutchpal-api/quiz` | Quiz UI | OpenAI `gpt-5-mini` agent | DB load for paragraph quiz | not normalized |
| `POST /dutchpal-api/vocabulary` | Vocabulary UI | OpenAI `text-embedding-ada-002` if `message` exists | Groq `gpt-oss-20b` -> fallback `gpt-5-nano` formats Markdown | OpenAI failure -> `503` |
| `POST /dutchpal-api/sentences` | Sentence UI | DB query | Groq `gpt-oss-20b` -> fallback `gpt-5-nano` only for missing translations | OpenAI failure -> `503` |
| `POST /dutchpal-api/translate` | Translation UI | Groq `gpt-oss-20b` -> fallback `gpt-5-nano` | none | OpenAI failure -> `503` |
| `POST /dutchpal-api/translate-word` | Word translation UI | Groq `gpt-oss-20b` -> fallback `gpt-5-nano` | `response_quality=2`: `gpt-5-mini` (low); `response_quality=3`: `gpt-5-nano` | OpenAI failure -> `503` |
| `POST /dutchpal-api/translate-word-as-json` | Selection/options UI | OpenAI `gpt-5-mini` | none | OpenAI failure -> `503` |
| `POST /dutchpal-api/explain` | Selection/options UI | OpenAI `gpt-5-mini` | none | OpenAI failure -> `503` |
| `POST /dutchpal-api/explain-grammar` | Grammar UI | OpenAI `gpt-5-mini` (low) | none | OpenAI failure -> `503` |
| `GET /dutchpal-api/bootstrap` | App startup | DB query | none | no AI |
| `/dutchpal-v2-api/*` | Study book UI | .NET + DB | none by default | no AI |

## AI providers

Groq `llama-*` models became enterprise-only (`404 model_not_found`) and were replaced on 2026-09-28. Simple tasks (`chat_fast`: translate, vocabulary formatting, sentence translations, translate-word quality 1) use Groq `openai/gpt-oss-20b` on the free tier (30 RPM, 1K RPD, 8K TPM) and fall back to OpenAI `gpt-5-nano` on any Groq failure. Everything else uses OpenAI. Fallbacks are logged as `Groq failed, falling back to gpt-5-nano`.

## OpenAI state

OpenAI currently returns:

```text
429 insufficient_quota
```

Fix required:

1. Fix OpenAI billing/quota/key.
2. If key changes, update `DevOps/k3s/secrets.env`.
3. Redeploy:

```bash
bash DevOps/k3s/deploy-to-vm.sh --image-tag current
```

## Production readiness gaps

| Priority | Gap | Required fix |
| --- | --- | --- |
| P0 | OpenAI quota broken | fix billing/key and redeploy secret |
| P0 | Notion write endpoints have no auth | add auth before public use |
| P0 | images use mutable `current` tag | move to git SHA tags |
| P1 | DB restore is manual | add repeatable restore/seed job |
| P1 | provider errors not normalized everywhere | use one AI provider wrapper |
| P1 | UI does not clearly display provider `503` | add provider-specific error message |
| P1 | no backup policy for `dutchpal-postgres` | add scheduled backup and restore test |
| P2 | OTEL/logging not standardized | add request id, route metrics, AI metrics |
