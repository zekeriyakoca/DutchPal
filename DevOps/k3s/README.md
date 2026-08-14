# DutchPal k3s deploy

This folder deploys DutchPal to the Oracle VM k3s cluster without changing eCommBone resources.

For the full production contract, read `docs/01-production-deployment.md`.

## 1. Prepare secrets

```bash
cp DevOps/k3s/secrets.env.example DevOps/k3s/secrets.env
```

Fill the values in `DevOps/k3s/secrets.env`.

## 2. Build images

```bash
bash DevOps/generate-images.sh --tag current
```

For local build smoke without push:

```bash
bash DevOps/generate-images.sh --tag local --no-push
```

## 3. Deploy

```bash
bash DevOps/k3s/deploy-to-vm.sh --image-tag current
```

Overrides:

```bash
DUTCHPAL_DOMAIN=dutchpal.lontray.art bash DevOps/k3s/deploy-to-vm.sh
SSH_HOST=ubuntu@lontray.art bash DevOps/k3s/deploy-to-vm.sh
SSH_KEY=~/.ssh/ssh-ovm-printmeart.key bash DevOps/k3s/deploy-to-vm.sh
```

## Notes

- Namespace defaults to `dutchpal`.
- The script does not modify `ecommbone`, `monitoring`, or `kube-system` resources.
- Traefik must already be installed with the IngressRoute CRD.
- `dutchpal.lontray.art` must point to the VM before external smoke checks pass.

## Current production routes

- UI: `https://dutchpal.lontray.art/`
- FastAPI agent: `https://dutchpal.lontray.art/dutchpal-api`
- .NET API: `https://dutchpal.lontray.art/dutchpal-v2-api`

The chart creates one DutchPal `IngressRoute` in the `dutchpal` namespace. It reuses the existing cluster Traefik installation and does not create a second Traefik instance.

## Post-deploy checks

```bash
curl -fsS https://dutchpal.lontray.art/dutchpal-api/health
curl -fsS https://dutchpal.lontray.art/dutchpal-v2-api/health
curl -fsS https://dutchpal.lontray.art/
curl -fsS -X POST https://dutchpal.lontray.art/dutchpal-api/chat \
  -H 'content-type: application/json' \
  --data '{"message":"Say only: ok"}'
```
