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
| digital-twins | coturn | `quay.io/coturn/coturn:4.7.0` | 0 | 5349 (TURNS) | TURN relay for WebRTC UDP-over-TCP tunneling |

**Data flow:** Browser &rarr; Web (React UI) &rarr; Kit (WebRTC stream + API proxy)
&rarr; Aero NIM (inference) &rarr; Kit (renders results) &rarr; Browser (live 3D viewport).
WebRTC media is tunneled through coturn (TURN relay over TLS/TCP).

**Total resources:** 4 pods, 2 GPUs, ~110 GB storage (PVCs for Omniverse caches
and NIM model).

### NIM Operator Components (Optional)

The Aero NIM can optionally be managed by the NIM Operator as a NIMCache +
NIMService pair. However, the DoMINO Automotive Aero NIM has an internal port
conflict when managed by the NIM Operator (`TRITON_HTTP_PORT 8080` conflicts
with its API server), so the default OpenShift overlay uses a standard
Deployment instead (`aeronim.enabled: true`, `nimOperator.domino-automotive-aero.enabled: false`).

### WebRTC Streaming Architecture

This blueprint uses Omniverse Kit App Streaming with WebRTC. The web frontend
proxies HTTP API and WebSocket traffic to Kit via Nginx (`/api/`, `/ws/`), but
the actual video stream uses UDP connections on ports 47995-48012 and
49000-49007. **OpenShift Routes cannot handle UDP traffic** (Layer 7, TCP only),
so the deployment includes a **coturn TURN relay** that tunnels WebRTC UDP
media over TLS/TCP:

1. **Signaling** (WebSocket): Browser &rarr; Kit edge Route (port 443) &rarr; Kit pod (port 49100)
2. **Media** (WebRTC/UDP tunneled over TCP): Browser &rarr; coturn passthrough Route (port 443) &rarr; coturn pod (port 5349, TLS termination) &rarr; Kit pod (UDP internally)

The client-side code monkey-patches `RTCPeerConnection` to inject the TURN
server and force `iceTransportPolicy: "relay"`, ensuring all media goes through
the tunnel. This is only activated when a TURN config is present (non-OpenShift
deployments are unaffected).

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
| Aero NIM management | Docker container with `runtime: nvidia` | Kubernetes Deployment (NIM Operator optional) | Standard Deployment with GPU resources and /dev/shm |
| External access (web) | Host port mapping | OpenShift Route with TLS | Production-grade HTTPS ingress |
| External access (Kit streaming) | Host port mapping | ClusterIP + coturn TURN relay | WebRTC UDP tunneled over TLS/TCP via coturn; Kit signaling exposed through edge Route |
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
- cert-manager operator (for coturn TLS certificate provisioning)
- NIM Operator (optional, for NIMCache/NIMService management of the Aero NIM)
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
| `openshift.routes.kit.enabled` | `false` | Create an edge Route for Kit WebSocket signaling |
| `openshift.routes.coturn.enabled` | `false` | Create a passthrough Route for coturn TURN relay |
| `openshift.scc.create` | `false` | Create custom SCC and RoleBinding |
| `openshift.scc.priority` | `10` | SCC priority |

### coturn Block (`coturn:`)

| Key | Default | Description |
|-----|---------|-------------|
| `coturn.enabled` | `false` | Deploy the coturn TURN relay |
| `coturn.auth.username` | `turnuser` | TURN authentication username |
| `coturn.auth.password` | `changeme` | TURN authentication password (set via `--set`) |
| `coturn.tls.secretName` | `""` | TLS secret name for coturn (must pre-exist) |
| `coturn.realm` | `turn.local` | TURN realm |

### Stream Config Block (`streamConfig:`)

| Key | Default | Description |
|-----|---------|-------------|
| `streamConfig.signalingServer` | `""` | Kit Route hostname for WebSocket signaling |
| `streamConfig.signalingPort` | `443` | Signaling port (443 via Route) |
| `streamConfig.forceWSS` | `true` | Force secure WebSocket |
| `streamConfig.turn.urls` | `""` | TURN server URL (e.g. `turns:hostname:443?transport=tcp`) |
| `streamConfig.turn.username` | `""` | TURN username |
| `streamConfig.turn.credential` | `""` | TURN credential |

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

### 3. Create coturn TLS Certificate

The coturn TURN relay needs a TLS certificate matching its Route hostname.
Use cert-manager (if installed) or create the secret manually:

**Option A: cert-manager (recommended)**

```bash
cat <<EOF | oc apply -n digital-twins -f -
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: rtwt-coturn-tls
spec:
  secretName: rtwt-coturn-tls
  issuerRef:
    name: letsencrypt-production   # adjust to your ClusterIssuer
    kind: ClusterIssuer
  dnsNames:
    - rtwt-turn-digital-twins.apps.<cluster-domain>
EOF
```

**Option B: Manual**

```bash
oc create secret tls rtwt-coturn-tls \
  --cert=tls.crt --key=tls.key -n digital-twins
```

### 4. Install the Chart

```bash
cd deploy/helm/digital-twins-fluid-sim/

helm install rtwt . \
  -f values.yaml \
  -f values-openshift.yaml \
  --set coturn.auth.password="<choose-a-password>" \
  -n digital-twins
```

This creates:
- 1 Aero NIM Deployment (AI inference with GPU)
- 1 Kit Deployment (Omniverse streaming with GPU)
- 1 Web Deployment (Nginx + React frontend)
- 1 coturn Deployment (TURN relay for WebRTC UDP-over-TCP)
- 3 OpenShift Routes (web edge, Kit signaling edge, coturn passthrough)
- 1 Custom SCC + RoleBinding (privileged access for Kit and NIM)
- 2 PVCs (Omniverse cache and local-share)
- 2 ConfigMaps (Nginx config, stream-config.json)

### 5. Configure Stream Config

After install, get the Route hostnames and update the stream config so the
web frontend knows how to reach Kit signaling and the TURN relay:

```bash
KIT_HOST=$(oc get route rtwt-kit -n digital-twins -o jsonpath='{.spec.host}')
TURN_HOST=$(oc get route rtwt-turn -n digital-twins -o jsonpath='{.spec.host}')
TURN_PASS="<same-password-from-step-4>"

helm upgrade rtwt . \
  -f values.yaml \
  -f values-openshift.yaml \
  --set coturn.auth.password="${TURN_PASS}" \
  --set streamConfig.signalingServer="${KIT_HOST}" \
  --set streamConfig.turn.urls="turns:${TURN_HOST}:443?transport=tcp" \
  --set streamConfig.turn.username="turnuser" \
  --set streamConfig.turn.credential="${TURN_PASS}" \
  -n digital-twins
```

### 6. Monitor Startup

The Aero NIM downloads the model on first start (10-30 minutes). Kit compiles
shaders on first launch (up to 30 minutes; cached in PVC for subsequent starts).

```bash
# Watch all pods
oc get pods -n digital-twins -w

# Monitor Aero NIM model download
oc logs -f deploy/rtwt-aeronim -n digital-twins

# Monitor Kit shader compilation
oc logs -f deploy/rtwt-kit -n digital-twins
```

Wait until all 4 pods show `Running 1/1`.

## Verification

### Check All Pods

```bash
oc get pods -n digital-twins
```

Expected pods:

```
NAME                              READY   STATUS    RESTARTS   AGE
rtwt-aeronim-xxxxxxxxxx-xxxxx     1/1     Running   0          5m
rtwt-coturn-xxxxxxxxxx-xxxxx      1/1     Running   0          5m
rtwt-kit-xxxxxxxxxx-xxxxx         1/1     Running   0          5m
rtwt-web-xxxxxxxxxx-xxxxx         1/1     Running   0          5m
```

### Check Routes

```bash
oc get routes -n digital-twins
```

Expected routes: `rtwt-web` (edge), `rtwt-kit` (edge), `rtwt-turn` (passthrough).

### Health Checks

```bash
# Aero NIM health
oc exec deploy/rtwt-kit -n digital-twins -- \
  curl -s http://rtwt-aeronim:8080/v1/health/ready

# Web frontend
oc exec deploy/rtwt-web -n digital-twins -- \
  curl -s http://localhost/

# Stream config served correctly
oc exec deploy/rtwt-web -n digital-twins -- \
  curl -s http://localhost/stream-config.json
```

## Accessing the UI

### Web Frontend (via Route)

```bash
WEB_HOST=$(oc get route rtwt-web -n digital-twins -o jsonpath='{.spec.host}')
KIT_HOST=$(oc get route rtwt-kit -n digital-twins -o jsonpath='{.spec.host}')
echo "https://${WEB_HOST}/?server=${KIT_HOST}&width=1920&height=1080&fps=60"
```

Open that URL in your browser. The React UI loads, fetches `/stream-config.json`
(which contains the TURN relay details), and establishes a WebRTC connection to
Kit through the coturn TURN relay.

If the stream does not connect, verify:
1. All 4 pods are `Running 1/1`
2. The `streamConfig` values were set correctly (Step 5 above)
3. The coturn TLS certificate is valid: `oc get certificate rtwt-coturn-tls -n digital-twins`
4. Check browser console for `[OmniverseAPI] TURN relay injected:` message

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

**What happened:** OpenShift Routes only handle HTTP(S) traffic (Layer 7, TCP).
Omniverse Kit App Streaming uses WebRTC which requires UDP on ports 47995-48012
and 49000-49007 for the media stream. There is no mechanism in the Route API to
expose UDP traffic. Inside the cluster everything works fine; the problem is
purely about getting external browser traffic to Kit's UDP ports.

**Services affected:** Kit (WebRTC streaming to browser)

**Fix:** Added a coturn TURN relay server that tunnels WebRTC UDP media over
TLS/TCP. The browser connects to coturn through a passthrough TLS Route, and
coturn relays the media to Kit's pod over UDP internally within the cluster.
The client-side JavaScript monkey-patches `RTCPeerConnection` to inject the
TURN server and force `iceTransportPolicy: "relay"`. Kit uses ClusterIP (not
NodePort). This approach aligns with NVIDIA's newer Kit App-Streaming (KAS)
architecture direction.

**Key insight:** The NVIDIA streaming library rewrites ICE candidate IPs using
the `mediaServer` config parameter. When a TURN relay is configured, the
`mediaServer` parameter must be omitted so coturn can reach Kit's actual pod IP
over UDP internally, rather than trying to route through the external Route
hostname.

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

### 9. Aero NIM Shared Memory Too Small

**What happened:** The Aero NIM's Triton inference server requires more than the
default 64 MB of `/dev/shm` for shared memory. The container crashes with
`Failed to increase the shared memory pool size`.

**Services affected:** Aero NIM

**Fix:** The Helm chart mounts an `emptyDir` volume at `/dev/shm` with
`sizeLimit` set via `aeronim.shmSize` (default 2Gi).

### 10. TOKENIZERS_PARALLELISM Race Condition

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
