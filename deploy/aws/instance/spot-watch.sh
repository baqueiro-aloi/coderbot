#!/bin/bash
# Polls IMDSv2 for the two-minute Spot interruption notice (and the earlier rebalance
# recommendation). On either: stop the container gracefully, flush and release the
# volume so the replacement instance can attach it without waiting for termination.
set -u
IMDS=http://169.254.169.254/latest
. /etc/coderbot/agent.conf
export AWS_DEFAULT_REGION="$REGION"

while true; do
  TOKEN=$(curl -sf -X PUT "$IMDS/api/token" -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' || true)
  if [ -n "$TOKEN" ]; then
    action=$(curl -s -o /dev/null -w '%{http_code}' -H "X-aws-ec2-metadata-token: $TOKEN" "$IMDS/meta-data/spot/instance-action")
    rebalance=$(curl -s -o /dev/null -w '%{http_code}' -H "X-aws-ec2-metadata-token: $TOKEN" "$IMDS/meta-data/events/recommendations/rebalance")
    if [ "$action" = "200" ] || [ "$rebalance" = "200" ]; then
      logger -t coderbot-spot-watch "notice received (instance-action=$action rebalance=$rebalance); stopping coderbot"
      systemctl stop coderbot
      sync
      umount /mnt/coderbot || logger -t coderbot-spot-watch "umount failed; termination will detach"
      aws ec2 detach-volume --volume-id "$VOLUME_ID" >/dev/null 2>&1 || true
      logger -t coderbot-spot-watch "released $VOLUME_ID"
      exit 0
    fi
  fi
  sleep 5
done
