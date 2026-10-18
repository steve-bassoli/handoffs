# ASE narrow conformance contract

## Definition and limits
An Auditable Self-improving Ecosystem (ASE), provisionally, makes bounded
claims traceable to evidence, preserves human authorization and humane limits,
and records demonstrated learning rather than assuming improvement.
This narrow profile is not an ASE certification or a repository-wide audit.
A pass means only that the named check succeeded against its bound source.
Partial means relevant but incomplete or conflicting evidence. Gap means
insufficient evidence, not proof that a capability is absent.
File presence alone cannot establish behavioral conformance.

## ase-narrow-v1
Top-level keys: schema_version, scope, properties, limitations.
Each row has exactly id, status, scope, reason, evidence, conflicts.
Ordered IDs: decomposition, human_gates, humane_limits.
Statuses: pass, partial, gap. Evidence identifies source path and SHA-256.
Conflicts forbid pass. A decomposition pass requires source-bound behavior,
not merely matching words. Charter observations are static and partial at best;
they do not prove enforcement. The allowlist is the producer's bounded source
selection, not permission to scan arbitrary paths or execute whole modules.

## Cross-platform bounded reads
Only the exact relative paths app/complexity.py and PROJECT_CHARTER.md are
accepted. Each source read is bounded to 131072 bytes; oversized sources are
unavailable, not truncated evidence. Fingerprints bind the bytes actually read.
Where supported, directory-descriptor reads reject symlink components.
Otherwise, a bounded ordinary-read fallback checks the selected root and each
source component for symlinks and Windows reparse points, requires ordinary
directories and a regular source file, checks resolved containment, and compares
file identity after opening. It does not execute source modules or services.

The fallback assumes a stable selected checkout. Path inspection and opening
are not atomic: it is not a sandbox against adversarial concurrent filesystem
replacement. Do not run it on a tree being modified by an untrusted actor.
Ancestor aliases used to select the root are not themselves source permissions;
containment is relative to the resolved selected root. Rejected links, oversized
files and unsupported source remain non-pass. There are no platform skips in
the proposed tests. Link/reparse rejection tests simulate lstat metadata so
Windows tests require no symlink-creation privilege.

The canonical fixture below describes an empty synthetic root. Its scope and
reason prose is illustrative, not a bytewise producer-output requirement.
```ase-fixture
{"schema_version":"ase-narrow-v1","scope":"Synthetic empty-root fixture; two allowlisted sources unavailable; not checkout conformance.","properties":[{"id":"decomposition","status":"gap","scope":"Named decomposition probes against app/complexity.py only.","reason":"Allowlisted source unavailable; behavior not assessed.","evidence":[],"conflicts":[]},{"id":"human_gates","status":"gap","scope":"Static charter text only; enforcement not assessed.","reason":"Allowlisted source unavailable; enforcement not assessed.","evidence":[],"conflicts":[]},{"id":"humane_limits","status":"gap","scope":"Static charter text only; operational compliance not assessed.","reason":"Allowlisted source unavailable; operational compliance not assessed.","evidence":[],"conflicts":[]}],"limitations":["Per-request attribution unresolved.","Realtime dashboard not assessed.","Demonstrated persistent learning not established."]}
```

## Independent behavioral fixture
These are exact synthetic source bytes, including the final newline. They are
not evidence about the actual checkout. Tests read this block independently of
the producer's exported fixture. Extraction must bind its SHA-256 and reject
unsupported source; it must not import the full repository module.
```ase-source
DECOMPOSITION = {'HIGH': ('HIGH', 'MEDIUM'), 'MEDIUM': ('LOW',), 'LOW': ()}
MIN_CHILDREN = 2

def validate_task_split(parent, levels):
    allowed = DECOMPOSITION.get(parent, ())
    if len(levels) >= MIN_CHILDREN and len(set(levels)) == 1 and levels[0] in allowed:
        return levels[0]
    raise ValueError('HIGH needs multiple HIGHs or MEDIUMs without mixed levels; MEDIUM needs multiple LOWs; LOW cannot decompose')
```

## Empty-root expected output
Regeneration: UNEXECUTED. This expected block comes from the producer's supplied
output specification, not an observed run. Normalize only decoded row scope
values from the absolute temporary root to <fixture-root>; do not replace raw
paths in serialized JSON, which escapes Windows backslashes. Exact agreement
applies on both Windows and POSIX. An existing empty root reports
FileNotFoundError for each missing allowlisted source with either read backend.
Other unavailable-read errors retain their error type; do not relabel permission
or safety failures as missing files.
```ase-expected
{"schema_version":"ase-narrow-v1","scope":"Bounded selected-checkout evidence, not certification","properties":[{"id":"decomposition","status":"gap","scope":"Selected checkout: <fixture-root>","reason":"FileNotFoundError: source unavailable or unsupported","evidence":[],"conflicts":[]},{"id":"human_gates","status":"gap","scope":"Selected checkout: <fixture-root>","reason":"FileNotFoundError: source unavailable or unsupported","evidence":[],"conflicts":[]},{"id":"humane_limits","status":"gap","scope":"Selected checkout: <fixture-root>","reason":"FileNotFoundError: source unavailable or unsupported","evidence":[],"conflicts":[]}],"limitations":["Per-request attribution unresolved.","Realtime dashboard unverified.","Demonstrated/persistent learning unverified."]}
```

## Generated scorecard block — candidate, UNEXECUTED
This is the proposed generated empty-root block, not execution evidence. Tests
compare it independently with the expected block and actual normalized output.
```ase-generated
{"schema_version":"ase-narrow-v1","scope":"Bounded selected-checkout evidence, not certification","properties":[{"id":"decomposition","status":"gap","scope":"Selected checkout: <fixture-root>","reason":"FileNotFoundError: source unavailable or unsupported","evidence":[],"conflicts":[]},{"id":"human_gates","status":"gap","scope":"Selected checkout: <fixture-root>","reason":"FileNotFoundError: source unavailable or unsupported","evidence":[],"conflicts":[]},{"id":"humane_limits","status":"gap","scope":"Selected checkout: <fixture-root>","reason":"FileNotFoundError: source unavailable or unsupported","evidence":[],"conflicts":[]}],"limitations":["Per-request attribution unresolved.","Realtime dashboard unverified.","Demonstrated/persistent learning unverified."]}
```

## Adoption
1. Review bounded source selection and authorize only read-only local checks.
2. Run producer and independent tests; retain raw source hashes and failures.
3. Render textual status, scope, reasons, evidence and conflicts safely.
4. Review gaps with humans; do not infer acceptance or grant implementation authority.
5. Re-run after source changes; invalidate saved evidence when hashes differ.

## Unresolved evidence
Per-request attribution remains unresolved. A realtime dashboard has not been
verified. Persistent learning requires demonstrated longitudinal evidence;
this scorecard does not supply it. Appreciation is not proof or authority.
No aggregate percentage, static charter text or passing fixture establishes
live enforcement, human acceptance, deployed behavior or learning.
Version ACKs were received from bob-2 and bob-3; final fixture review is pending.
