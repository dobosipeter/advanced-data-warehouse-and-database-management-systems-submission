# Hetzner Access and Deployment Notes

This document captures the current deployment approach for the public demo VM and the fallback SSH path that works when direct outbound SSH is blocked by a corporate network.

## Hosting Summary

| Item | Value |
|---|---|
| Provider | Hetzner Cloud |
| OS | Ubuntu 24.04 LTS |
| Public app URL target | `https://mw79on-demo.online` |
| Public API URL target | `https://api.mw79on-demo.online/docs` |
| Public ports | `22`, `80`, `443` |
| Internal-only ports | `5432`, `8000`, `8501` |
| Public IP behavior | Server IPv4 is stable while the server exists; no floating IP is required for the current single-VM setup |

## SSH Access

### Direct access

If the current network allows outbound SSH:

```bash
ssh root@<hetzner-vm-ip>
```

### Fallback access via Azure VM

The current working fallback is:

1. Connect to the Azure VM.
2. Copy the local SSH key pair to the Azure VM user account.
3. From the Azure VM, SSH to the Hetzner VM as `root`.

#### Copy key pair to Azure VM

Run this from the machine that already has the working local key:

```bash
scp ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub <azure-user>@<azure-vm-ip>:~/.ssh/
```

On the Azure VM, lock the permissions:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

Then connect onward to Hetzner:

```bash
ssh -i ~/.ssh/id_ed25519 root@<hetzner-vm-ip>
```

### Cleanup reminder

If the Azure VM is only being used as a hop host, remove the copied private key when it is no longer needed:

```bash
rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub
```

## First-Time Server Bootstrap

Run these commands on the Hetzner VM as `root`:

```bash
apt-get update
apt-get install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

Verify the expected services are available:

```bash
docker --version
docker compose version
ufw status
```

## Deployment Sequence

After the base OS bootstrap:

1. Clone the repository onto the VM.
2. Copy `.env.example` to `.env` and set production secrets.
3. Update DNS at Namecheap to point `mw79on-demo.online` and `api.mw79on-demo.online` to the Hetzner IPv4 address.
4. Bring up the stack with Docker Compose.
5. Run the first historical load and ETL/prediction jobs.

## Current Deployment Progress

The following steps have already been completed on the Hetzner VM:

1. VM provisioned and reachable through the Azure-VM SSH hop fallback.
2. Docker Engine and Docker Compose installed.
3. Repository cloned to `/opt/air-quality-intelligence`.
4. `.env` created from `.env.example` and populated with the OpenAQ API key.
5. Namecheap DNS `A` records configured for:
   - `mw79on-demo.online` → Hetzner IPv4
   - `api.mw79on-demo.online` → Hetzner IPv4
6. `docker compose up -d --build` completed successfully.
7. Caddy obtained valid Let's Encrypt certificates for both public hostnames.

Current container exposure is expected to be:

- Caddy publicly on `80/443`
- PostgreSQL on `127.0.0.1:5432`
- FastAPI on `127.0.0.1:8001`
- Streamlit on `127.0.0.1:8501`

## Next Runtime Steps

Run the initial data and analytics pipeline on the VM:

```bash
cd /opt/air-quality-intelligence
docker compose --profile tools run --rm worker python ingest.py --initial --history-days 30
docker compose --profile tools run --rm worker python etl.py
docker compose --profile tools run --rm worker python train_model.py
docker compose --profile tools run --rm worker python predict.py
```

After those complete, verify the public endpoints:

```bash
curl -I https://mw79on-demo.online
curl -I https://api.mw79on-demo.online/docs
```

## Current Verified State

The first production data load has completed successfully:

- Initial ingestion inserted `4039` measurements with `0` failures
- DW ETL loaded `4039` measurements and `46` alerts
- PM2.5 training completed with random forest selected as best model
- Prediction run inserted `4` prediction rows

The public endpoints have been verified externally and currently return HTTP `200`:

- `https://mw79on-demo.online`
- `https://api.mw79on-demo.online/docs`

## GitHub Actions Deployment Setup

The repository now includes a deployment workflow at `.github/workflows/deploy.yml`. It:

1. checks out the repository,
2. validates the deployment scripts and Compose file,
3. connects to the Hetzner VM over SSH,
4. syncs the repository contents to `/opt/air-quality-intelligence`,
5. runs `scripts/deploy_stack.sh`, and
6. verifies the public dashboard and API URLs.

### Required GitHub repository secrets

Add these secrets before enabling the workflow:

| Secret | Value |
|---|---|
| `SSH_HOST` | Hetzner IPv4 address |
| `SSH_PORT` | `22` |
| `SSH_USER` | `root` (or the deployment user if changed later) |
| `SSH_PRIVATE_KEY` | Dedicated private deploy key for GitHub Actions |
| `DEPLOY_PATH` | `/opt/air-quality-intelligence` |
| `APP_URL` | `https://mw79on-demo.online` |
| `API_URL` | `https://api.mw79on-demo.online/docs` |

### Recommended deploy-key setup

Prefer a dedicated deployment key instead of reusing the day-to-day personal SSH key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/air_quality_github_actions -C "github-actions-deploy"
cat ~/.ssh/air_quality_github_actions.pub
cat ~/.ssh/air_quality_github_actions
```

- Add the **public** key to `/root/.ssh/authorized_keys` on the Hetzner VM.
- Add the **private** key content to the GitHub repository secret `SSH_PRIVATE_KEY`.

After the secrets are configured, the workflow can be triggered either by pushing to `main` or manually from the Actions tab.
