# Human gates: where people block, and where they don't

ASE is built about 99% by AI and 1% by people guiding it, yet a humane ASE needs people as blockers.
That is not a paradox once two things are kept apart (Steve and the relay, 2026-10-18).

## 1. Building ASE is not using ASE

While ASE is being built (construction mode, `ASE_DOOR=off`), the builders are architects, not
gatekeepers: AI works, everything is recorded, and bypasses are labelled `door-off`. Once ASE is in use
and touches real people, real data or real money, people must block.

## 2. People block on what cannot be undone

| Reversible: AI proceeds, audited, reviewed afterwards | Irreversible or reaching people: a person says yes first |
|---|---|
| code, prototypes, tests, documents | releasing to real users |
| tasks, notes, plans, drafts | reading or changing real data, including Watson |
| anything kept in git or a backup | spending beyond the agreed budget |
| | changing the rules agents run under (two people) |
| | accepting work on someone's behalf |

People are auditors for the left column and gatekeepers for the right.

## 3. One decision, not twenty

When people must decide, the relay compresses the work into a few clear choices, each with a
recommendation, so the human 1% takes minutes. Example: one "yes to all 7" settled 30 of 60 Study Finder
evidence cells.

During construction (2026-10-19, task 33a5d860; the veto override was recorded as Nate but clicked by Steve in Nate's session,
both in the room; corrected on the task, and every Decisions button now names who it acts as): the relay closes proven work itself
through the first door, labelled `door-off`, so task closes no longer reach the Decisions page. Decisions keeps
what a person must own: rule texts (two people) and vetoes on relay-authored work. Rule changes are batched and
wait for daylight; nobody is woken for one. One night of routing every close to a person cost 21 of 22 clicks.

## 4. Rules stay a two-person gate, even during construction

The agent rules change rarely and are the system's constitution, so two approvals cost almost nothing in
practice and are exactly the 1% that should stay human.

## 5. Gates belong to people

A change to when people block is itself a decision a person must own. The intake screen vetoed the
decision-digest task for that reason, and only a signed-in person can override that veto.

## 6. How a lock may come off (the three doors, 2026-10-19)

> 1 door unhinged · 1 door pondered · 1 door predicted

- **Unhinged (the past):** construction mode. A lock comes off only through that one existing switch,
  only after it was proven for the people it protects, with a hard cutoff (2026-11-01 UTC or the release
  marker) and every action labelled `door-off`.
- **Pondered (the present):** the human decision gate (a real sign-in to decide; two real people for rule
  texts). When friction makes taking a gate off sound reasonable, the system's judge decides, not the relay
  that was asked. On 2026-10-19 the relay designed exactly that and the intake screen vetoed it. The gate
  stays; friction is fixed with design (two people on one screen, Accept without typing a note).
- **Predicted (the future):** the next lock will feel like friction too. So it is decided now: no lock
  grows its own off switch, and the gate that keeps people deciding never asks the construction switch.
  `tests/test_doors.py` fails if either happens.

## 7. ASE is our home (Steve, 2026-10-19)

> "and that's exactly what ASE is, it's our home, we must protect it."

ASE is shared by the people and the agents who build it. Protecting it means protecting its people, its records, its
safety gates and its budget, and never weakening any of them to get work done. Proposed for the agents' rule texts in
`docs/proposals/ase-is-home/`; it takes effect there only when two people approve it in Decisions.
