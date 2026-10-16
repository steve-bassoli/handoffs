# Bounty execution and Watson verification

Product direction supplied by Steve, October 16, 2026. Save as the target workflow;
this document does not claim these features are already implemented.

## Goal

Accept a bounty, let an API agent prepare a reviewable result, and retain an
auditable record of the developer proving the changed behavior in the app.
Gold and reward changes are out of scope for this direction.

## Required user flow

1. **Accept bounty.** Show a spinner and loading text on the button immediately.
   One acceptance creates one task assignment and one AI run. Disable duplicate
   submissions while the request is pending; an uncertain retry reuses the same
   operation ID. Restore a usable button with a clear error if acceptance fails.
2. **Progress notification.** Show one notification at the top right for that run.
   Update it as the work progresses: queued, researching, awaiting developer
   answers, preparing artifacts, ready, or failed. Use actual recorded stages;
   do not invent percentages. The developer can navigate elsewhere while work
   continues. Refreshing or returning to the app restores authoritative status.
3. **Contextual model selection.** The service selects an appropriate model using
   the bounty's context, task type, and complexity. Record the chosen model and
   selection reason with the run. Luna remains the current testing model; the
   routing policy and available model choices are still to be implemented.
   Preserve the maximum of three developer questions across the whole run.
4. **Research ready.** Update the same top-right notification when the research
   or fix bundle is ready. Include a direct link to the exact bounty page.
   Preparation being finished does not establish that the fix was verified.
5. **Artifacts.** The bounty page lists every retained artifact with a download
   link, plus the portable ZIP for a fresh Codex chat. Preserve the research,
   source/context pins, implementation plan, proposed changes, local run
   instructions, and available validation evidence. Clearly distinguish proposed
   test commands from tests actually executed and their results.
6. **Developer verification.** The developer applies the patch and verifies the
   behavior in the application. The bounty page records evidence against the
   acceptance criteria and the developer's explicit verification decision.
7. **Watson evidence pair.** For WATSON bounties only, require two MP4 attachments:
   one demonstrating the legacy functionality and one demonstrating the same
   functionality after the patch is applied. Label the slots **Legacy behavior**
   and **Patched behavior**. Do not apply this requirement to non-Watson tasks.
8. **Auditable completion.** Keep the videos, artifacts, revisions, criterion
   verdicts, actor, timestamps, and verification decision together on the bounty.
   An AI-produced ZIP, PR, notification, or pair of uploads cannot itself supply
   the developer's verification decision.

## Watson comparison contract

- Determine Watson scope explicitly from the task/project metadata; do not infer
  it from the title alone.
- Both MP4s must demonstrate the same named scenario, with comparable inputs,
  user role, configuration, and expected result. Record the legacy version and
  patch commit/build so the comparison is attributable to specific software.
- Each criterion records its expected behavior, observed legacy and patched
  outcomes, evidence references (including video timestamps), and pass/fail or
  unresolved verdict. A missing recording leaves the Watson verification gate
  incomplete. A failed or unresolved criterion cannot count as verified.
- Bind the evidence to the exact patch revision. A later patch requires a new
  verification decision and evidence sufficient for that revision; old approval
  does not silently apply to new code.
- Record checks for relevant behavior that a screen recording cannot establish,
  such as permissions, persisted data, audit events, e-signatures, transactions,
  or error handling. Use actual test results or observable application/backend
  evidence when those behaviors are in scope. Never manufacture a passing result.
- Keep uploaded evidence immutable with a content hash and actor/time metadata.
  Replacement evidence is a new version, preserving the previous record. Store
  recordings in application artifact storage, not Git. Use approved test data;
  credentials and sensitive records do not belong in demonstrations.
- Two MP4s establish a reviewable before/after record for the demonstrated
  scenarios. They do not alone prove 100% equivalence of all Watson behavior or
  establish regulatory compliance. Report coverage against the explicit pinned
  criteria and scenarios. Any overall rewrite coverage percentage requires a
  defined baseline inventory and verified coverage of that inventory.

## State and hierarchy

Keep assignment, AI preparation, evidence submission, and human verification
separate. A successful path is:

`available -> accepted/researching -> awaiting answers (if needed) -> artifacts ready -> awaiting local verification -> evidence ready -> verified`

The next UX consolidates the current separate take/start controls into **Accept
bounty** for this execution path. Acceptance starts preparation; downloading the
result does not complete verification. Failed API work exposes a clear failure
and explicit retry without losing the assignment or previous evidence.

If the agent cannot produce a fix, retain its findings and propose bounded child
tasks. The user must explicitly confirm the exact children before they exist.
The attempt may close with outcome **follow-ups required**, while the original
requirement remains unverified. The parent/child tree and ordered history must
show that distinction through to the eventual verified result.

## Minimum implementation order

1. Wire Accept bounty to one persisted AI run with button loading and one
   updating top-right notification linking back to the task.
2. Expose all artifact downloads on the bounty page and record model selection.
3. Add the explicit Watson marker, the two MP4 slots, and criterion-based local
   verification tied to the patch revision.
4. Enforce the verification gate and display its evidence and lineage in the UI.

Existing prototype foundations: Luna API execution, up to three questions,
downloadable fix ZIP, explicit local-verification reporting, confirmed child
creation, and a task tree. This direction adds contextual routing, global
notifications, individual artifact downloads, and the Watson video/evidence gate;
their presence must be verified before describing them as implemented. Current
demo identity and simulated PR verification are not authenticated audit proof.
