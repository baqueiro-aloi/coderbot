"""Phase prompt templates for the codebot lifecycle.

Templates use string.Template ($name) placeholders, rendered via render() below.
This is deliberate: call sites interpolate UNTRUSTED text (email reply bodies,
raw e2e output) that routinely contains literal '{' and '}' (JSON, stack traces,
code). str.format() would raise KeyError/ValueError on those; Template does not,
and safe_substitute never rescans the substituted values.
"""
from string import Template


def render(template: str, **kwargs) -> str:
    return Template(template).safe_substitute(**kwargs)


PICK = """Here is the list of pending improvements for the $project project (from the
backlog Google Doc). Some items may depend on others; pick the single item that
makes most sense to implement NEXT (prerequisites first, easier enablers first).

Pending items:
$items

Respond with ONLY a JSON object, no other text:
{"item": "<exact text of the chosen item>", "slug": "<short-kebab-case-slug>", "reason": "<one sentence>"}
"""

EXPLORE = """You are working autonomously on the $project repo, on branch $branch,
implementing this improvement from the backlog:

    $item

Use the /opsx:explore approach: investigate the codebase, clarify the requirements,
identify integration points, risks, and the simplest solid design. Work everything
out yourself; only use the NEED_USER_INPUT mechanism for decisions that genuinely
require the user. End with a concise summary of your conclusions.
"""

PROPOSE = """Now formalize the plan: run the /opsx:propose workflow (openspec CLI) to
create a change named $slug with proposal.md, design.md, specs, and tasks.md,
based on your exploration. Requirements:
- Every user-facing feature MUST include comprehensive Playwright e2e tests in e2e/tests/.
When done, output the full text of proposal.md and a summary of the tasks so it can
be emailed to the user for review.
"""

CLASSIFY_APPROVAL_REPLY = """The user replied to the proposal-review email with:

    $reply

Classify their intent. Respond with ONLY a JSON object, no other text:
{"action": "approve" | "changes", "feedback": "<the requested changes, empty if approve>"}

Only choose "approve" when the reply is a clear, explicit go-ahead to implement the
proposal as-is. If the reply is ambiguous, asks a question, or requests any change,
choose "changes" and put the substance in "feedback".
"""

REVISE_PROPOSAL = """The user reviewed the proposal and did NOT approve it yet. They
replied with:

    $feedback

Revise the change artifacts (openspec change $slug) accordingly and output the updated
proposal for another review round. Do not treat this as approval — the user must
explicitly approve before implementation begins.
"""

IMPLEMENT = """The user approved the proposal. Implement the openspec change $slug
fully (the /opsx:apply workflow): work through every task in tasks.md, marking them
complete. Mandatory:
- Comprehensive Playwright e2e tests for the feature in e2e/tests/ (they must pass).
- Commit your work on branch $branch with clear messages. Do NOT push yet.
End with a summary of what was implemented and the list of new/changed e2e spec files
(one per line, prefixed with `E2E_SPEC: `).
"""

FIX_E2E = """The e2e suite failed. Fix the issues and re-commit. Failure output:

$output
"""

PR_BODY = """Create a pull request for the current branch $branch against main using
`gh pr create` (push the branch first). Title it after the improvement; write a clear
body describing the change, the e2e coverage added, and link the openspec change.
End your response with the PR URL on its own line prefixed with `PR_URL: `.
"""

ADDRESS_REVIEW = """An automated code reviewer (OpenCodeReview) reviewed your pull
request and left the comments below. Evaluate each one on its merits — the reviewer
is helpful but pattern-based and not always right.

$comments

For each comment: if it points to a genuine problem, fix it properly. If it is a
false positive or not worth acting on, do NOT change code just to silence it — briefly
note why you're leaving it. Keep the Playwright e2e tests passing and updated. Commit
your changes on branch $branch with clear messages and push (the reviewer re-runs on
the new commit). End with a short summary of what you changed and what you left as-is
and why.
"""

CLASSIFY_PR_REPLY = """The user replied to the pull-request review email with:

    $reply

Classify their intent. Respond with ONLY a JSON object:
{"action": "merge" | "changes", "feedback": "<the change requests, empty if merge>"}
"""

APPLY_PR_FEEDBACK = """The user reviewed the PR and requested changes:

    $feedback

Apply the requested changes on branch $branch, keep e2e tests passing and updated,
commit and push. End with a summary of what changed.
"""
