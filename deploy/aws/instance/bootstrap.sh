#!/bin/bash
# First-boot user-data for a coderbot agent instance (AL2023 arm64). Kept minimal on
# purpose: everything else runs from the versioned checkout on the volume, so a code
# change never needs a new launch template. Parameters come from /etc/coderbot/agent.conf
# (written by the user-data preamble rendered from agent.yaml).
set -euxo pipefail
exec > >(tee -a /var/log/coderbot-bootstrap.log) 2>&1

. /etc/coderbot/agent.conf
export AWS_DEFAULT_REGION="$REGION"
MNT=/mnt/coderbot

dnf install -y docker git jq
# Docker Compose v2 plugin is not in the AL2023 docker rpm. Pinned.
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-aarch64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Headroom for the image build and parallel agent/e2e work on the smaller pool members.
if ! swapon --show | grep -q swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---- attach the agent's persistent volume ---------------------------------------
# With capacity rebalance the replacement boots while the old instance is still
# shutting down; attach-volume refuses while it is held, which is the mutual
# exclusion we want. Retry for up to 10 minutes.
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
for i in $(seq 1 60); do
  if aws ec2 attach-volume --volume-id "$VOLUME_ID" --instance-id "$INSTANCE_ID" --device /dev/xvdf >/dev/null 2>&1; then
    break
  fi
  echo "volume $VOLUME_ID not attachable yet (attempt $i)"; sleep 10
done
aws ec2 wait volume-in-use --volume-ids "$VOLUME_ID"
# Nitro exposes it as /dev/nvmeXn1 with the volume id (dash stripped) as serial.
SERIAL=$(echo "$VOLUME_ID" | tr -d -)
DEV=""
for i in $(seq 1 30); do
  DEV=$(lsblk -dno NAME,SERIAL | awk -v s="$SERIAL" '$2==s {print "/dev/"$1}')
  [ -n "$DEV" ] && break; sleep 2
done
[ -n "$DEV" ] || { echo "volume device not found"; exit 1; }
if ! blkid "$DEV" >/dev/null; then
  mkfs.ext4 -L coderbot "$DEV"
fi
mkdir -p "$MNT"
echo "$DEV $MNT ext4 defaults,nofail 0 2" >> /etc/fstab
mount "$MNT"

# Docker's data-root on the volume: image layers, the build cache and the target
# repo's e2e images survive a replacement, so only an agent's first boot builds.
mkdir -p "$MNT/docker"
echo '{"data-root": "/mnt/coderbot/docker"}' > /etc/docker/daemon.json
systemctl enable --now docker

# ---- the coderbot checkout, then hand over to its boot script --------------------
if [ ! -d "$MNT/coderbot/.git" ]; then
  git clone "$CODERBOT_REPO_URL" "$MNT/coderbot"
fi
git -C "$MNT/coderbot" fetch --tags origin
# A branch name must track the remote (origin/<ref>); tags and commits resolve as-is.
git -C "$MNT/coderbot" checkout -q --detach "origin/$CODERBOT_REF" 2>/dev/null \
  || git -C "$MNT/coderbot" checkout -q --detach "$CODERBOT_REF"

exec "$MNT/coderbot/deploy/aws/instance/boot.sh"
