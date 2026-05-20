# Kubernetes Deployment (Helm)

This directory contains the Helm chart for running the NVIDIA Digital Twins for
Fluid Simulation blueprint on Kubernetes.

Docker Compose remains the primary local development path. Use this chart when
you need a cluster-native deployment or cloud validation path. MicroK8s is a
convenient local test cluster, but the chart is not tied to it.

## Scope

The chart is intentionally single-node:

- **Lite**: Kit + web, one GPU, cached inference from `data/cache/`.
- **Standard**: Kit + AeroNIM + web, two GPUs, live AeroNIM inference.
- **Not included**: multi-user session routing, load-balanced Kit replicas, or
  managed streaming control-plane packaging.

The browser must reach the Kit WebRTC ports on the same node that serves the
web UI. The Kit stream accepts one active client.

## Modes

| | Lite | Standard |
|---|---|---|
| Pods | kit, web | kit, aeronim, web |
| GPUs | 1 RTX-class GPU, >= 16 GB VRAM | 2 GPUs, or enough VRAM to schedule both pods |
| NGC account | Not required | Required for AeroNIM |
| Inference | Pre-baked cache staged by `rtdt-data` | Live AeroNIM / Triton |
| UI controls | Velocity + Spoiler cached; Mirrors/Rims restricted | Full control surface |

## Prerequisites

- Kubernetes v1.26+.
- NVIDIA GPU Operator or equivalent device plugin/runtime support.
- `helm` v3 and `kubectl` for normal clusters.
- `microk8s.helm3` and `microk8s.kubectl` only if using MicroK8s for local testing.
- A registry your cluster can pull from for cloud installs.
- `git lfs pull` before building images so cache and stage assets are real
  files, not LFS pointers.

## Validation Levels

| Level | Command | Proves | Does not prove |
|---|---|---|---|
| Render | `deploy/helm/test.sh` | Chart lint/template checks for both modes. | Runtime scheduling or image pulls. |
| Cluster smoke | `deploy/helm/test.sh --cluster --mode lite` | Install, rollout, and in-cluster service connectivity. | Browser WebRTC/rendering. |
| Local GPU cluster | `deploy/helm/test.sh --microk8s --mode lite` after image import | Local image startup, GPU scheduling, Kit + web wiring. MicroK8s is the documented example. | Registry pulls or cloud routing. |
| Cloud/standard | Install commands below | Registry, LoadBalancer, GPU Operator, AeroNIM path. | Managed control-plane integration. |

## Local Render Check

Run this before any cluster install:

```sh
deploy/helm/test.sh
```

The script runs `helm lint`, renders `lite` and `standard`, verifies NGC secret
wiring, confirms `lite` omits AeroNIM, and checks that invalid modes fail.

## Local Cluster Smoke Test

Use a local GPU-capable Kubernetes cluster for the first real test. The commands
below use MicroK8s because it is compact and matches the cluster shape used
during validation: single node, DNS, GPU support, and optionally MetalLB. Do not
deploy a separate streaming control plane for this chart.

Set up the cluster:

```sh
microk8s start
microk8s status --wait-ready
microk8s enable dns
microk8s enable gpu
```

Optional kubeconfig for manual commands:

```sh
mkdir -p ~/.kube
microk8s config > ~/.kube/microk8s-rtdt.yaml
export KUBECONFIG=~/.kube/microk8s-rtdt.yaml
```

Build and import local images:

```sh
git lfs pull
docker compose build kit web
docker build -f Dockerfile.data -t rtdt-data:latest .
docker build -f aeronim/Dockerfile.aeronim -t rtdt-aeronim:latest .

docker save \
  rtdt-kit-app:latest \
  rtdt-trame-app:latest \
  rtdt-data:latest \
  rtdt-aeronim:latest \
  -o /tmp/rtdt-fluid-sim-images.tar

microk8s ctr image import /tmp/rtdt-fluid-sim-images.tar
```

Install and test lite:

```sh
cd deploy/helm
./test.sh --microk8s --mode lite --timeout 30m
```

The script runs the render checks first, installs/upgrades the release, waits
for deployments, runs `helm test`, and prints the web URL.

On reused MicroK8s/Horde hosts, stale kubelet serving certificates can break
`helm test --logs` even when the test pod succeeded. In that case use:

```sh
./test.sh --microk8s --mode lite --timeout 30m --no-test-logs
```

To exercise `LoadBalancer` locally, enable MetalLB and override the web service:

```sh
HOST_IP=<microk8s-host-ip>
microk8s enable metallb:${HOST_IP}/32
./test.sh --microk8s --mode lite -- --set web.service.type=LoadBalancer
```

After lite passes, a two-GPU MicroK8s host can exercise standard mode:

```sh
NGC_API_KEY=<your-ngc-api-key> ./test.sh --microk8s --mode standard --timeout 45m
```

## Build And Push Images

Kubernetes needs four images:

- `rtdt-kit-app`: Kit/WebRTC app, built by Compose.
- `rtdt-trame-app`: web UI, built by Compose.
- `rtdt-data`: runtime data and USD stages, built from `Dockerfile.data`.
- `rtdt-aeronim`: AeroNIM plus this app's `rtwt` Triton model, built from
  `aeronim/Dockerfile.aeronim`.

```sh
git lfs pull
docker compose build kit web
docker build -f Dockerfile.data -t rtdt-data:latest .
docker build -f aeronim/Dockerfile.aeronim -t rtdt-aeronim:latest .

REG=<your-registry>
VERSION=0.1.0

for img in rtdt-kit-app rtdt-trame-app rtdt-data rtdt-aeronim; do
  docker tag  ${img}:latest ${REG}/${img}:${VERSION}
  docker push ${REG}/${img}:${VERSION}
done
```

`rtdt-data` replaces the host bind mounts used by Docker Compose. The kit pod
stages it under `/app/rtwt`; the AeroNIM pod stages the same payload under
`/opt/data` and `/opt/stages`, matching `aeronim/rtwt/1/model.py`.

## Install Lite

```sh
helm upgrade --install rtdt-fluid-sim ./deploy/helm \
  --namespace rtdt-fluid-sim \
  --create-namespace \
  --set mode=lite \
  --set kit.image.repository=${REG}/rtdt-kit-app \
  --set kit.image.tag=${VERSION} \
  --set web.image.repository=${REG}/rtdt-trame-app \
  --set web.image.tag=${VERSION} \
  --set data.image.repository=${REG}/rtdt-data \
  --set data.image.tag=${VERSION} \
  --set web.service.type=LoadBalancer
```

Watch rollout and find the URL:

```sh
kubectl -n rtdt-fluid-sim get pods -w
kubectl -n rtdt-fluid-sim get svc rtdt-fluid-sim-web
```

First launch can take several minutes while Kit compiles shaders.

## Install Standard

Standard requires enough GPUs for both Kit and AeroNIM, a custom `rtdt-aeronim`
image built from `aeronim/Dockerfile.aeronim`, and an NGC API key available to
the AeroNIM runtime.

```sh
export NGC_API_KEY=<your-ngc-api-key>

helm upgrade --install rtdt-fluid-sim ./deploy/helm \
  --namespace rtdt-fluid-sim \
  --create-namespace \
  --set mode=standard \
  --set-string ngcSecret.apiKey="${NGC_API_KEY}" \
  --set kit.image.repository=${REG}/rtdt-kit-app \
  --set kit.image.tag=${VERSION} \
  --set web.image.repository=${REG}/rtdt-trame-app \
  --set web.image.tag=${VERSION} \
  --set data.image.repository=${REG}/rtdt-data \
  --set data.image.tag=${VERSION} \
  --set aeronim.image.repository=${REG}/rtdt-aeronim \
  --set aeronim.image.tag=${VERSION} \
  --set web.service.type=LoadBalancer
```

AeroNIM can take 5-10 minutes to load after the image is pulled. The kit pod's
`wait-for-aeronim` init container waits for `/v2/health/ready`.

```sh
kubectl -n rtdt-fluid-sim logs -l app.kubernetes.io/component=aeronim -f
kubectl -n rtdt-fluid-sim get pods -w
```

## Private Registries

If `rtdt-kit-app`, `rtdt-trame-app`, `rtdt-data`, or `rtdt-aeronim` are in a
private registry, create one pull secret and reference it for each image:

```sh
kubectl -n rtdt-fluid-sim create secret docker-registry my-registry-creds \
  --docker-server=<registry-host> \
  --docker-username=<user> \
  --docker-password=<pass>

helm upgrade --install rtdt-fluid-sim ./deploy/helm \
  ...other flags... \
  --set-json 'kit.imagePullSecrets=[{"name":"my-registry-creds"}]' \
  --set-json 'web.imagePullSecrets=[{"name":"my-registry-creds"}]' \
  --set-json 'data.imagePullSecrets=[{"name":"my-registry-creds"}]' \
  --set-json 'aeronim.imagePullSecrets=[{"name":"my-registry-creds"}]'
```

The default standard path uses a custom `rtdt-aeronim` image. If you intentionally
pull the upstream NIM image directly from `nvcr.io`, reference the generated NGC
pull secret with `--set-json 'aeronim.imagePullSecrets=[{"name":"ngc-docker-reg-secret"}]'`.

## NGC Secret Handling

Do not put real API keys in `values.yaml`.

- **Development**: `MODE=standard NGC_API_KEY=... deploy/helm/deploy.sh`
  forwards the key with `--set-string` and rejects obvious placeholders. This is
  convenient, but Helm can retain rendered secret data in the release record.
- **CI smoke tests**: `--set-string ngcSecret.apiKey=$NGC_API_KEY` is acceptable only
  for short-lived test clusters managed from a CI secret store.
- **Production**: set `ngcSecret.create=false` and manage secrets with
  SealedSecrets, SOPS, External Secrets Operator, Vault, or equivalent.

When `ngcSecret.create=false`, pre-create:

- the Opaque secret containing `NGC_API_KEY`; set `ngcSecret.apiSecretName` if
  you do not want the default `<release>-rtdt-fluid-sim-ngc-api-key`;
- any image pull secrets referenced by `kit`, `web`, `data`, or `aeronim`.

## Networking

The web service defaults to `NodePort` on port `30080`. Use
`web.service.type=LoadBalancer` for most cloud tests.

Kit WebRTC uses host ports by default:

- TCP `49100` for signaling.
- UDP `1024` for media.
- TCP/UDP `47995-48012` and `49000-49007` for WebRTC transport/data.

`kit.hostPorts.enabled=true` matches Docker Compose and lets the browser reach
Kit directly on the node IP. If your platform disallows host ports, set it to
`false` and provide equivalent platform routing for those Kit ports.

## Persistent Omniverse Cache

By default, Kit cache directories use `emptyDir`; shader compilation repeats
when the pod is rescheduled. Enable PVCs if you want cache persistence:

```sh
helm upgrade --install rtdt-fluid-sim ./deploy/helm \
  ...other flags... \
  --set kit.persistence.ovCache.enabled=true \
  --set kit.persistence.ovCache.size=20Gi \
  --set kit.persistence.ovCache.storageClass=<storage-class>
```

The same pattern is available for `kit.persistence.ovLocalShare`. PVCs are
retained on uninstall.

## Pass Criteria

Lite:

- Kit and web deployments become `Available`.
- `helm test` succeeds.
- The web URL loads and connects to the Kit stream.
- Velocity and Spoiler update cached results.
- Flow, Streamlines, Volume, and Slice render.

Standard:

- Kit, AeroNIM, and web deployments become `Available`.
- `helm test` succeeds, including AeroNIM readiness.
- Full UI controls drive live inference.
- Kit logs show cache misses on first combinations and cache hits on repeats.

## Cloud Portability Notes

This chart packages this repository's own Kubernetes runtime. Local MicroK8s
testing is useful for cluster setup validation, not for a separate managed
streaming control plane.

To keep the chart portable toward managed GPU environments:

- push images to a real registry; do not depend on MicroK8s image imports;
- externalize secrets instead of committing values files with credentials;
- keep Kit, web, data, and AeroNIM images independently configurable;
- expect managed platforms to replace `hostPort` with their own routing;
- validate standard mode with the same AeroNIM image tag and NGC org you intend
  to use later.

Managed application CRDs, profiles, external deployment workflows, and viewer
integration are separate work.

## Troubleshooting

### ImagePullBackOff

Check image names, tags, registry reachability, and pull secrets:

```sh
kubectl -n rtdt-fluid-sim describe pod <pod-name>
```

For standard mode, `nvcr.io` failures usually mean the NGC key or image-pull
secret is wrong.

### `libGLX_nvidia.so.0 not found`

The GPU runtime is not mounted into the container. Install or repair the NVIDIA
GPU Operator/device plugin on the node. On some workstation GPUs, runtime-
compiled driver mode may be required.

### AeroNIM Stuck Or Slow

The AeroNIM image is large and model load can take several minutes. Watch:

```sh
kubectl -n rtdt-fluid-sim describe pod -l app.kubernetes.io/component=aeronim
kubectl -n rtdt-fluid-sim logs -l app.kubernetes.io/component=aeronim --tail=200
```

### Kit Stuck In `wait-for-aeronim`

The kit init container waits until AeroNIM returns `/v2/health/ready`. Confirm
the AeroNIM pod is running, the NGC key is valid, and the cluster can reach
`nvcr.io`.

### Controls Work But Live Inference Does Not

Readiness only proves Triton loaded the model. For standard mode, confirm the
AeroNIM pod also staged the data image:

```sh
kubectl -n rtdt-fluid-sim describe pod -l app.kubernetes.io/component=aeronim
```

The pod should have a `stage-data` init container and mounts at `/opt/data` and
`/opt/stages`. If logs mention `Could not load sublayer
@/opt/stages/BaseCAEVariants.usda@`, the data image is not mounted correctly.

### Browser Does Not Connect To Stream

Check, in order:

1. Client network can reach the node IP and Kit ports in [Networking](#networking).
2. Kit finished first-launch shader compilation.
3. Web pod completed its `wait-for-kit` init container.

## Uninstall

```sh
helm uninstall rtdt-fluid-sim -n rtdt-fluid-sim
kubectl delete namespace rtdt-fluid-sim
```

If you enabled persistence and want to reclaim storage before deleting the
namespace:

```sh
kubectl -n rtdt-fluid-sim delete pvc -l app.kubernetes.io/instance=rtdt-fluid-sim
```

## Cloud Test Report Template

Record the following for any cloud or standard-mode validation:

1. Cloud, instance type, GPU model/count, GPU Operator version, Kubernetes version.
2. Image registry and image tags used.
3. Mode tested: `lite` or `standard`.
4. Time from `helm upgrade --install` to all deployments `Available`.
5. Time from first browser load to visible stream.
6. `kubectl get pods -n <namespace>` at steady state.
7. Pass/fail against [Pass Criteria](#pass-criteria).
8. Any failing pod `describe` output and relevant logs.
