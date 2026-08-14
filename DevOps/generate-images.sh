#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

API_REPO="${API_REPO:-$ROOT_DIR/../DutchPal-API}"
UI_REPO="${UI_REPO:-$ROOT_DIR/../DutchPal-UI}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-docker.io/zekeriyakoca}"
IMAGE_TAG="current"
PUSH=1
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-https://dutchpal.lontray.art}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag|--image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --no-push)
      PUSH=0
      shift
      ;;
    --public-origin)
      PUBLIC_ORIGIN="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$API_REPO/DutchPal_API" ]]; then
  echo "ERROR: DutchPal-API repo not found at $API_REPO" >&2
  exit 1
fi

if [[ ! -d "$UI_REPO/src" ]]; then
  echo "ERROR: DutchPal-UI repo not found at $UI_REPO" >&2
  exit 1
fi

AGENT_IMAGE="$IMAGE_REGISTRY/dutchpal-agent-api:$IMAGE_TAG"
CORE_IMAGE="$IMAGE_REGISTRY/dutchpal-core-api:$IMAGE_TAG"
UI_IMAGE="$IMAGE_REGISTRY/dutchpal-ui:$IMAGE_TAG"

echo "Building DutchPal images:"
echo "  $AGENT_IMAGE"
echo "  $CORE_IMAGE"
echo "  $UI_IMAGE"
echo "  public origin: $PUBLIC_ORIGIN"

docker build -t "$AGENT_IMAGE" "$ROOT_DIR"

docker build \
  -f "$API_REPO/DutchPal_API/Dockerfile" \
  -t "$CORE_IMAGE" \
  "$API_REPO"

docker build \
  -f "$ROOT_DIR/DevOps/docker/Dockerfile.ui" \
  --build-arg "PUBLIC_ORIGIN=$PUBLIC_ORIGIN" \
  -t "$UI_IMAGE" \
  "$UI_REPO"

if [[ "$PUSH" == "1" ]]; then
  docker push "$AGENT_IMAGE"
  docker push "$CORE_IMAGE"
  docker push "$UI_IMAGE"
else
  echo "Skipping push because --no-push was supplied."
fi
