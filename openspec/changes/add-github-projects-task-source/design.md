## Context

`gdoc_client` is a module of plain functions, used as a singleton by `main.py`
at eleven call sites and stubbed in every FSM test with
`patch.dict(sys.modules, {"gdoc_client": Mock()})` followed by
`patch.object(main.gdoc_client, ...)`. The task identity the FSM carries is the
bullet text (`state["item"]`), which the PICK prompt copies verbatim and
`mark_done` later matches on. GitHub access elsewhere in codebot is `gh` CLI
subprocesses (`gh pr ...`, `gh api graphql`) authenticated by `GH_TOKEN`.

## Goals / Non-Goals

**Goals**
- Add GitHub Projects v2 as a backlog backend with zero behaviour change for
  Doc deployments.
- Keep `main.py` churn mechanical: same function names, same item dicts.
- No new Python dependencies; reuse the `gh` CLI and `GH_TOKEN`.

**Non-Goals**
- Migrating items between backends.
- Supporting several sources at once, or several repos on one board.
- Draft cards or pull-request cards as tasks (labels do not exist on them).

## Decisions

- **Module façade, not a class.** `task_source.py` mirrors `agent_runner.py`:
  `if config.TASK_SOURCE == "gdoc": ... elif "github": ...` with lazy imports
  so GitHub mode never imports the Google libraries. Tests keep patching a
  module attribute of `main`. A Protocol adds nothing with stdlib unittest and
  a single active backend per process.
- **Dicts plus an `id` key, not a dataclass.** `render_items`,
  `prioritize_items`, the PICK matching and the FSM tests all consume dicts.
  `id` is `""` for the Doc and the ProjectV2Item node id for GitHub. Write
  functions take `item_id=None`; the Doc ignores it, GitHub prefers it and
  falls back to title matching (seeded items, pre-upgrade `state.json`, the
  startup re-claim). `state["item"]` stays the text so emails, PR bodies and
  logs are untouched; `state["item_id"]`/`state["item_url"]` are added to
  `RESET_KEYS` and copied into hold records.
- **Ownership is a label on the issue** (user decision): `codebot:<instance>`
  while claimed, `codebot-hold:<instance>` while on hold. Labels are visible on
  the board, survive status automations, and need no custom project field.
  Consequences: only project items whose content is an issue in the target repo
  are pickable; drafts and PRs are skipped and counted in a log line; seeding
  creates real issues. Labels are created idempotently at startup
  (`gh label create --force`).
- **Race handling is add-then-verify.** GitHub has no compare-and-swap on
  labels. `claim_task` reads the labels (foreign claim → refuse), adds its own
  label, re-reads, and if a foreign claim label is now also present removes its
  own and refuses. Both racing instances back off and repick on their next tick
  (120 s apart); the Status change to In progress happens only after the
  verified claim. `do_pick`'s existing "resume what I already claimed" filter
  remains the safety net.
- **Status mapping.** pending = Status in `CODEBOT_GH_PROJECT_PICK_STATUSES`
  (default `Ready`); claim → `In progress`; PR opened → `In review`; hold keeps
  the status and swaps the label; abort → first pick status; done → `Done`.
  Every write is idempotent and "already Done" counts as success, so GitHub's
  own project automations cannot conflict.
- **Target repo** for issues and labels is parsed from the checkout's `origin`
  remote (`CODEBOT_GH_ISSUE_REPO` overrides), since codebot works one repo.
- **Seeding title limit.** Issue titles are capped by GitHub; seeded texts
  longer than 200 characters put their first sentence in the title and the full
  text in the body, and `has_item` matches on title or first body line.
- **Images** referenced in the issue body (`![](url)` / `<img src>`) are
  downloaded best-effort with the token into `data/gh_images/`, mirroring the
  Doc's `doc_images/`.

- **Activity trail is one call, `note_activity(text, id, message, ref) -> ref`.**
  `main.trail()` builds `[<instance>] <headline>` plus the body and calls it from
  `email()` (every user-facing message) and from the silent phase transitions
  (picked, approved, answer received, implemented, verified, reviewed, e2e result,
  archived, PR opened, review round, conflicts resolved, merged). `ref` is an
  opaque thread handle the backend may return and the caller stores in
  `state["trail_ref"]` (in `RESET_KEYS`, so hold/resume carry it). GitHub posts
  issue comments and returns no ref; the Doc cannot anchor a comment to a bullet
  through the Drive API, so the first note creates a doc-level comment quoting the
  item text and later notes reply in that thread (a 404 on reply starts a new
  one). A JIRA backend would post issue comments. Failures are logged and never
  change the FSM; `CODEBOT_ACTIVITY_TRAIL=off` disables it. The Doc requires the
  full `drive` scope instead of `drive.readonly`, so existing installs re-consent
  once; until then only the trail is affected (a 403 carries the hint).
- The GitHub `note_pr` write-back no longer comments the PR link itself: the "PR
  opened" trail note carries it, and the PR body's `Closes` line links the issue.

## Risks / Trade-offs

- Token scope: a classic PAT needs `project` (not only `read:project`) and SSO
  authorization for the org; `validate()` reports this at startup, not at the
  first pick.
- The label race is not atomic; the back-off is documented above.
- Each `gh` call is a subprocess (~0.5–1 s); a listing is one call per 100
  items, a claim is four. Fine at the poll interval; project and field ids are
  cached per process.
