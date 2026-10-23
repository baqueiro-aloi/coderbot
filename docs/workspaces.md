# Multi-repository feature workspaces

Coderbot coordinates one backlog feature across repositories beneath a non-Git
directory. The entire workspace is writable; selection is automatic change/PR
tracking, not a permission boundary. Root files remain local; no root Git is created.

## Configuration

```dotenv
CODEBOT_REPO_PATH=/absolute/path/to/feature-workspace
# Optional, relative to the workspace root:
CODEBOT_WORKSPACE_MANIFEST=workspace.json
```

Mode is detected automatically: `.git` at the target root (file or directory)
means single-repository mode; without it, the target is a workspace. No mode
setting is required, and an old `CODEBOT_TARGET_MODE` setting is ignored.

The parent Compose bind mount exposes child repositories at their host paths.
Rebuild after entrypoint changes. Starting the bot starts real backlog work;
review configuration and saved state first.

Discovery defaults to four directory levels, excludes generated folders and
symlink directories, and supports worktree `.git` files. Each repository needs
`origin` and an available default branch, from `origin/HEAD` or a manifest override.
The current checkout branch is never guessed as the base. GitHub Projects needs
`CODEBOT_GH_ISSUE_REPO=owner/repo` because the workspace root has no origin.

Optional manifest:

```json
{
  "max_depth": 4,
  "exclude": ["scratch/*"],
  "base_branches": {"api": "develop", "frontend": "main"},
  "shared_inputs": ["openspec", "docs", "scripts", "e2e", "*compose*.y*ml"],
  "checks": [
    {"id": "integration", "argv": ["python3", "scripts/integration_test.py"], "cwd": ".", "scope": "full"}
  ],
  "docker": {"context": "desktop-linux", "host_root": "/absolute/path/to/feature-workspace"}
}
```

Agent-emitted `CHECK_PLAN` uses workspace-relative `cwd`. Repository checks are
discovered automatically; verification also requires a shared root/E2E check.
Repository and root source content contributes to evidence/cache identity,
including unchanged dependency repositories.

## Workflow

- One source task, shared root OpenSpec plan, and communication thread.
- Agent-selected feature branches use each repository's base. Additional repos
  need no selection approval. Existing functional proposal approval still applies.
- Independent branch, publication, review, and merge progress for each changed repo.
- Checks and independent internal review precede publication.
- Each PR is announced with reports/available attachments in the feature thread.
- Completion requires all required merges and valid integrated verification.
- Shared edits have private eligible-content recovery journals under Coderbot data.
  Delivery lists local-only files: **merging PRs does not deliver those files**.

## Safety and operational limits

No repository sandbox is imposed. Picking requires clean child repositories;
mismatched/unattributed work pauses rather than resets it. Abort/hold preserve
workspace files and branches. State from another target requires explicit reset or
migration. Do not run older single-repository builds against workspace state.

Docker checks require an explicit context and host-root mapping. The mapping is
not file synchronization: remote paths must already exist and match harness binds.
Checked scripts that prune Docker resources or delete volumes are rejected. Use a
dedicated test Compose project without development/shared volumes; arbitrary shell
commands are not a security sandbox. Linux checks cannot call macOS `open`.

The current ejecuciones-mensuales `e2e/run.sh` needs a safe Linux-compatible entrypoint:
it calls `open` and removes volumes. Coderbot reports this instead of executing
destructive cleanup against your development stack.

Cross-repository merges are independent, not atomic. Changed PR heads, closed PRs,
conflicts, and failed checks pause completion. Verified root-only changes can be
delivered locally without inventing a PR.
