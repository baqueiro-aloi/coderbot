#!/usr/bin/env bash
# Coderbot on AWS: one Spot instance + one persistent EBS volume per agent, driven by
# CloudFormation and the AWS CLI only. Point AWS_PROFILE / AWS_REGION at any account.
#
#   deploy.sh shared  --vpc vpc-123                        once per account/region
#   deploy.sh secrets [--env .env] [--claude-dir ~/.claude] [--claude-json ~/.claude.json] [--data data]
#   deploy.sh agent   NAME --subnet subnet-123 --target-repo owner/name [--ref main] [--size 40]
#                     [--types m7g.large,...] [--on-demand-pct 0] [--snapshot snap-123] [--reseed]
#                     [--coderbot-url URL]
#   deploy.sh status  [NAME]        instances, Spot/on-demand, volume, container health
#   deploy.sh logs    NAME          follow the container log (SSM session)
#   deploy.sh shell   NAME          interactive shell on the instance (SSM session)
#   deploy.sh update  NAME          fetch the pinned ref again and rebuild/restart in place
#   deploy.sh recycle NAME          terminate the instance; the ASG replaces it (drills recovery)
#   deploy.sh stop    NAME          desired capacity 0 (volume kept)
#   deploy.sh start   NAME          desired capacity 1
#   deploy.sh destroy NAME          delete the stack (the volume is snapshotted first)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_STACK="${CODERBOT_SHARED_STACK:-coderbot-shared}"
SECRET_PREFIX="${CODERBOT_SECRET_PREFIX:-coderbot}"
SCRATCH="${TMPDIR:-/tmp}/coderbot-deploy.$$"; mkdir -p "$SCRATCH"; trap 'rm -rf "$SCRATCH"' EXIT

die() { echo "error: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "$1 is required"; }
need aws
stack_of() { echo "coderbot-$1"; }
require_name() { [[ "${1:-}" =~ ^[a-z0-9][a-z0-9-]{0,30}$ ]] || die "agent NAME must match [a-z0-9][a-z0-9-]{0,30}"; }

# ------------------------------------------------------------------ helpers
asg_instance() {  # -> instance id of the agent's ASG member (empty if none)
  aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$(stack_of "$1")" \
    --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService` || LifecycleState==`Pending`].InstanceId | [0]' \
    --output text 2>/dev/null | sed 's/^None$//'
}
ssm_run() {  # ssm_run INSTANCE_ID COMMAND... : run and print output (waits up to 30 min)
  local iid="$1"; shift
  local cmd_json; cmd_json=$(python3 -c 'import json,sys; print(json.dumps({"commands": sys.argv[1:], "executionTimeout": ["1800"]}))' "$@")
  local cid; cid=$(aws ssm send-command --instance-ids "$iid" --document-name AWS-RunShellScript \
    --parameters "$cmd_json" --query 'Command.CommandId' --output text)
  local status
  while :; do
    status=$(aws ssm get-command-invocation --command-id "$cid" --instance-id "$iid" --query Status --output text 2>/dev/null || echo Pending)
    case "$status" in Pending|InProgress|Delayed) sleep 5 ;; *) break ;; esac
  done
  aws ssm get-command-invocation --command-id "$cid" --instance-id "$iid" \
    --query '[StandardOutputContent, StandardErrorContent]' --output text
  [ "$status" = Success ] || die "command on $iid ended with $status"
}

# ------------------------------------------------------------------ commands
cmd_shared() {
  local vpc=""
  while [ $# -gt 0 ]; do case "$1" in --vpc) vpc="$2"; shift 2 ;; *) die "unknown option $1" ;; esac; done
  [ -n "$vpc" ] || vpc=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
  [ "$vpc" != None ] && [ -n "$vpc" ] || die "no default VPC; pass --vpc"
  echo "deploying $SHARED_STACK in vpc $vpc"
  aws cloudformation deploy --stack-name "$SHARED_STACK" --template-file "$HERE/shared.yaml" \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides VpcId="$vpc" SecretPrefix="$SECRET_PREFIX"
  echo "next: deploy.sh secrets, then deploy.sh agent NAME --subnet ... --target-repo ..."
}

cmd_secrets() {
  local env=".env" claude_dir="$HOME/.claude" claude_json="$HOME/.claude.json" data="data"
  while [ $# -gt 0 ]; do case "$1" in
    --env) env="$2"; shift 2 ;; --claude-dir) claude_dir="$2"; shift 2 ;;
    --claude-json) claude_json="$2"; shift 2 ;; --data) data="$2"; shift 2 ;;
    *) die "unknown option $1" ;; esac; done
  put() {  # put SECRET FILE
    if [ -s "$2" ]; then
      aws secretsmanager put-secret-value --secret-id "$SECRET_PREFIX/$1" --secret-string "file://$2" --query VersionId --output text >/dev/null
      echo "  $SECRET_PREFIX/$1  <- $2"
    else
      echo "  $SECRET_PREFIX/$1  skipped ($2 missing or empty)"
    fi
  }
  [ -s "$env" ] || die "$env not found (pass --env)"
  grep -q '^GH_TOKEN=' "$env" || die "$env has no GH_TOKEN"
  echo "pushing secrets:"
  put env "$env"
  put claude-credentials "$claude_dir/.credentials.json"
  put claude-json "$claude_json"
  put google-token "$data/token.json"
  put google-credentials "$data/credentials.json"
  echo "note: agents seed these files once; rerun 'deploy.sh agent NAME ... --reseed' to push new values onto an existing volume"
}

cmd_agent() {
  local name="${1:-}"; shift || true; require_name "$name"
  local subnet="" target="" ref="main" size=40 types="" pct=0 snapshot="" reseed=false url=""
  while [ $# -gt 0 ]; do case "$1" in
    --subnet) subnet="$2"; shift 2 ;; --target-repo) target="$2"; shift 2 ;; --ref) ref="$2"; shift 2 ;;
    --size) size="$2"; shift 2 ;; --types) types="$2"; shift 2 ;; --on-demand-pct) pct="$2"; shift 2 ;;
    --snapshot) snapshot="$2"; shift 2 ;; --reseed) reseed=true; shift ;; --coderbot-url) url="$2"; shift 2 ;;
    *) die "unknown option $1" ;; esac; done
  [ -n "$subnet" ] || die "--subnet is required (a public subnet)"
  [ -n "$target" ] || die "--target-repo owner/name is required"
  local az; az=$(aws ec2 describe-subnets --subnet-ids "$subnet" --query 'Subnets[0].AvailabilityZone' --output text)
  [ -n "$az" ] && [ "$az" != None ] || die "subnet $subnet not found"
  [ -z "$types" ] || [ "$(tr ',' '\n' <<<"$types" | wc -l)" -eq 5 ] || die "--types needs exactly five instance types"

  # Render: the bootstrap script rides inside user-data as gzip+base64 (no CloudFormation
  # escaping needed), the agent parameters go through Fn::Sub.
  local b64; b64=$(gzip -9c "$HERE/instance/bootstrap.sh" | base64 | tr -d '\n')
  sed "s|__BOOTSTRAP_GZ_B64__|$b64|" "$HERE/agent.yaml" > "$SCRATCH/agent.yaml"

  local params=(AgentName="$name" SharedStackName="$SHARED_STACK" SubnetId="$subnet" AvailabilityZone="$az"
                TargetRepo="$target" CoderbotRef="$ref" VolumeSizeGb="$size" OnDemandPercentage="$pct"
                ReseedSecrets="$reseed" SnapshotId="$snapshot")
  [ -z "$types" ] || params+=(InstanceTypes="$types")
  [ -z "$url" ] || params+=(CoderbotRepoUrl="$url")
  echo "deploying $(stack_of "$name") in $az (subnet $subnet), target $target, ref $ref"
  aws cloudformation deploy --stack-name "$(stack_of "$name")" --template-file "$SCRATCH/agent.yaml" \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset --parameter-overrides "${params[@]}"
  echo "deployed. First boot builds the image (several minutes); follow with: deploy.sh status $name / deploy.sh logs $name"
}

cmd_status() {
  local names=("$@")
  if [ ${#names[@]} -eq 0 ]; then
    mapfile -t names < <(aws cloudformation describe-stacks --query 'Stacks[?starts_with(StackName, `coderbot-`) && StackName != `'"$SHARED_STACK"'`].StackName' --output text | tr '\t' '\n' | sed 's/^coderbot-//' | grep . || true)
  fi
  [ ${#names[@]} -gt 0 ] || { echo "no agent stacks"; return; }
  for name in "${names[@]}"; do
    local stack; stack=$(stack_of "$name")
    local sstatus; sstatus=$(aws cloudformation describe-stacks --stack-name "$stack" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo MISSING)
    local vol; vol=$(aws cloudformation describe-stacks --stack-name "$stack" --query 'Stacks[0].Outputs[?OutputKey==`VolumeId`].OutputValue | [0]' --output text 2>/dev/null || true)
    local iid; iid=$(asg_instance "$name")
    echo "== $name  stack=$sstatus  volume=${vol:-?}"
    if [ -z "$iid" ]; then echo "   no instance (desired capacity 0, or launching)"; continue; fi
    aws ec2 describe-instances --instance-ids "$iid" \
      --query 'Reservations[0].Instances[0].[InstanceId, InstanceType, InstanceLifecycle || `on-demand`, State.Name, PublicIpAddress, LaunchTime]' --output text \
      | awk '{printf "   instance=%s type=%s market=%s state=%s ip=%s since=%s\n", $1,$2,$3,$4,$5,$6}'
    aws ec2 describe-volumes --volume-ids "$vol" --query 'Volumes[0].Attachments[0].[InstanceId, State]' --output text 2>/dev/null \
      | awk '{printf "   volume attached to %s (%s)\n", $1, $2}'
    ssm_run "$iid" 'docker ps --filter name=codebot --format "   container={{.Names}} {{.Status}}"; tail -n 3 /var/log/coderbot-bootstrap.log 2>/dev/null | sed "s/^/   boot: /"' 2>/dev/null || echo "   (SSM not reachable yet)"
  done
}

cmd_logs() {
  require_name "${1:-}"; local iid; iid=$(asg_instance "$1"); [ -n "$iid" ] || die "no running instance for $1"
  aws ssm start-session --target "$iid" --document-name AWS-StartInteractiveCommand \
    --parameters '{"command":["cd /mnt/coderbot/coderbot && docker compose --env-file /mnt/coderbot/agent.env -f deploy/aws/docker-compose.aws.yml logs -f --tail 200"]}'
}

cmd_shell() {
  require_name "${1:-}"; local iid; iid=$(asg_instance "$1"); [ -n "$iid" ] || die "no running instance for $1"
  aws ssm start-session --target "$iid"
}

cmd_update() {
  require_name "${1:-}"; local iid; iid=$(asg_instance "$1"); [ -n "$iid" ] || die "no running instance for $1"
  echo "updating $1 on $iid (fetch pinned ref, rebuild, restart)"
  ssm_run "$iid" '. /etc/coderbot/agent.conf' \
    'git -C /mnt/coderbot/coderbot fetch --tags origin' \
    'git -C /mnt/coderbot/coderbot checkout -q --detach "origin/$CODERBOT_REF" 2>/dev/null || git -C /mnt/coderbot/coderbot checkout -q --detach "$CODERBOT_REF"' \
    'git -C /mnt/coderbot/coderbot log -1 --oneline' \
    '/mnt/coderbot/coderbot/deploy/aws/instance/boot.sh 2>&1 | tail -n 5'
}

cmd_recycle() {
  require_name "${1:-}"; local iid; iid=$(asg_instance "$1"); [ -n "$iid" ] || die "no running instance for $1"
  echo "terminating $iid; the ASG launches a replacement that re-attaches the volume"
  aws autoscaling terminate-instance-in-auto-scaling-group --instance-id "$iid" --no-should-decrement-desired-capacity --query 'Activity.StatusCode' --output text
}

cmd_stop()  { require_name "${1:-}"; aws autoscaling set-desired-capacity --auto-scaling-group-name "$(stack_of "$1")" --desired-capacity 0; echo "$1: desired capacity 0 (volume kept)"; }
cmd_start() { require_name "${1:-}"; aws autoscaling set-desired-capacity --auto-scaling-group-name "$(stack_of "$1")" --desired-capacity 1; echo "$1: desired capacity 1"; }

cmd_destroy() {
  require_name "${1:-}"; local stack; stack=$(stack_of "$1")
  echo "deleting $stack (the volume is snapshotted on delete; find it under Name=coderbot-$1)"
  aws cloudformation delete-stack --stack-name "$stack"
  aws cloudformation wait stack-delete-complete --stack-name "$stack"
  echo "deleted"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  shared|secrets|agent|status|logs|shell|update|recycle|stop|start|destroy) "cmd_$cmd" "$@" ;;
  *) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
