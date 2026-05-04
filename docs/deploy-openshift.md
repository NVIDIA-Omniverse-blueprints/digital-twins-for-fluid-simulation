# Deploying the Real-Time Wind Tunnel Digital Twin on Red Hat OpenShift AI

## What We're Deploying

The NVIDIA Omniverse Blueprint for Real-Time CAE Digital Twins combines an AI
surrogate model, a GPU-accelerated 3D renderer, and a web frontend into an
interactive wind tunnel for vehicle aerodynamics.

| Namespace | Component | Image | GPU | Port | Purpose |
|-----------|-----------|-------|-----|------|---------|
| digital-twins | Aero NIM | `nvcr.io/nim/nvidia/domino-automotive-aero:2.0.0` | 1 | 8080 | DoMINO aerodynamic inference |
| digital-twins | Kit (Omniverse) | `rtdt-kit-app:latest` | 1 | 49100 (HTTP), 47995–48012, 49000–49007 (WebRTC) | USD scene rendering + WebRTC streaming |
| digital-twins | Web | `rtdt-web-app:latest` | 0 | 80 | React UI + Nginx reverse proxy to Kit |

**Data flow:** Browser &rarr; Web (React UI) &rarr; Kit (WebRTC stream + API proxy)
&rarr; Aero NIM (inference) &rarr; Kit (renders results) &rarr; Browser (live 3D viewport)

**Total resources:** 3 pods, 2 GPUs, ~110 GB storage (PVCs for Omniverse caches
and NIM model).

### NIM Operator Components

When deployed with the NIM Operator (recommended on OpenShift), the Aero NIM is
managed as a pair of custom resources:

- **NIMCache** &mdash; downloads and caches the DoMINO model on a PVC. Annotated
  with `helm.sh/resource-policy: keep` to survive upgrades and uninstalls.
- **NIMService** &mdash; runs the inference server, references its NIMCache for
  model storage, manages replicas, GPU allocation, and health probes.

### WebRTC Streaming Architecture

This blueprint uses Omniverse Kit App Streaming with WebRTC. The web frontend
proxies HTTP API and WebSocket traffic to Kit via Nginx (`/api/`, `/ws/`), but
the actual video stream uses direct UDP connections on ports 47995–48012 and
49000–49007. **OpenShift Routes cannot handle UDP traffic**, so the Kit service
must remain as NodePort (or LoadBalancer) even when OpenShift Routes are used
for the web frontend.

## Tested Hardware

| Parameter | Value |
|-----------|-------|
| Platform | Red Hat OpenShift AI (RHOAI) 4.14+ |
| GPU nodes | 1+ nodes with NVIDIA RTX GPUs (L40/L40s, A6000, or RTX 6000 Pro) |
| GPUs per node | 2+ (one for Kit, one for Aero NIM) |
| Total GPUs | 2 |
| VRAM | 40 GB+ per GPU |
| CPU | 32+ cores |
| RAM | 128 GB+ |
| Storage | 100 GB+ (dynamic provisioning recommended) |
| API keys | NVIDIA NGC API key |

**Minimum for reproduction:** 2 &times; NVIDIA L40s / A6000 GPUs with 40 GB+
VRAM each, 128 GB RAM, 100 GB storage.

## What's Different from Upstream

| Area | Upstream Default | OpenShift Deployment | Impact |
|------|-----------------|---------------------|--------|
| Orchestration | Docker Compose | Helm chart on Kubernetes | Declarative lifecycle management |
| Aero NIM management | Docker container with `runtime: nvidia` | NIM Operator (NIMCache + NIMService) | Automated model download, cache lifecycle |
| External access (web) | Host port mapping | OpenShift Route with TLS | Production-grade HTTPS ingress |
| External access (Kit streaming) | Host port mapping | NodePort Service | WebRTC UDP requires direct connectivity |
| Security context | `privileged: true` in Compose | Custom SCC with privileged + host IPC | Compatible with OpenShift SCC enforcement |
| Volume management | Docker named volumes | Dynamic PVCs | Cluster-native storage provisioning |
| Kit image | Built locally via `build-docker.sh` | Pre-built and pushed to registry | Must push to accessible registry before deploy |

## Prerequisites

### CLI Tools

- `oc` (OpenShift CLI) v4.14+
- `helm` v3.12+
- `docker` (for building and pushing images)

### Cluster Requirements

- OpenShift 4.14+ with NVIDIA GPU Operator installed
- NIM Operator installed (provides `apps.nvidia.com/v1alpha1` API)
- At least 2 available GPUs on the same or different nodes

### Build and Push Images

The Kit and Web images must be built and pushed to a registry accessible from
your OpenShift cluster. The Aero NIM image is pulled directly from `nvcr.io`.

```bash
# Build images locally
./build-docker.sh

# Tag and push to your registry
export REGISTRY=your-registry.example.com/digital-twins
docker tag rtdt-kit-app:latest ${REGISTRY}/rtdt-kit-app:latest
docker tag rtdt-web-app:latest ${REGISTRY}/rtdt-web-app:latest
docker push ${REGISTRY}/rtdt-kit-app:latest
docker push ${REGISTRY}/rtdt-web-app:latest
```

Update `values-openshift.yaml` to reference your registry:

```yaml
kit:
  image:
    repository: your-registry.example.com/digital-twins/rtdt-kit-app
web:
  image:
    repository: your-registry.example.com/digital-twins/rtdt-web-app
```

### Verify GPU Availability

```bash
oc get nodes -l nvidia.com/gpu.present=true -o custom-columns=\
NAME:.metadata.name,\
GPUS:.status.capacity.nvidia\.com/gpu,\
ALLOCATABLE:.status.allocatable.nvidia\.com/gpu
```

### Resource Requirements

| Resource | Aero NIM | Kit | Web | Total |
|----------|----------|-----|-----|-------|
| GPU | 1 | 1 | 0 | 2 |
| Model storage | ~50 Gi | — | — | ~50 Gi |
| Cache storage | — | 50 Gi (ov-cache) + 10 Gi (ov-local-share) | — | ~60 Gi |

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NGC_API_KEY` | Yes | — | NGC API key for pulling NIM images and model downloads |

### OpenShift Block (`openshift:`)

| Key | Default | Description |
|-----|---------|-------------|
| `openshift.enabled` | `false` | Master toggle for all OpenShift resources |
| `openshift.routes.web.enabled` | `false` | Create a Route for the web frontend |
| `openshift.routes.web.host` | `""` | Hostname (auto-generated if empty) |
| `openshift.routes.web.tls.termination` | `edge` | TLS termination strategy |
| `openshift.scc.create` | `false` | Create custom SCC and RoleBinding |
| `openshift.scc.priority` | `10` | SCC priority |

### NIM Operator Block (`nimOperator:`)

The Aero NIM (`nimOperator.domino-automotive-aero`) supports:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Deploy via NIM Operator instead of raw Deployment |
| `replicas` | `1` | Number of inference replicas |
| `image.repository` | `nvcr.io/nim/nvidia/domino-automotive-aero` | NGC container image |
| `image.tag` | `2.0.0` | Image version |
| `resources.limits.nvidia.com/gpu` | `1` | GPU allocation |
| `storage.pvc.size` | `50Gi` | Model cache PVC size |
| `storage.pvc.storageClass` | `""` | StorageClass (cluster default if empty) |
| `expose.service.port` | `8080` | Service port |

## Deployment

### 1. Create Namespace

```bash
oc new-project digital-twins
```

### 2. Create NGC Secrets

The NGC registry secret must carry Helm ownership labels so `helm install` can
adopt it:

```bash
export NGC_API_KEY="<your-ngc-api-key>"

oc create secret docker-registry ngc-secret \
  --docker-server=nvcr.io \
  --docker-username='$oauthtoken' \
  --docker-password="${NGC_API_KEY}" \
  -n digital-twins

oc label secret ngc-secret \
  app.kubernetes.io/managed-by=Helm -n digital-twins
oc annotate secret ngc-secret \
  meta.helm.sh/release-name=rtwt \
  meta.helm.sh/release-namespace=digital-twins -n digital-twins
```

Create the NGC API secret for the NIM Operator:

```bash
oc create secret generic ngc-api \
  --from-literal=NGC_API_KEY="${NGC_API_KEY}" \
  -n digital-twins

oc label secret ngc-api \
  app.kubernetes.io/managed-by=Helm -n digital-twins
oc annotate secret ngc-api \
  meta.helm.sh/release-name=rtwt \
  meta.helm.sh/release-namespace=digital-twins -n digital-twins
```

### 3. Install the Chart

```bash
cd deploy/helm/digital-twins-fluid-sim/

helm install rtwt . \
  -f values.yaml \
  -f values-openshift.yaml \
  -n digital-twins
```

This creates:
- 1 NIMCache resource (triggers Aero NIM model download)
- 1 NIMService resource (runs Aero NIM inference after cache is ready)
- 1 Kit Deployment (Omniverse streaming with GPU)
- 1 Web Deployment (Nginx + React frontend)
- 1 OpenShift Route (web frontend with edge TLS)
- 1 Custom SCC + RoleBinding (privileged access for Kit and NIM)
- 2 PVCs (Omniverse cache and local-share)
- 1 ConfigMap (Nginx config with Kit service discovery)

### 4. Monitor NIM Model Download

The NIMCache downloads the DoMINO model from NGC. This can take 10–30 minutes
depending on network speed.

```bash
oc get nimcache -n digital-twins -w
```

Wait until the cache shows `Ready`:

```
NAME             STATUS   AGE
aeronim-cache    Ready    15m
```

## Verification

### Check All Pods

```bash
oc get pods -n digital-twins
```

Expected pods:

```
NAME                           READY   STATUS    RESTARTS   AGE
aeronim-0                      1/1     Running   0          5m
rtwt-kit-xxxxxxxxxx-xxxxx      1/1     Running   0          5m
rtwt-web-xxxxxxxxxx-xxxxx      1/1     Running   0          5m
```

### Check NIMService Status

```bash
oc get nimservice -n digital-twins
```

### Health Checks

```bash
# Aero NIM health
oc exec deploy/rtwt-kit -n digital-twins -- \
  curl -s http://aeronim:8080/v1/health/ready

# Web frontend
oc exec deploy/rtwt-web -n digital-twins -- \
  curl -s http://localhost/
```

## Accessing the UI

### Web Frontend (via Route)

```bash
oc get route rtwt-web -n digital-twins -o jsonpath='{.spec.host}'
```

Open `https://<route-hostname>` in your browser. The React UI loads and
establishes a WebRTC connection to the Kit streaming service.

### Kit WebRTC Streaming (via NodePort)

The Kit service exposes WebRTC streaming ports as NodePorts. Determine the node
IP and allocated ports:

```bash
# Get the node where Kit is running
oc get pod -l app.kubernetes.io/component=kit -n digital-twins \
  -o jsonpath='{.items[0].status.hostIP}'

# Get the allocated NodePorts
oc get svc rtwt-kit -n digital-twins
```

The web frontend must be configured to connect to the Kit streaming endpoint.
If the WebRTC connection does not establish, verify that:
1. The Kit NodePort ports are reachable from the client browser
2. Firewall rules allow UDP traffic on the allocated NodePorts
3. The Kit pod has GPU access and started successfully

## Testing End-to-End

Pods being `Running` does not mean the pipeline works. Validate the full flow:

1. **Open the web UI** via the Route URL
2. **Wait for the 3D scene to load** — first launch compiles shaders (can take
   up to 30 minutes; subsequent launches are ~2 minutes)
3. **Modify a vehicle parameter** (e.g., toggle the spoiler)
4. **Verify inference results update** — the aerodynamic visualization should
   change in real-time
5. **Test different visualization modes** — Curve Trace, Volume Trace, Slice Planes

If the scene loads but inference does not work, check the Aero NIM pod logs:

```bash
oc logs -f deploy/aeronim -n digital-twins
```

## OpenShift-Specific Challenges and Solutions

### 1. Kit Requires Privileged Container Access

**What happened:** The Omniverse Kit application requires `privileged: true`
for GPU/Vulkan rendering. It needs access to the NVIDIA GPU driver, Vulkan ICD
loader, and host GPU devices. OpenShift's default `restricted` SCC blocks
privileged containers.

**Error:** Pod fails to start; Kit startup script reports
`Fatal Error: Can't find libGLX_nvidia.so.0...`

**Services affected:** Kit

**Fix:** The `openshift.yaml` template creates a custom SCC
(`<release>-scc`) that allows privileged containers, host IPC, and host
ports. A RoleBinding grants this SCC to the `default` ServiceAccount.

### 2. Aero NIM Requires Host IPC

**What happened:** The upstream Docker Compose runs the Aero NIM with
`ipc: host` for CUDA inter-process communication. The default OpenShift
`restricted` SCC blocks host IPC access.

**Services affected:** Aero NIM (Deployment path)

**Fix:** The custom SCC includes `allowHostIPC: true`. When using the NIM
Operator path, the NIMService handles IPC requirements directly.

### 3. WebRTC Streaming Cannot Use OpenShift Routes

**What happened:** OpenShift Routes only handle HTTP(S) traffic. Omniverse Kit
App Streaming uses WebRTC which requires direct UDP connectivity on ports
47995–48012 and 49000–49007 for the media stream.

**Services affected:** Kit (WebRTC streaming to browser)

**Fix:** The Kit service uses `type: NodePort` instead of ClusterIP. The web
frontend Route handles the HTML/API/WebSocket traffic, while the browser
connects directly to Kit's NodePorts for the WebRTC media stream. Ensure
firewall rules allow UDP traffic on the allocated NodePort range.

### 4. GPU Scheduling and Tolerations

**What happened:** GPU nodes in OpenShift clusters often carry taints
(`nvidia.com/gpu=present:NoSchedule`) to prevent non-GPU workloads from
scheduling there.

**Services affected:** Kit, Aero NIM

**Fix:** Add tolerations in the values overlay:

```yaml
kit:
  tolerations:
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule

nimOperator:
  domino-automotive-aero:
    tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
```

### 5. Kit and Web Images Must Be Pre-Built

**What happened:** Unlike the other NIM-only blueprints where all images come
from NGC, this blueprint has two custom images (`rtdt-kit-app`, `rtdt-web-app`)
that must be built from the repo's Dockerfiles and pushed to a registry
accessible from the OpenShift cluster.

**Services affected:** Kit, Web

**Fix:** Build images locally with `./build-docker.sh`, then tag and push to
your container registry. Update the `kit.image.repository` and
`web.image.repository` values to point to your registry.

### 6. Nginx Upstream Must Match Kit Service Name

**What happened:** The original `nginx.conf` hardcodes `server kit:49100` as
the upstream. In Kubernetes, the Kit service name includes the Helm release
prefix (e.g., `rtwt-kit`).

**Services affected:** Web (Nginx proxy to Kit)

**Fix:** The Helm chart templates the nginx config via a ConfigMap
(`web-configmap.yaml`) that dynamically resolves the Kit service name using
`{{ include "digital-twins-fluid-sim.fullname" . }}-kit`. This is mounted
into the Nginx container, replacing the hardcoded upstream.

### 7. NGC Secret Ownership by Helm

**What happened:** If NGC secrets are created with `oc create secret` before
`helm install`, Helm refuses to adopt them during install or upgrade.

**Error:** `Error: rendered manifests contain a resource that already exists`

**Services affected:** All (secrets are shared)

**Fix:** Pre-label secrets with Helm ownership metadata before install:

```bash
oc label secret <name> app.kubernetes.io/managed-by=Helm
oc annotate secret <name> \
  meta.helm.sh/release-name=rtwt \
  meta.helm.sh/release-namespace=digital-twins
```

### 8. Initial Shader Compilation Takes Up to 30 Minutes

**What happened:** On the very first launch, Omniverse Kit compiles shaders
for the scene. This is a one-time operation — compiled shaders are cached in
the `ov-cache` PVC. However, during this time the UI shows a blank grey/black
screen and users may think the deployment failed.

**Services affected:** Kit

**Fix:** Document the expected wait time. Monitor Kit logs with
`oc logs -f deploy/rtwt-kit` to track shader compilation progress. Ensure
the `ov-cache` PVC persists across pod restarts to avoid re-compilation.

### 9. TOKENIZERS_PARALLELISM Race Condition

**What happened:** NIM containers using HuggingFace tokenizers may hit a thread
pool race condition, causing startup failures.

**Services affected:** Aero NIM

**Fix:** Set `TOKENIZERS_PARALLELISM=false` in the NIM Operator env config.
The `values-openshift.yaml` overlay includes this preventively.

## Cleanup

Remove the Helm release:

```bash
helm uninstall rtwt -n digital-twins
```

**Important:** NIMCache PVCs persist after uninstall due to
`helm.sh/resource-policy: keep`. This is intentional — model downloads are
expensive. To remove them manually:

```bash
oc delete nimcache --all -n digital-twins
oc delete pvc -l app.kubernetes.io/managed-by=nim-operator -n digital-twins
```

Remove the Omniverse cache PVCs:

```bash
oc delete pvc rtwt-ov-cache rtwt-ov-local-share -n digital-twins
```

Delete the namespace (removes all remaining resources):

```bash
oc delete project digital-twins
```
