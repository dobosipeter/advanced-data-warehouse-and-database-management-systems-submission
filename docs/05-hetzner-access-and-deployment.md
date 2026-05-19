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

The repository still needs production deployment configuration work for the reverse proxy and host port exposure before the final public rollout. This document should be updated again once that production configuration is committed.
