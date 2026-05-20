# AWS CDK Deployment

## Architecture

![AWS Architecture](doc/CAE-on-AWS-arch.png)

Two EC2 instances are deployed by default (split mode):

| Stack | Instance | Runs |
|---|---|---|
| `OmniverseCAENimStack` | g5.xlarge | AeroNIM inference server (`aeronim`) |
| `OmniverseCAEComputeStack` | g5.2xlarge | Kit streaming app + Trame web frontend |

An S3 bucket (`OmniverseCAERepoArtifactStack`) holds a snapshot of the local
repository. Both EC2 instances pull source from there instead of cloning from
git — so the local state you deploy is exactly what runs in the cloud.

Single-instance mode (`-c splitDeployment=false`) runs everything on one
g5.4xlarge and skips the NIM stack.

---

## Prerequisites

**Tools**
- AWS CLI v2 with credentials configured (`AWS_ACCOUNT_ID`, `AWS_REGION` exported)
- Node.js ≥ 18 and `npm`
- Python 3.10+

**CDK CLI** — must be v2.1120.0 or newer (schema v53):
```bash
npm install -g aws-cdk   # or: npm install aws-cdk --prefix ~/.local
cdk --version            # must print 2.1120.0 or higher
```

**Python virtual environment** (run once from the `deploy/aws-cdk/` directory):
```bash
cd deploy/aws-cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Bootstrap** (run once per AWS account + region):
```bash
cdk bootstrap aws://$AWS_ACCOUNT_ID/$AWS_REGION
```

---

## Before You Deploy — Prepare the Local Repo

The CDK upload zips and uploads the local working tree to S3. The EC2 instances
pull from that snapshot, so **binary assets and submodule content must be
present locally before you run `cdk deploy`**.

```bash
# 1. Pull all Git LFS binary files (data/, stages/, images/, etc.)
git lfs pull

# 2. Initialize the kit-cae submodule and pull its LFS files
git submodule update --init --recursive
git submodule foreach --recursive 'git lfs pull'
```

If either step is skipped, the corresponding files will be LFS pointer stubs on
S3 and the containers will fail to find the data they need at runtime.

---

## Configuration

1. Export account and region:
```bash
export AWS_ACCOUNT_ID=012345678901
export AWS_REGION=us-east-1
```

2. Find your public IP (e.g. [whatsmyip.com](https://whatsmyip.com)) — needed
   for the `allowedIpRanges` flag.

---

## Deploy

```bash
cdk deploy --all \
  --parameters OmniverseCAEConfigStack:NGCApiKey=nvapi-<your-key> \
  -c allowedIpRanges="<your-public-ip>/32" \
  [--profile <aws-profile>]
```

The NGC API key is passed as a CloudFormation `NoEcho` parameter and stored in
Secrets Manager.

Optional parameters:
| Flag | Default | Effect |
|---|---|---|
| `--parameters OmniverseCAEConfigStack:NGCApiKey=...` | required on deploy | Store the NGC API key in Secrets Manager |
| `-c splitDeployment=false` | true (split) | Run everything on one large instance |
| `-c allowedIpRanges="x.x.x.x/32"` | none (no inbound) | Restrict frontend access to your IP |
| `--profile <name>` | default | AWS profile to use |

**Deployment order** — CDK handles this automatically via dependencies:
1. `OmniverseCAEConfigStack` — NGC API key in Secrets Manager
2. `OmniverseCAERepoArtifactStack` — upload local repo to S3 (~2–5 min depending on LFS size)
3. `OmniverseCAENetworkStack` — VPC and subnets
4. `OmniverseCAENimStack` + `OmniverseCAEComputeStack` — EC2 instances (in parallel)
5. `OmniverseCAEConnectivityStack` — security group wiring between instances

**Time to ready:** 20–40 minutes total. The EC2 boot sequence pulls from S3,
builds Docker images, and starts containers. Kit compiles shaders on first
launch (adds ~10 minutes on top of boot).

---

## Check Status

```bash
./check-app-status.sh -r $AWS_REGION [--profile <aws-profile>]
```

When all containers are up, this prints the application URL. The URL is also
visible in CloudFormation outputs:
```
OmniverseCAEComputeStack.ApplicationURL = http://xxx.xxx.xxx.xx
```

Open in **Chrome** for best WebRTC compatibility.

---

## Delete (avoid ongoing cost)

```bash
cdk destroy --all [--profile <aws-profile>]
```

The S3 artifact bucket is automatically deleted with its contents. The NGC API
key secret in Secrets Manager is also removed.

---

## Security

Access to the frontend is limited to the IP range you provide. Be aware:
- An incorrect `allowedIpRanges` setting can open the instance to the internet.
- Users behind the same corporate NAT share your public IP and will have access.
- Traffic between the browser and the frontend is unencrypted (no TLS).

For anything beyond a temporary test setup, add authentication and TLS.

---

## Troubleshooting

### Connect to an instance via SSM

CDK outputs the connection commands directly:
- **NIM instance**: `OmniverseCAENimStack.NimSSMConnectCommand`
- **OV instance**: `OmniverseCAEComputeStack.SSMConnectCommand`

```bash
aws ssm start-session --target i-xxxxxxxxxxxxxxxxx [--profile <aws-profile>] [--region $AWS_REGION]
```

Once connected, switch to the ubuntu user and check the boot log:
```bash
sudo su ubuntu
cat /var/log/user-data.log     # full boot output
docker ps                       # check which containers are running
cd /home/ubuntu/digital-twins-for-fluid-simulation
docker compose logs kit --tail 50
```

### No connection / timeout
- Verify `allowedIpRanges` matches your current public IP (corporate NAT can change it).
- Check that the OV instance boot completed: `cat /var/log/user-data.log` should end with "User data script completed successfully!".

### Grey screen (controls visible but no stream)
- Kit is still compiling shaders — wait a few minutes and reload.
- Try resizing the browser window or appending `?width=1600&height=1200&fps=60` to the URL.

### NIM not responding / inference not working
1. Check the NIM instance: `docker ps` should show `aeronim` running.
2. Confirm AeroNIM is ready: `curl http://localhost:8080/v2/health/ready` should return `{}`.
3. AeroNIM can take 5–15 minutes to load the model after the container starts.
4. Check the NIM IP in the OV instance's `.env`: `grep NIM /home/ubuntu/digital-twins-for-fluid-simulation/.env`

### Relaunch containers without full redeploy

**OV instance** (kit + web only):
```bash
cd /home/ubuntu/digital-twins-for-fluid-simulation
./relaunch-containers.sh              # re-fetches NIM IP from SSM automatically
./relaunch-containers.sh <NIM_IP>     # or pass the NIM private IP directly
```

**NIM instance** (aeronim only):
```bash
/home/ubuntu/relaunch-nim.sh
```

---

## Sharing the NIM Instance

The AeroNIM inference server can serve multiple frontend instances:
1. Deploy only the Config, Network, and NIM stacks.
2. Create additional CDK apps for each frontend, referencing the shared NIM's SSM
   parameter `/omniverse-cae/nim-ip` for the private IP.
3. Add an inbound rule on the NIM security group for each frontend's security group
   (port 8080).
