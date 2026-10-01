## MODIFIED Requirements

### Requirement: Conditional E2E gate
Codebot SHALL run the E2E gate when a harness is detected and require an established acceptable outcome before opening a PR unless the user explicitly grants a scoped waiver. Passing tests, confirmed preexisting failures, regressions, infrastructure failure, indeterminate outcomes and waived execution SHALL be distinguished. A waiver SHALL retain its original instruction, scope, reason and applicable version, and SHALL NOT set a passed result. Without a harness E2E SHALL be not applicable, and other applicable requirement and verification gates SHALL still be enforced.

#### Scenario: E2E harness present
- **WHEN** implementation completes with an E2E harness
- **THEN** codebot verifies the gate and repairs regressions or diagnoses unknown outcomes before proceeding absent a scoped waiver

#### Scenario: E2E harness absent
- **WHEN** no harness is detected
- **THEN** codebot does not execute E2E or treat its absence as failure, while enforcing other applicable verification

#### Scenario: User waives broken general collection
- **WHEN** the user instructs codebot to skip the broken general E2E collection
- **THEN** codebot records that scope and reports the collection as waived, separately from any passing feature-specific tests

## ADDED Requirements

### Requirement: Requirement coverage gates delivery
Before delivery, codebot SHALL map each approved requirement to implementation and appropriate verification, including feature evidence when applicable. A material requirement not implemented SHALL block claims of complete delivery and enter repair or replanning as appropriate. Tests demonstrating only the implemented subset SHALL NOT establish complete feature coverage.

#### Scenario: Tests pass but selector is missing
- **WHEN** effort tests pass but a required model selector has no implementation
- **THEN** codebot identifies the missing requirement and does not declare the feature complete

### Requirement: Outcomes retain content and repair provenance
Verification outcomes SHALL refer to the content and environment verified and retain report references and waiver/preexisting evidence. Repairs SHALL invalidate affected outcomes. Required test repairs SHALL remain available in task commits or tracked linked work, not only a machine-local stash. Unknown and infrastructure outcomes SHALL be diagnosed before asking the user to fix a product failure that has not been established.

#### Scenario: Code changes after checks
- **WHEN** recovery changes code covered by an earlier successful check
- **THEN** codebot invalidates and reruns the affected check before relying on it in delivery

#### Scenario: Preexisting failure claim
- **WHEN** codebot reports a remaining failure as preexisting
- **THEN** it retains the baseline comparison and result evidence supporting that claim

### Requirement: Review findings are evaluated against approved intent
Codebot SHALL identify review authors as human, automated or unknown using available provenance rather than treating every non-primary-reviewer account as human. It SHALL assess each finding as a defect, clarification, preference or design conflict against approved requirements. It SHALL correct real defects, explain justified nonchanges and replan material newly discovered design issues. Exhausted review rounds SHALL produce a concise prioritized summary, recommendation and precise remaining decision, with details in the PR or attached report.

#### Scenario: Automated reviewer requests conflicting default
- **WHEN** an automated finding requests medium effort but high effort is an approved requirement
- **THEN** codebot evaluates compatibility evidence and approved intent rather than changing the default solely to close the thread

#### Scenario: Eleven threads remain
- **WHEN** functional review rounds finish with eleven open conversations
- **THEN** codebot explains the significant remaining blockers and recommended action without dumping all comments or proposing an unexplained bypass
