# Watson AI Driven Modernization Charter

Decision recorded October 16, 2026. This charter governs the modernization target
and development workflow. It does not certify that the prototype already meets it.

The goal is seamless AI integration of Watson maintenance and usability through
three cooperating systems: Watson services, Gremlins, and HANDOFFS. AI performs
investigation, decomposition, implementation and evidence preparation. Humans use
the Watson application to verify LOW bounties, rather than to drive routine work.
Human authority over policy, access, task creation and deployment remains intact.

## 1 Watson Services

Replace Watson's legacy application face with REST and MCP interfaces, migrating
one verified boundary at a time. Both interfaces use the same business behavior
and authorization rules; MCP is not an alternate permission bypass. Retain a
versioned legacy baseline and a rollback path during replacement.

The compatibility target includes legacy behavior, bugs and all. A bounty may
explicitly authorize correcting a legacy defect; its acceptance criteria then
define that intentional difference. Preserve unrelated behavior. Compatibility
does not authorize reproducing a security weakness in a new access boundary.

## 2 Gremlins

Gremlins is the Watson compatibility test harness target. Its first local version
exposes an offline comparator through its own MCP server. Large AI models own the implementation design, within the approved scope
and access boundaries; this charter does not prescribe a test framework or stack.

Gremlins compares the pinned legacy baseline and candidate against a versioned
behavior catalog covering relevant inputs, outputs, errors, permissions and state
changes. The target is 100% legacy functionality for that declared catalog,
including documented quirks unless an approved bounty changes them. Unknown or
untested behavior remains unverified, not implicitly compatible.

Keep Gremlins acceptance expectations independent of the implementing model's
claims. Use isolated or explicitly approved environments and controlled data.
Harness availability, a generated test, a proposed command or a simulator pass
does not establish live Watson compatibility. Do not perform production writes,
weaken security or obtain new access merely to make a test pass.

## 3 HANDOFFS

HANDOFFS already has an MCP server. It coordinates AI-driven maintenance and
provides a navigable audit trail from HIGH inception through decomposition,
dependencies, implementation, verification and completion. Preserve revisions,
failed attempts and prior evidence. Link shared prerequisites instead of creating
duplicate tasks. A closed LOW exposes its accepted proof directly, without making
the user hunt through transcripts or artifact directories.

### Rule of Three

HIGH decomposes into exactly three HIGHs or exactly three MEDIUMs, without mixed
levels. HIGH branches eventually reach MEDIUM; each MEDIUM decomposes into exactly
three LOWs. A genuinely LOW root needs no artificial parents. Explore three
meaningful alternatives for a design decision, but never invent facts, questions
or filler tasks to meet a count. Explain why the three responsibilities cover the
parent criteria and how their outcomes combine. Reconsider a boundary that cannot
support a defensible split.

Only LOW work is executable. An implementation LOW owns one minimal managed commit
for its immutable plan/leaf receipt. A verification LOW produces evidence without
a forced commit. New child bounties require explicit human confirmation of the
complete proposed set. Child completion alone does not prove integrated parent
acceptance.

### One Proof Before Completion

One sufficient primary proof artifact is required before completing a LOW bounty:
a video, an image, or a text artifact. There is no two-factor requirement, no
mandatory pair of videos, and no requirement to manufacture three proofs. The
rule of three governs design and decomposition, not proof count. Supporting
material is optional; one artifact must be sufficient for the claimed outcome.

Bind the proof to the bounty, relevant acceptance criteria, baseline and candidate
revisions, environment and verification run where applicable. Show the defect and
corrected result, or the relevant observed outcome for verification-only work.
Label proposed or unexecuted checks separately. Do not expose credentials or
unnecessary private data. A filename, PR link, AI assertion or empty approval note
alone is not proof.

The proof must be viewable by the human and inspectable by AI. AI reviews whether
it supports the criteria, recording pass, fail or inconclusive with reasons; the
human explicitly verifies the LOW outcome before completion. These are review
steps on one proof, not demands for additional proof forms. Missing, unreadable,
contradictory or insufficient proof leaves the bounty unresolved. Being AI
inspectable does not guarantee the AI judgment is correct.

Gremlins supplies compatibility evidence as its relevant capabilities become
available. The closure rule must not label Gremlins checks as executed before
they exist or run. A HIGH or MEDIUM closes only when its integrated acceptance
criteria have evidence, not merely because three children were created or closed.

### Current Prototype Boundary

The local engine enforces typed LOW outcomes, ternary decomposition, managed
commit receipts, shared prerequisite cycle checks and separate parent acceptance.
Posted, Claimed and Closed are lifecycle projections; cancellation and supersession
are Closed dispositions, not successful verification.

Bounties can declare SIM, ORA or LIVE validation targets and WRAP, REPLACE or RETIRE
migration intent. These are metadata, not execution receipts. Known facts require
a source; assumptions and unknowns occupy separate shelves. Mapper, Maker and
Breaker describe responsibilities, not three agents claimed to have run. Shared
prerequisites are linked once in a connected constellation.

One immutable primary proof is bound to criteria, revisions, environment, source
and prerequisite receipts. Current passing AI review and explicit human LOW
verification gate completion and payment. Replacement proof preserves history;
changed context invalidates acceptance. Historical closures are not retroactively
verified. Composite acceptance needs three verified children and its own reviewed
integration proof. Funded verified completion releases existing escrow once;
decomposition neither mints nor duplicates Gold.

Gremlins Mimic compares supplied Legacy, REST and MCP observations against an
explicit expectation. Saboteur injects an in-memory discrepancy to challenge
detection. Witness preserves the reproducer and named legacy quirk in a hashed
report. This SIM-only version runs no Watson or Oracle operations and cannot
certify live parity. Complete Watson REST/MCP replacement remains a target.

These changes are local, not deployed. Demo identity and PR verification remain
simulated. AI proof review uses a separate, tool-free provider request with
structured criterion verdicts; provider access has only been tested with fixtures.
MP4 can be retained and viewed, but automatic video review returns inconclusive.
This charter does not close live tasks, approve proposals, grant access, authorize
production actions, or publish changes to shared main.
