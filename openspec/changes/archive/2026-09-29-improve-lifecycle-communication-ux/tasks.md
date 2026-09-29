## 1. Milestone presentation and delivery

- [x] 1.1 Pregenerate one accessible labeled SVG and PNG rendition per eight milestone stages; verify all labels and highlighted nodes match the lifecycle order.
- [x] 1.2 Add a transport-neutral milestone send helper and persist sent markers across task restart/hold/resume/reset; verify retries do not produce duplicate announcements.
- [x] 1.3 Support a CID-inline PNG in Gmail's HTML alternative and a task-thread image upload in Slack, retaining text-only stage labels; test both render/send paths and image-upload failure behavior.
- [x] 1.4 Wire pick/explore, propose, approval, implementation, verification, archive, PR-ready and confirmed merge milestones to the shared helper; test both ordinary and WAIT_REPLY continuations and DONE-without-merge.

## 2. Proposal package and revision history

- [x] 2.1 Implement strict active-change artifact discovery and safe Markdown-to-self-contained-HTML generation with a working file/heading index and offline navigation; test nested specs, unsafe HTML/URLs and missing files.
- [x] 2.2 Persist immutable review-package files and snapshots under git-ignored data; check channel attachment limits before asking for approval, with an explicit incomplete-package recovery path.
- [x] 2.3 Build a revision digest against the immediately preceding *sent* artifact snapshot, including added/removed/changed requirements, design and tasks; test repeated revision rounds and unchanged revisions.
- [x] 2.4 Route normal proposal, requested revision and question-continuation completion through a single proposal-review sender; verify each sends the complete, current HTML attachment in Gmail and Slack.

## 3. Decision-first and evidence-aware handoffs

- [x] 3.1 Add compact decision cards for proposal approval, agent questions, stuck recovery and PR merge; test action wording, language localization and unchanged reply classification.
- [x] 3.2 Persist validated quality-gate and internal-review outcomes and actual e2e results, then format a readable pass/pre-existing/not-applicable/unavailable verification summary; test both harness-present and harness-absent cases.
- [x] 3.3 Compose a PR-review cover note with task/PR links, key changes, next action and a labeled index derived only from actually delivered attachments/Drive URLs; test missing evidence and upload failures.
- [x] 3.4 Carry the user's requested PR changes through the queued push and WAIT_REPLY continuation, and send a concise request/change/verification recap once the push succeeds; test retry and content accuracy.

## 4. Architectural decisions during PR review

- [x] 4.1 Collect the archived approved design and a bounded committed PR diff/changed-file list for a read-only structured architecture-analysis turn; test large diffs, changed-path filtering and malformed results.
- [x] 4.2 Validate and prioritize high-impact decisions and unverified assumptions against changed files, approved plan and the PR head; produce short citations/impact/status text, including explicit valid-empty and failed-analysis cases.
- [x] 4.3 Send the separate informational report after PR creation and before review wait or immediate finalize, persisting a head/report marker; test no extra approval state, automated-review polling continuity, and a report-generation/send failure.
- [x] 4.4 Recheck architecture only after review, feedback or conflict-resolution pushes and send a concise delta for materially changed decisions, suppressing unchanged reports; test both material and routine fixes.

## 5. Integration and documentation

- [x] 5.1 Exercise complete email and Slack lifecycle simulations, including proposal revisions, a restarted/held task, automated-review present/absent, externally merged PR and completion without merge.
- [x] 5.2 Document message timing, review packages, architectural-report semantics and offline/attachment behavior in README; run the full unit test suite and strict OpenSpec validation.
