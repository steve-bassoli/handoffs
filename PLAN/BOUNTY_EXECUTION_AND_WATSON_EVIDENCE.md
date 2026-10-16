# Bounty execution and Watson verification

Steve's October 16, 2026 one-proof decision supersedes the earlier deferred
two-MP4 design. There is no paired-video requirement to activate later. One
sufficient text, image or video artifact supports the claimed outcome; optional
support does not create a fixed artifact count. See the governing
[modernization charter](../PROJECT_CHARTER.md).

## Bounty lifecycle

The three visible phases are Posted, Claimed and Closed. Detailed preparation,
approval and verification states remain in the audit history. Cancelled and
superseded are Closed dispositions, not verified successes. Research ending or
children being proposed does not establish acceptance.

HIGH decomposes into exactly three HIGHs or three MEDIUMs; MEDIUM into exactly
three LOWs. New children require human confirmation of the complete set. A LOW
implementation owns one minimal managed commit; verification-only LOWs need no
invented code change. Parents require their own integrated acceptance, not merely
three closed children. Shared prerequisites are linked rather than duplicated.

## One proof before completion

Claim the bounty and pin its intent, criteria, baseline and candidate revisions,
source and verification environment. Keep source-backed facts separate from
assumptions and unknowns. SIM, ORA and LIVE identify the declared target, not proof
that a system ran. WRAP, REPLACE and RETIRE identify migration intent.

Attach one sufficient primary artifact and explicitly request AI review. The
review checks each criterion without tools or execution privileges. Failed,
unreadable, contradictory or insufficient evidence leaves work unresolved. A LOW
also needs an explicit human verification decision before completion. A composite
needs verified children/prerequisites and separate reviewed integration proof.
Every closure and settlement path enforces the same gate.

The artifact is immutable and hashed. Replacements preserve prior artifacts;
changed bound context makes proof stale. Closed LOW proof is directly viewable
and downloadable, including in the artifact ZIP. An AI assertion, PR URL or empty
approval note alone is not proof. Evidence must cover the declared scenario,
relevant state, permissions and side effects; a screenshot alone may be inadequate.
Use approved data and exclude credentials. Demo identities are not authenticated
compliance signatures, and AI judgment is not a certification.

## Implemented local prototype

The service and bounty UI support context shelves, lifecycle projection, a connected
dependency constellation, primary proof upload/history, AI review, human LOW
verification and guarded closure. Completion releases existing funded escrow once;
it does not mint additional rewards. Provider errors and restarted reviews remain
inconclusive until explicit retry. Text/JSON and PNG/JPEG can be submitted to the
review adapter. MP4 is downloadable/viewable but automatic video review currently
returns inconclusive; use sufficient text/image evidence rather than bypassing it.
Provider calls were verified with fixtures, not a paid live run.

Gremlins has an offline workbench and real read-only MCP server. Mimic compares
supplied Legacy, REST and MCP observations; Saboteur challenges mismatch detection
with an isolated in-memory mutation; Witness retains a hashed comparison and named
quirk contract. This SIM-only comparator runs no Watson or Oracle operations.
Unknown behavior remains unverified; coverage requires a pinned behavior catalog.

## Remaining execution UX

The target Accept bounty experience combines assignment and AI preparation with
immediate button loading and one updating top-right progress notification linking
to the bounty. Current separate take/start controls remain; there is no invented
percentage or claim that this combined interaction is implemented. Contextual
model routing and resumable global notifications remain future work. Luna is the
configured test default, not automatic complexity-based routing. Preparation asks
at most three developer questions and retains portable artifacts for a fresh chat.

Real Watson REST/MCP adapters, Oracle/application runners, deployment authorization,
authenticated identity and broader legacy coverage remain separate work. Local
verification does not publish these changes or mutate live bounties.
