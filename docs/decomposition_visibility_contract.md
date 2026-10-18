# Decomposition visibility v1 — proposed integration, not wired

These files propose detached, read-only UI composition. They do not mount UI,
load scripts, add endpoints, authorize disclosure, modify existing renderers or
establish human acceptance. No checks were executed by the proposal author.

## Producer input and evidence

`project_decomposition_visibility(lineage, detailsById, coverage)` accepts a
list of at most 10000 lineage rows with nonempty string `id` and string-or-null
`parent_id`; omitting `parent_id` makes topology incomplete, not a root.
`detailsById` and `coverage` are objects. `coverage.complete_parent_ids`, when
present, is a list of at most 10000 strings. Its absence means no completeness
claim. Details must supply `classification_explicit: true` and a recognized
`complexity` to establish classification. A default complexity is not evidence.
Titles are strings, otherwise the producer uses the ID. The producer does not
use actor, worker or assignment to infer classification or coverage.

Output is `{schema_version: 1, tickets: [...]}`. Each ticket has string `id`,
string-or-null `parent_id`, string-array `child_ids`, string `title`, string
`status`, and a one-element string-array `reasons`. IDs and children are sorted
by the producer. The renderer preserves supplied order, displaying every record
including valid records and leaves; it does not revalidate policy or topology.

Exact state/reason combinations:

| State | Visible label | Reason |
| --- | --- | --- |
| valid | Valid split | split_valid |
| violation | Violation | split_invalid |
| not_yet_split | Not yet split | no_children |
| unknown | Unknown | topology_invalid, topology_incomplete, coverage_incomplete, or classification_missing |

Precedence is global invalid topology (duplicates, cycles, orphans), global
incomplete topology, missing per-parent coverage, missing explicit parent/child
classification, then no children or canonical split validation. A classified,
covered leaf is not yet split, including a LOW leaf; this is not a requirement
that LOW split. Unknown is not a violation or a clean result. No fixed-three
rule is introduced.

The renderer validates the envelope, bounded record count, unique nonempty IDs,
field types and these state/reason pairs. It rejects malformed payloads as
`Decomposition visibility unavailable.` without rendering ticket controls.
It does not prove graph consistency or independently authenticate evidence.
An empty valid array says `No tickets supplied.`, not that all work is valid.

## JavaScript input and mounting contracts

Load `app/static/decomposition-visibility.js` explicitly. It exposes only:

- `window.renderDecompositionVisibility(options)` — shared evidence panel.
- `window.renderDecompositionHierarchy(options)` — hierarchy host adapter.
- `window.renderDecompositionFlow(options)` — flow host adapter.

`options` is optional and has:

- `visibility`: the producer output itself, not the fixture wrapper or raw lineage.
- `teaching`: an authorized JSON serialization of
  `app.decomposition_teaching.build_teaching()`.
- `onNavigate`: optional function receiving the exact string ticket ID.
- `hostNode`: optional detached DOM element containing the existing host view.

All calls return a detached section. Callers own script loading, payload
provenance, authorized scope, freshness, mounting, replacement and callback
behavior. The renderer performs no network, storage, global patching or
automatic mounting. Navigation is a callback, not authorization to mutate.
Controls are native `button type=button`, so browser Enter/Space activation
uses the ordinary click handler; without a callback IDs are inert spans.
All labels, titles, IDs, reasons and teaching strings use `textContent`.

### Hierarchy

The adapter appends `hostNode`, if supplied, followed by the shared panel.
There is no invented hierarchy-renderer global or implicit DOM lookup. The
caller must construct the hierarchy through its existing authorized path and
supply its detached root. Without it, the adapter returns the evidence panel
inside its wrapper. No claim is made that a hierarchy has been reconstructed.

### Flow and existing-flow fallback

A supplied `hostNode` takes priority. Otherwise the adapter calls the existing
`window.renderTicketFlow(options)` if available, passing the same options
through unchanged, including `lineage`, `detailsById`, `currentId` and
`onNavigate`. The existing flow expects `lineage: {items: [...], root_id: ...}`,
not the producer's lineage list; callers must supply the appropriate host
shape separately from `visibility`. Existing flow exceptions propagate; they
are not retried or disguised as successful output.

If neither a supplied host nor the existing renderer is available, the adapter
returns a `section.ticket-flow` with `aria-label="Task flow"` and visible
`Task flow unavailable.` text, alongside the evidence panel. If visibility or
teaching is unavailable, the existing flow still renders; do not replace it
with the visibility panel. The adapter does not redefine `renderTicketFlow`.
Its returned `.ticket-flow` root, cards, metadata, current marker and children
remain unchanged inside the wrapper. The existing flow alone handles assigned
agent evidence; visibility adds no assignment logic and never derives it from
actor. Exact page-level historical fallback/mounting behavior outside these
read sources still requires relay review before integration.

For either adapter, supplied nodes are appended by identity, not cloned,
cleared, decorated or rewritten. They must be detached: appending an already
mounted node would move it, so live-node mounting is outside this contract.
The wrapper changes ancestry; review host CSS selectors before wiring.

## Canonical rule help

The shared legend names the four evidence states. Policy help consumes the
canonical teaching explanation, minimum, rules, source and fingerprint rather
than duplicating decomposition rules in JavaScript. It requires teaching v1,
source `app.complexity:DECOMPOSITION,MIN_CHILDREN,validate_bounty_split`, string
explanation, integer positive minimum, string-array rule values and a lowercase
64-hex fingerprint. The display does not require examples and does not verify
the fingerprint cryptographically. Source/fingerprint are supplied provenance,
not proof. Do not pass arbitrary data as canonical teaching.

Missing or malformed help says `Canonical rule help unavailable.`; it does not
hide ticket evidence or substitute guessed rules. Teaching is passed directly,
so this file does not require the sibling teaching renderer to be loaded.

## Shared-fixture verification

`tests/fixtures/decomposition_visibility_v1.json` remains unchanged and is the
shared synthetic case source. The Python contract test compares exact producer
output with every expected record and checks nonmutation. The Node-vm contract
test feeds those same expected records through both adapters, asserting IDs,
states, textual labels, reasons, titles and callback IDs. The view test covers
host preservation, native-button structure, hostile strings, malformed and
missing help/evidence, empty payloads and delegation to the existing flow.
Both Node tests skip explicitly when Node is absent; Python fixture comparisons
still execute independently. A skip is not renderer verification.

The minimal DOM does not emulate browser keyboard dispatch, layout, focus,
real parent relationships or HTML accessibility APIs. Review actual Enter/Space
activation, tab order and host CSS in a browser before acceptance. No live
integration, database writes or publication is authorized by these tests.
