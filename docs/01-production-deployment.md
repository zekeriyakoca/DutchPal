# DutchPal production deployment

> Last updated: 2026-10-17  
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
| `DutchPal-API` | .NET API, only Notion writes (no longer called by the UI; retire it) | built by `DutchPal/DevOps/generate-images.sh` |
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
| PVC | `postgres-data-dutchpal-postgres-0`, `dutchpal-media` |

## Media volume

Exam audio, video and pictures (see "Exams with media" in [06-content-extraction.md](06-content-extraction.md))
are not in any image. They live on the PVC `dutchpal-media` (`local-path`, 2Gi, `helm.sh/resource-policy: keep`),
mounted read-only at `/media` in the agent API with `MEDIA_DIR=/media`, and are served at
`https://dutchpal.lontray.art/dutchpal-api/media/<path>` (Range requests work, so players can seek).
Values: `media.enabled`, `media.storageClass`, `media.storage`, `media.mountPath`.

The agent API mounts the volume read-only, so copy files in through a short-lived pod that mounts it writable
(run from a machine with kubectl access to the cluster, in the main checkout that has `media/`):

```bash
kubectl -n dutchpal run media-upload --image=busybox:1.36 --restart=Never --overrides='{"spec":{"containers":[{"name":"media-upload","image":"busybox:1.36","command":["sleep","3600"],"volumeMounts":[{"name":"media","mountPath":"/media"}]}],"volumes":[{"name":"media","persistentVolumeClaim":{"claimName":"dutchpal-media"}}]}}'
kubectl -n dutchpal wait --for=condition=Ready pod/media-upload --timeout=120s
kubectl -n dutchpal cp media/staatsexamen-b1 media-upload:/media/staatsexamen-b1
kubectl -n dutchpal exec media-upload -- du -sh /media/staatsexamen-b1
kubectl -n dutchpal delete pod media-upload
```

`kubectl cp` into an existing folder nests it, so delete the old folder in the pod first when re-uploading
(`kubectl -n dutchpal exec media-upload -- rm -rf /media/staatsexamen-b1`). The PVC is bound on first use
(`WaitForFirstConsumer`), so deploy the chart first. Check one file:
`curl -fsI "https://dutchpal.lontray.art/dutchpal-api/media/staatsexamen-b1/2024-luisteren/Track%203%20opgave%201.mp3"`.
The chapters that use these files are imported like any other book (`tools/content/import.py`).

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

### Retiring the old book tables

The app no longer reads `books`, `sections`, `sentences`, `question_groups` or `question_items`
(examples, book selects and the chat agent use the content tables from
[06-content-extraction.md](06-content-extraction.md)). `vocabulary` stays: Vocab Game and
`/word/lookup` use it. Once that API version is deployed and a backup is taken, drop them
(done in production on 2026-10-17 after a backup; kept here for other environments):

```sql
BEGIN;
DROP TABLE question_items, question_groups, sentences, sections, books;
COMMIT;
```

`tools/embed.py` still defines these models for the old offline pipeline; do not run it afterwards.

### Users and settings tables

`users` and `user_settings` ([services/users.py](../services/users.py)) are created by the agent
API on startup with `create_all`, which only creates missing tables and never alters or drops
anything, so it is safe on the existing database. Nothing to run by hand. A later column change
needs an `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` next to that `create_all` in `main.py`.

## Secrets and config

All values live in `DevOps/k3s/secrets.env` (git-ignored, copy from `secrets.env.example`);
`deploy-to-vm.sh` puts them into `secret/dutchpal-secrets`, which the agent API reads entirely
(`envFrom`). Local development reads the same names from `.env`.

| Variable | Required | Used for |
| --- | --- | --- |
| `NOTION_SECRET` | yes | default (shared) Notion integration secret |
| `NOTION_NOUN_DB_ID`, `NOTION_VERB_DB_ID` | yes | default Notion databases (the ids the .NET API had as `Notion:NounDbId` / `Notion:VerbDbId`) |
| `GOOGLE_CLIENT_ID` | for sign-in | audience checked on Google ID tokens |
| `SESSION_SECRET` | for sign-in | signs the session cookie; changing it signs everyone out |
| `SETTINGS_ENCRYPTION_KEY` | for own Notion | Fernet key that encrypts users' Notion secrets; losing it makes saved secrets unreadable |

Without the three sign-in values the app works as before: no one can sign in and every Notion
save goes to the default Notion.

### Google sign-in

1. Google Cloud console → APIs & Services → OAuth consent screen: app name DutchPal, user type
   External, scopes `openid`, `email`, `profile`; publish it.
2. Credentials → Create credentials → OAuth client ID → type **Web application**.
   Authorised JavaScript origins: `https://dutchpal.lontray.art` and `http://localhost:4200`.
   No redirect URIs are needed.
3. Copy the client ID (`….apps.googleusercontent.com`). It is public:
   - backend: `GOOGLE_CLIENT_ID` in `secrets.env` / `.env`;
   - UI: `googleClientId` in `DutchPal-UI/src/environments/environment.ts` and
     `environment.production.ts`. An empty value hides the sign-in button.
4. Generate `SESSION_SECRET` and `SETTINGS_ENCRYPTION_KEY` with the commands in
   `secrets.env.example`, then redeploy.

The session is an httpOnly, Secure, SameSite=Lax cookie set by `/dutchpal-api/auth/google`. The
UI and API share the origin in production, so no token is stored in the browser.

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
| `POST /dutchpal-api/quiz` | Quiz UI | OpenAI `gpt-5-mini` agent, structured JSON output, validated (one retry) | none | OpenAI failure -> `503` |
| `POST /dutchpal-api/vocabulary` | Vocabulary UI | DB query (`vocabulary`, examples from `dialogues`/`exercises`), JSON rows; OpenAI `text-embedding-ada-002` if `message` exists | none | OpenAI failure -> `503` |
| `POST /dutchpal-api/translate` | Translation UI | Groq `gpt-oss-20b` -> fallback `gpt-5-nano` | one retry on unreadable JSON | OpenAI failure -> `503`; unreadable JSON -> `502` |
| `POST /dutchpal-api/word/lookup` | Translation UI (word) | DB: `vocab_entries`, `vocabulary` | Groq `gpt-oss-20b` -> fallback `gpt-5-nano` fills missing fields (JSON, one retry) | stored data returned without examples; nothing stored -> `503` / `502` |
| `POST /dutchpal-api/translate-word` | Selection/options UI | same as `/word/lookup`, rendered as a Markdown table | same as `/word/lookup` | same as `/word/lookup` |
| `POST /dutchpal-api/translate-word-as-json` | Selection/options UI | OpenAI `gpt-5-mini` | none | OpenAI failure -> `503` |
| `POST /dutchpal-api/explain` | Selection/options UI | OpenAI `gpt-5-mini` | none | OpenAI failure -> `503` |
| `GET /dutchpal-api/bootstrap` | App startup | DB query (`chapters`: book options) | none | no AI |
| `POST /dutchpal-api/notion/{noun,verb}` | Selection/options UI (Notion save) | Notion API: the user's own Notion from Settings, else the default | none | Notion error -> `502`; not configured -> `503` |
| `POST /dutchpal-api/auth/google`, `GET /auth/me`, `POST /auth/logout` | Header sign-in | Google ID token check | none | bad token -> `401`; not configured -> `503` |
| `GET /dutchpal-api/settings`, `PUT`/`DELETE /settings/notion`, `POST /settings/notion/test` | Settings page | DB; test calls Notion | none | signed out -> `401` |

## AI providers

Groq `llama-*` models became enterprise-only (`404 model_not_found`) and were replaced on 2026-09-28. Simple tasks (`chat_fast`: translate, word lookup, vocabulary formatting) use Groq `openai/gpt-oss-20b` on the free tier (30 RPM, 1K RPD, 8K TPM) and fall back to OpenAI `gpt-5-nano` on any Groq failure. Everything else uses OpenAI. Fallbacks are logged as `Groq failed, falling back to gpt-5-nano`.

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
| P1 | anonymous users can still write to the default Notion (owner's choice) | require sign-in for the default Notion if it gets abused |
| P0 | images use mutable `current` tag | move to git SHA tags |
| P1 | DB restore is manual | add repeatable restore/seed job |
| P1 | provider errors not normalized everywhere | use one AI provider wrapper |
| P1 | UI does not clearly display provider `503` | add provider-specific error message |
| P1 | no backup policy for `dutchpal-postgres` | add scheduled backup and restore test |
| P2 | OTEL/logging not standardized | add request id, route metrics, AI metrics |
