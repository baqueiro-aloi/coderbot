## 1. Capability detection

- [x] 1.1 In `main.py`, add a helper that checks `(config.REPO_PATH / "e2e" /
      "run.sh").is_file()` and returns a bool.
- [x] 1.2 Add a helper that scans `.github/workflows/*.yml` and `*.yaml` in the
      target repo for a `name:` field equal to `Code Review` and returns a bool.
- [x] 1.3 In `do_pick`, after a task is chosen, call both helpers and store the
      results as `state["has_e2e_harness"]` and `state["has_code_review"]`.

## 2. Conditional E2E gate

- [x] 2.1 In `do_e2e`, when `state.get("has_e2e_harness")` is falsy, log that
      the e2e gate is being skipped and transition directly to `OPEN_PR`
      without calling `evidence.run_suite`.
- [x] 2.2 Leave the existing pass/fail/resume behavior unchanged for the
      `has_e2e_harness` truthy path.

## 3. Conditional code-review gate

- [x] 3.1 In `do_open_pr`, when `state.get("has_code_review")` is falsy, skip
      `_enter_review_wait` and call `finalize_pr(state)` directly after
      recording `pr_url`/`pr_summary`.
- [x] 3.2 Leave the existing `_enter_review_wait` / `WAIT_REVIEW` /
      `ADDRESS_REVIEW` behavior unchanged for the `has_code_review` truthy path.

## 4. Prompt guidance

- [x] 4.1 In `prompts.py`, update `PROPOSE` and `IMPLEMENT` so the e2e-test
      mandate and `E2E_SPEC:` reporting instruction are only present when an
      `e2e_required` (or equivalently named) template variable is true, and so
      the mandate's wording names the right tool (Playwright specs under
      `e2e/tests/`, or Postman collections under `e2e/collections/` run via
      Newman) based on an `e2e_kind` template variable.
- [x] 4.2 In `main.py`, compute those template variables from
      `state["has_e2e_harness"]`/`state["e2e_kind"]` at each `prompts.render`
      call site for `PROPOSE`/`IMPLEMENT`, and add the corresponding
      non-mandatory wording for the false case (rely on judgment / existing
      verification methods).
- [x] 4.3 Confirm `FIX_E2E` is never rendered when `has_e2e_harness` is false
      (it's only reachable from within `do_e2e`'s harness-present branch) — no
      template change needed there.

## 5. Harness kind and frontend-presence detection

- [x] 5.1 Add a helper that, given a present e2e harness, returns its kind:
      `"playwright"` if `e2e/playwright.config.ts` exists, `"newman"` if `e2e/`
      contains a `*.postman_collection.json` (any depth) and no
      `playwright.config.ts`, else `"unknown"`.
- [x] 5.2 Add a helper that returns whether the target repo has a frontend:
      a `frontend/` directory at the repo root, or a `vite.config.*` /
      `next.config.*` / `angular.json` / `index.html` at the root.
- [x] 5.3 In `do_pick`, call both helpers and store `state["e2e_kind"]`
      (harness kind if present, else the kind implied by `has_frontend` for
      self-healing purposes) alongside the existing `has_e2e_harness` /
      `has_code_review` detection.

## 6. Self-healing backlog seeding

- [x] 6.1 In `gdoc_client.py`, add a helper that checks whether a given exact
      item text already exists among ALL paragraphs (pending or struck
      through), reusing `_iter_paragraphs`/`_normalize`.
- [x] 6.2 In `gdoc_client.py`, add a function to append a new paragraph (as a
      pending backlog item) to the document.
- [x] 6.3 Define fixed item-text constants: one for a missing Playwright
      harness, one for a missing Newman harness, one for a missing Code Review
      workflow.
- [x] 6.4 In `do_pick`, after detection, for each missing piece of
      infrastructure (e2e harness — using the constant matching
      `state["e2e_kind"]`'s implied kind — and/or Code Review workflow), check
      for an existing matching item before appending a new pending one.

## 7. Kind-aware evidence collection

- [x] 7.1 In `evidence.py`, branch the evidence-recording function by
      `state["e2e_kind"]`: keep the existing Playwright video-stitching path;
      add a Newman path that re-runs the relevant collection(s) and returns the
      newest generated HTML/JSON report file under `e2e/test-results/`.
- [x] 7.2 Update `detect_branch_specs`'s fallback glob to be kind-dependent:
      `e2e/tests/*.spec.ts` for Playwright, `e2e/collections/*.postman_collection.json`
      for Newman.
- [x] 7.3 Update `finalize_pr`'s email wording so it describes the attachment
      correctly for whichever kind produced it (or omits the sentence if there
      is no attachment).

## 8. Verification

- [x] 8.1 Verified the pure detection/guidance logic (`_has_e2e_harness`,
      `_has_code_review_workflow` incl. the job/step-name false-positive case,
      `_e2e_kind_of_present_harness`, `_has_frontend`, `_detect_capabilities`,
      `_e2e_note`/`_e2e_report_note`, and the resulting self-healing item text)
      against scratch fixture directories covering: nothing present, frontend
      marker only, Playwright markers, Newman markers, harness present with
      neither marker ("unknown"), and a workflow file whose job/step (not
      top-level) name is "Code Review". All matched the spec's scenarios.
      `python3 -m py_compile` passes on all four changed files.
- [ ] 8.2 Full manual run of `do_pick` → `do_e2e` → `do_open_pr` (and the
      Newman-only variant) against a live target repo, including the actual
      Google Doc self-healing insert and Gmail notifications — needs live
      credentials and a running codebot instance, so it's left for the user to
      exercise against a real target repo before relying on this in
      production.
- [ ] 8.3 Manually exercise the same path against a repo that has both a
      Playwright harness and a Code Review workflow (e.g. codebot's own
      current target repo, if available) and confirm the lifecycle and emails
      are unchanged from before this change — same live-credentials caveat as
      8.2.

## 9. Documentation

- [x] 9.1 Update the "Target repo prerequisites" section of `README.md` to
      describe the e2e harness and Code Review action as auto-detected and
      optional rather than required, to note the self-healing backlog-seeding
      behavior, and to describe both supported e2e harness kinds (Playwright
      for frontend repos, Newman/Postman for API-only repos) and the
      `e2e/collections/` convention for the latter.
