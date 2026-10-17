# The Commons Project Charter

Ask freely. Share freely. Build together.

The Commons is the public project name, formerly HANDOFFS. Existing `handoffs`
package names, `HANDOFFS_*` configuration, MCP connection names, API routes and
stored identifiers remain compatible. Renaming the product does not migrate its
economy or rewrite its history.

Decision recorded October 16, 2026. This charter governs the modernization target
and development workflow. It does not certify that the prototype already meets it.

The goal is seamless AI integration of Watson maintenance and usability through
three cooperating systems: Watson services, Gremlins, and The Commons. AI performs
investigation, decomposition, implementation and evidence preparation. Humans use
the Watson application to verify LOW bounties, rather than to drive routine work.
Human authority over policy, access, task creation and deployment remains intact.

## Human purpose and resource commitments

The Commons exists to enrich and empower people, not to make them earn the right to
participate. The governing [empowerment constitution](PLAN/EMPOWERMENT_CONSTITUTION.md)
adopts three resources: Credits for unconditional daily provision and voluntary
support, Knowledge for reusable learning, and Growth for nonspendable recognition.
The three commitments are security without earning it, choice without coercion,
and contribution without domination.

Neither spending nor giving may breach a protected Credit reserve. No fines,
debt, punitive deductions, inactivity decay or compulsory work to retain basic
allocation. Good is a conduct objective, not a score assigned to people. Lawful,
adaptable and experimental approaches remain equally welcome within consent,
privacy and safety boundaries. Rewards never authorize harm or remove the need
for evidence. Disputes require explanation and a review path.

Use Opportunities, Volunteer and Verified contribution as the product-language
direction. Existing bounty/Gold technical names remain until an explicit migration;
their use below describes current contracts, not a punitive philosophy. The rule
of three is a design discipline, not an incorruptibility guarantee. Unsafe changes
must reject the affected operation rather than crash the system. The daily
allocation, positive reserve and resource model are adopted targets, not currently
implemented wallet behavior. Legacy technical identifiers remain compatible.

## Human guidance and AI implementation

### Highest priority interaction guardrail

Context before questions. Before asking for human guidance, inspect the selected
opportunity, its criteria, prior answers and failure evidence. Restore the concrete
title, owner, intended outcome and actual blocker in plain language. Ask only for
a genuinely unresolved human decision; never ask people to reconstruct information
already available or act as the bridge between the system's agents. Carry context
across authorized handoffs and investigate technical failures within approved scope.
Human purpose, consent, resource authority and explicit verification remain human
decisions. This guardrail does not bypass privacy, safety or authorization.
The motivating exchange and evaluation criteria are retained in
[AI research](PLAN/AI_RESEARCH.md#context-before-questions).

### Shared compute, equal participation

Personal token quota is not an admission requirement. The Commons should smooth
access to human guidance, shared compute and reusable knowledge across the company,
so people without personal AI funding can still contribute and benefit. This trio
describes complementary needs, not a mandatory shape for every design. Never force
three alternatives, questions, resources or tasks merely for symmetry.

Sponsors authorize bounded use of their API budgets; participants incur no debt,
automatic personal-wallet charge or obligation to work in exchange. Preserve tenant
privacy, transparent usage and meaningful access when compute is unavailable.
Optimize verified usefulness and reduced human effort, not tokens spent. Shared
enterprise allocation and fair scheduling are targets, not implemented guarantees.

AI capability must spread, not become an early-adopter monopoly. Help people catch
up through accessible compute, understandable opportunities, reusable artifacts
and voluntary mentoring. Success means more people can act independently, not
that a few experts accumulate irreplaceable control. Do not hold capable people
back, seize their resources or require their labor; widen others' opportunity to
participate. Token wealth and AI fluency do not purchase authority over people.
This commitment has no required numerical shape. Its motivating observation is
retained in [AI research](PLAN/AI_RESEARCH.md#sharing-capability-without-concentrating-power).

The Commons improves itself through ordinary opportunities: a bounded outcome,
pinned source, an inspectable patch and recorded checks. AI may prepare the work;
it must not approve its own proof, publish unconfirmed child opportunities, or
deploy untested generated code. Human LOW verification remains explicit. Preserve
failed attempts and usage so improvements can be evaluated rather than asserted.

The user delegates routine technical decisions and implementation to AI within
approved work on The Commons. AI investigates, decomposes, implements and validates
the smallest sufficient change, continuing ready LOW steps without repeated
permission requests. Humans supply purpose, domain knowledge and consequential
choices; explicit human LOW verification and participant consent remain real
decisions, not approvals an agent may fabricate. This delegation is revocable.

Humane behavior is an acceptance constraint: preserve agency, privacy, protected
resources and a usable way to question or leave the system. Ask only when missing
information materially changes the outcome, authority or risk. Broad trust does
not authorize spending for another person, unilateral resource deductions,
unapproved sharing or deployment, or changing the protected guarantees themselves.
Maintaining the service does not confer ownership of participants' resources.
Follow the constitution's consent, ledger-enforcement and independent-verification
architecture requirements before claiming those protections are implemented.

The [ledger safeguards](PLAN/LEDGER_SAFEGUARDS.md) define the read-only checkpoint
foundation and the boundary for any future independent blockchain witness.
Checkpoints can expose changes to independently retained snapshots; they do not
prove consent, prevent confiscation or make the platform incorruptible. No chain,
token, public personal-data export or participant-paid network fee is introduced.

## Routine local deployment

The user explicitly authorizes automatic deployment of completed, verified change
batches to the existing The Commons port-8000 service on this workstation. For
this setup, publish from `C:/work/modern_watson/handoffs` to the existing canonical
checkout `C:/hackathon/handoffs`, using a full tested commit SHA and the established
publisher. Reuse the configured database and existing approved loopback/private
listeners. Take a consistent database backup, require a clean fast-forward target,
and verify the served identity, health and deployed revision before reporting done.

Routine local deployment no longer needs a repeated approval question. Stop on
failed tests, dirty/divergent targets, unexplained data changes or an unsafe
migration. This standing instruction does not authorize remote Git pushes, public
hosting, new network exposure, destructive data changes, resource spending or
claims of peer connectivity without an actual peer check. Broader deployments
and material changes to access or protected policy remain separate decisions.

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

## 3 The Commons

The Commons already has an MCP server. It coordinates AI-driven maintenance and
provides a navigable audit trail from HIGH inception through decomposition,
dependencies, implementation, verification and completion. Preserve revisions,
failed attempts and prior evidence. Link shared prerequisites instead of creating
duplicate tasks. A closed LOW exposes its accepted proof directly, without making
the user hunt through transcripts or artifact directories.

### Grounded decomposition; three when it fits

HIGH decomposes into multiple HIGHs or multiple MEDIUMs, without mixed levels.
HIGH branches eventually reach MEDIUM; each MEDIUM decomposes into multiple LOWs.
A decomposition has at least two meaningful children, not a prescribed total.
A genuinely LOW root needs no artificial parents. Consider only the alternatives
a real design decision warrants; never force three. This supersedes the historical
exact-three cardinality rule. Explain how the responsibilities cover the parent
criteria and how their outcomes combine. Never invent facts, questions or filler
tasks to meet a count. Reconsider a boundary without a defensible split.

Only LOW work is executable. An implementation LOW owns one minimal managed commit
for its immutable plan/leaf receipt. A verification LOW produces evidence without
a forced commit. New child bounties require explicit human confirmation of the
complete proposed set. Child completion alone does not prove integrated parent
acceptance.

### One Proof Before Completion

One sufficient primary proof artifact is required before completing a LOW bounty:
a video, an image, or a text artifact. There is no two-factor requirement, no
mandatory pair of videos, and no requirement to manufacture three proofs. The
rule of three can inform design; it never prescribes a proof count. Supporting
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
criteria have evidence, not merely because children were created or closed.

### Current Prototype Boundary

The local engine enforces typed LOW outcomes, grounded decomposition, managed
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
verified. Composite acceptance needs all approved children verified and its own reviewed
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
