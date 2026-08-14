#!/usr/bin/env bash
set -euo pipefail

KEY="${SSH_KEY:-$HOME/.ssh/ssh-ovm-printmeart.key}"
SSH_TARGET="${SSH_HOST:-ubuntu@lontray.art}"
NAMESPACE="${NAMESPACE:-dutchpal}"
RELEASE="${RELEASE:-dutchpal}"
IMAGE_TAG="current"
DOMAIN="${DUTCHPAL_DOMAIN:-dutchpal.lontray.art}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image-tag|--tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --domain)
      DOMAIN="$2"
      shift 2
      ;;
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
HELM_CHART_DIR="$ROOT_DIR/DevOps/helm/dutchpal"
SECRETS_FILE="$SCRIPT_DIR/secrets.env"

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "ERROR: $SECRETS_FILE not found." >&2
  echo "Copy DevOps/k3s/secrets.env.example to DevOps/k3s/secrets.env and fill it." >&2
  exit 1
fi

# shellcheck source=secrets.env
source "$SECRETS_FILE"

: "${POSTGRES_USER:=dutchpal}"
: "${POSTGRES_DB:=dutchpal}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required in DevOps/k3s/secrets.env}"
: "${OPENAI_API_KEY:?OPENAI_API_KEY is required in DevOps/k3s/secrets.env}"
: "${GROQ_API_KEY:?GROQ_API_KEY is required in DevOps/k3s/secrets.env}"
: "${CO_API_KEY:?CO_API_KEY is required in DevOps/k3s/secrets.env}"
: "${LOGFIRE_TOKEN:=}"

echo "Deploying DutchPal to $SSH_TARGET"
echo "  namespace: $NAMESPACE"
echo "  release:   $RELEASE"
echo "  tag:       $IMAGE_TAG"
echo "  domain:    $DOMAIN"

if command -v dig >/dev/null 2>&1; then
  RESOLVED_IP="$(dig +short "$DOMAIN" | tail -n 1 || true)"
  if [[ -z "$RESOLVED_IP" ]]; then
    echo "WARNING: $DOMAIN does not resolve yet. Helm deploy can still run, but external smoke tests may fail."
  else
    echo "DNS: $DOMAIN -> $RESOLVED_IP"
  fi
fi

echo "Copying Helm chart to VM..."
ssh -i "$KEY" "$SSH_TARGET" 'mkdir -p ~/dutchpal/helm'
scp -i "$KEY" -r "$HELM_CHART_DIR" "$SSH_TARGET":~/dutchpal/helm/

ssh -i "$KEY" -o ServerAliveInterval=30 -o ServerAliveCountMax=20 "$SSH_TARGET" \
  NAMESPACE="$NAMESPACE" \
  RELEASE="$RELEASE" \
  IMAGE_TAG="$IMAGE_TAG" \
  DOMAIN="$DOMAIN" \
  POSTGRES_USER="$POSTGRES_USER" \
  POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  POSTGRES_DB="$POSTGRES_DB" \
  OPENAI_API_KEY="$OPENAI_API_KEY" \
  GROQ_API_KEY="$GROQ_API_KEY" \
  CO_API_KEY="$CO_API_KEY" \
  LOGFIRE_TOKEN="$LOGFIRE_TOKEN" \
  'bash -s' << 'REMOTE'
set -euo pipefail
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

echo "Checking cluster access..."
kubectl get nodes >/dev/null

if ! command -v helm >/dev/null 2>&1; then
  echo "Installing Helm..."
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

if ! kubectl api-resources | grep -q '^ingressroutes'; then
  echo "ERROR: Traefik IngressRoute CRD is not available in this cluster." >&2
  echo "DutchPal chart does not install cluster-wide Traefik resources." >&2
  exit 1
fi

echo "Ensuring namespace and secrets..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic dutchpal-secrets \
  --from-literal=POSTGRES_USER="$POSTGRES_USER" \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=POSTGRES_DB="$POSTGRES_DB" \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=GROQ_API_KEY="$GROQ_API_KEY" \
  --from-literal=CO_API_KEY="$CO_API_KEY" \
  --from-literal=LOGFIRE_TOKEN="$LOGFIRE_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Running Helm lint..."
helm lint "$HOME/dutchpal/helm/dutchpal"

echo "Deploying Helm release..."
helm upgrade --install "$RELEASE" "$HOME/dutchpal/helm/dutchpal" \
  --namespace "$NAMESPACE" \
  -f "$HOME/dutchpal/helm/dutchpal/values.yaml" \
  -f "$HOME/dutchpal/helm/dutchpal/values.k3s.yaml" \
  --set "global.imageTag=$IMAGE_TAG" \
  --set "global.domain=$DOMAIN" \
  --set "config.publicOrigin=https://$DOMAIN" \
  --cleanup-on-fail \
  --wait --timeout 10m

echo "Restarting app deployments to pull image tag ${IMAGE_TAG}..."
for deployment in dutchpal-agent-api dutchpal-core-api dutchpal-ui; do
  kubectl -n "$NAMESPACE" rollout restart "deployment/${deployment}"
done

echo "Waiting for rollouts..."
kubectl -n "$NAMESPACE" rollout status statefulset/dutchpal-postgres --timeout=5m
kubectl -n "$NAMESPACE" rollout status deployment/dutchpal-agent-api --timeout=5m
kubectl -n "$NAMESPACE" rollout status deployment/dutchpal-core-api --timeout=5m
kubectl -n "$NAMESPACE" rollout status deployment/dutchpal-ui --timeout=5m

echo "Internal smoke checks..."
kubectl -n "$NAMESPACE" run dutchpal-smoke-agent \
  --rm -i --restart=Never --image=curlimages/curl:8.7.1 \
  -- curl -fsS "http://dutchpal-agent-api:40001/health" < /dev/null

kubectl -n "$NAMESPACE" run dutchpal-smoke-core \
  --rm -i --restart=Never --image=curlimages/curl:8.7.1 \
  -- curl -fsS "http://dutchpal-core-api:5257/health" < /dev/null

echo "Current DutchPal resources:"
kubectl -n "$NAMESPACE" get pods,svc,pvc,ingressroute

echo "External smoke checks (non-blocking if DNS is not ready):"
curl -fsS --max-time 10 "https://${DOMAIN}/dutchpal-api/health" || echo "WARNING: agent external smoke failed"
curl -fsS --max-time 10 "https://${DOMAIN}/dutchpal-v2-api/health" || echo "WARNING: core external smoke failed"
curl -fsS --max-time 10 "https://${DOMAIN}/" >/dev/null || echo "WARNING: UI external smoke failed"

echo "DutchPal deploy complete."
REMOTE

echo ""
echo "URLs:"
echo "  https://$DOMAIN/"
echo "  https://$DOMAIN/dutchpal-api/health"
echo "  https://$DOMAIN/dutchpal-v2-api/health"
