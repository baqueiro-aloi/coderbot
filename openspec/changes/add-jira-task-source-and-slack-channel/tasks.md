## 1. Configuration and identity

- [x] 1.1 Add independent source/channel selectors, Jira site/project/account-token/status settings, and Slack channel/bot/app-token settings with per-mode startup validation and email/GDoc defaults; cover all source/channel combinations in config tests.
- [x] 1.2 Generate and persist `codebot-<adjective>-<animal>` for new installations plus a separate persistent random ownership fingerprint for every installation; preserve explicit and previously saved names; test restart and distinct fingerprints for equal names.
- [x] 1.3 Update Google Doc and GitHub Projects claim/hold markers to carry the fingerprint, compare full owner identities, and migrate only locally corroborated legacy markers; test equal names on different installations, hold/resume, and lost-state legacy fail-closed behavior.

## 2. Jira Cloud backlog backend

- [x] 2.1 Add a Jira REST v3 client with email/API-token authentication, timeouts, actionable HTTP/rate-limit errors and paginated `POST /search/jql`; test request shapes and pagination without network access.
- [x] 2.2 Render Jira ADF descriptions into readable task details/links and fetch accessible description images/issue attachments best-effort; cover nested lists, links, missing files and `Codebot[n]` text.
- [x] 2.3 Implement Jira pending issue filtering by project/status/foreign labels, recovery of own claims and stable issue ID/key/URL metadata; test grouped board statuses and stale search results against direct reads.
- [x] 2.4 Implement fingerprinted add-then-verify label claims, contention back-off, hold/unhold/unclaim and removal of only own labels using Jira issue update operations; test two bots with the same readable name, claim races and unrelated labels.
- [x] 2.5 Resolve per-issue Jira transitions to configurable active/review/done/eligible statuses for claim, PR, merge/DONE and ABORT; validate project and status configuration; test unavailable transitions and idempotent retries.
- [x] 2.6 Implement Jira issue creation/deduplication for self-healing items and ADF activity comments/PR links, preserving best-effort note behavior; test duplicates across statuses and creation into eligible state.
- [x] 2.7 Register Jira in `task_source.py` and make PR body generation source-aware: GitHub keeps its closing URL; Jira adds `Closes <key>` plus browser URL and only finishes through Jira transition; cover Jira+email and GitHub regression paths.

## 3. Conversation abstraction and Gmail compatibility

- [x] 3.1 Define a conversation façade for open-thread/send, ordered replies, commands, processed markers, stale-reply drain, check-ins and STATUS; adapt Gmail calls without altering mailbox-wide command behavior or existing Gmail thread IDs.
- [x] 3.2 Route `main.py`'s send, wait, command, hold, status, ping, PR finalization and stale-reply paths through the façade; in Slack WAIT_CLEAN announce once and retry automatically without accepting out-of-task commands; make prompts/messages channel-aware and verify Gmail retries, DONE ambiguity and classifiers remain unchanged.
- [x] 3.3 Make selected conversation/evidence behavior independent of the backlog source; test GDoc+Slack and Jira+email handoffs and that a Jira/Slack-only installation does not require Gmail credentials.

## 4. Slack Socket Mode reception and persistence

- [x] 4.1 Integrate a per-instance Slack Socket Mode client and validate bot token/app token, public channel identity, membership and necessary event permissions; document/install its pinned dependencies.
- [x] 4.2 Add a durable, deduplicating SQLite inbox and owned-thread registry under `data/`; persist accepted Slack events before acknowledgment, ignore other channels, foreign roots, bots and top-level posts; test restart/redelivery and chronological order.
- [x] 4.3 Run the Slack receiver independently of long-running agent calls, reconnect after disconnects, and wake idle/wait ticks on a queued event without interrupting a current agent turn; test replies received while an agent call is in progress.
- [x] 4.4 Post one task root immediately after claim with instance/source identity; persist/recover its channel/root timestamp and reconcile an uncertain post by correlation marker; test crash/retry without duplicate task roots.
- [x] 4.5 Send normal updates, proposals, PR decisions, check-ins and status in the root thread; chunk long text and provide screenshots/reports through Slack's external upload flow while retaining Drive video links; test length and upload-failure paths.
- [x] 4.6 Handle replies/commands from any human in owned active/held threads only; preserve bare DONE classification, scope ABORT/DONE/STATUS/CONTINUE on held threads to that held task, and reject top-level or other-instance commands; test HOLD/CONTINUE across two tasks.
- [x] 4.7 Drain pre-conflict Slack merge/review replies before a refreshed PR-ready handoff and guard side effects against duplicate event delivery; test restart and stale irreversible commands.

## 5. Portable interactive setup

- [x] 5.1 Audit environment keys read by `config.py`, `evidence.py`, entrypoint/healthcheck and other runtime components against `.env.example` and current setup; enumerate missing settings, legacy aliases and transient-only variables with documented ownership in a shared catalog.
- [x] 5.2 Build the catalog's defaults, type/range/format validation, secret masking and applicability rules for every current and new setting; add a regression check that fails when runtime config or `.env.example` gains an undocumented/unoffered setting.
- [x] 5.3 Keep `scripts/setup.sh` as a portable launcher for bash/zsh on macOS/Linux; bootstrap an isolated host Python environment with a pinned Textual dependency and provide a usable stdlib text-mode fallback when the TUI cannot launch.
- [x] 5.4 Build Textual setup pages for repo, identity, GDoc/GitHub Projects/Jira source, Gmail/Slack channel, agent and GitHub credentials, with contextual help, back navigation, masked secret fields and validation before confirmation.
- [x] 5.5 Add an advanced searchable settings page exposing every cataloged runtime option, including statuses/labels, models, activity trail, retries, timeouts, evidence/Drive, environment notes and heartbeat; test that hidden inactive settings remain editable and are not lost.
- [x] 5.6 Preserve existing `.env` comments, unknown keys, advanced values and unchanged secrets; show a masked diff, reject invalid changes, make a backup and atomically write only after confirmation. Test cancel, first install, reconfigure, and changing source/channel without erasing old credentials.
- [x] 5.7 Guide conditional Google OAuth scopes/API setup, Jira token/status checks, per-instance Slack app/channel/Socket Mode setup and existing Claude/OpenCode authentication without requiring `.env` to be partially saved; test cross-combinations and error recovery.

## 6. Documentation and verification

- [x] 6.1 Update `.env.example`, README and deployment instructions for the new guided setup, all supported advanced settings and independent Jira/Slack selectors; document Textual bootstrap/text fallback and required auth for each combination.
- [x] 6.2 Test setup/catalog coverage in bash and zsh on macOS/Linux-capable environments (including no TUI/failed bootstrap) and ensure existing `.env` values survive reconfiguration; run targeted Jira, conversation and FSM regression tests, then the repository unit suite.
- [x] 6.3 Validate this OpenSpec change strictly, and document manual smoke procedures for Jira issue claim→hold→review→done, Slack message→reply/command→restart across two bot apps in one channel, and first-time/repeated setup in both UI modes.

## 7. Jira project configuration and opt-in queue

- [x] 7.1 Fetch Jira project workflow statuses after entering URL, project key, account email and token; use them for the four TUI dropdowns and numbered text-mode choices, and allow credential correction/retry on API errors.
- [x] 7.2 Add a required `CODEBOT_JIRA_PICK_LABEL` to runtime and guided setup; document that Jira issues need both the configured status and this opt-in label, without changing other task sources.
- [x] 7.3 Filter newly pickable Jira issues by status and opt-in label in JQL, local results and direct claim verification; preserve fingerprinted recovery of own issues even if their opt-in label was removed later.
- [x] 7.4 Seed Jira self-healing issues with the opt-in label, preserve it through claim/hold/abort/done, add regression tests and validate the full change.

## 8. Credential-driven setup choices

- [x] 8.1 Guide users to create per-instance Slack bot and app tokens with direct app-setting links, scopes and masked fields before presenting channel selection.
- [x] 8.2 Validate both Slack tokens, paginate joined public channels, and select by channel name in Textual/text mode; refresh choices after token changes and report missing access without saving.
- [x] 8.3 List accessible Jira projects after site/account/token entry, select project key before status mapping, and retry account/project discovery on failure in both UIs.
- [x] 8.4 List GitHub Projects v2 boards after GH_TOKEN and target repo are known, select URL by title with an explicit manual URL path for alternate owners; test pagination and permission errors.
- [x] 8.5 Update setup documentation and regression tests for token→discovery→selection ordering and validate the complete change.

## 9. Section-based setup and actionable tests

- [x] 9.1 Replace Textual wizard navigation with a main menu of configuration sections, a menu-level full Test, Exit, and per-section masked draft, Test, Save and Close, and Discard.
- [x] 9.2 Validate only the current section and its saved prerequisites before saving, persist its changes immediately without erasing other `.env` entries, mark successful sections complete and invalidate dependent marks after changes.
- [x] 9.3 Give text-mode setup the same menu and per-section save/test/discard behavior, including dependent Jira/Slack/GitHub discovery within each section.
- [x] 9.4 Distinguish Slack missing scopes, invalid tokens, non-member/private/archived channels in Test and Save and Close with actionable instructions and no secrets in errors.
- [x] 9.5 Cover first-time section-by-section setup, failed tests without writes, reopening settings, global Test and Exit with real Textual/test-mode and text-mode regression tests; update docs and strictly validate the change.
