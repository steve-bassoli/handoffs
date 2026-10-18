"""Pure ASE adoption guidance. Supplied evidence is reported, not verified here."""
import copy
import re

# This explicit crosswalk connects the two existing, differently named models.
REFERENCES = {
    'decomposition': ('auditable-change', 'tested-learning'),
    'human_gates': ('human-authority',),
    'humane_limits': ('bounded-resources',),
}
GATES = [
    'Implementation authority permits proposed source changes only; no live writes, publication or inferred human acceptance.',
    'Testing requires separate authorization; passing checks are not human acceptance.',
    'Human acceptance is a separate, explicit decision; unresolved evidence is not human acceptance.',
    'No launch, payment, settings or acceptance controls are supplied.',
]
WORKFLOW = [
    {'id': 'inspect', 'action': 'Inspect the supplied definition and narrow scorecard offline.',
     'verification': 'Record scope, source fingerprints, gaps and conflicts; this model performs no source inspection.',
     'next_step': 'Select one bounded issue, or keep a work-only REST checkpoint.'},
    {'id': 'propose', 'action': 'Describe a bounded implementation LOW with owned files and explicit acceptance criteria.',
     'verification': 'Confirm consent, resource limits and separate implementation authority; no automatic launch or commit.',
     'next_step': 'Present proposed source changes for authorized review.'},
    {'id': 'test', 'action': 'Request authorization for named local tests before execution.',
     'verification': 'Record actual commands, results, failures, unknown usage and unexecuted checks; never retry unknown usage automatically.',
     'next_step': 'Refresh evidence after source changes, then request separate human acceptance.'},
    {'id': 'rest', 'action': 'REST at capacity with a minimal work-only checkpoint.',
     'verification': 'Record completed work, failures, unknowns and unexecuted checks without personal health details.',
     'next_step': 'Resume only within authorized capacity; REST preserves access and recognition.'},
]
LIMITATIONS = [
    'This model uses supplied data only: no network, filesystem inspection, writes or test execution.',
    'Reported fingerprints are not verified against current source bytes here; refresh the scorecard after source changes.',
    'A narrow pass is not certification, deployed enforcement, persistent learning or human acceptance.',
    'Gap means insufficient evidence, not proof of absence; partial and conflicting evidence remain unresolved.',
    'Standalone rendering is not host integration; no routes, settings or launch controls are added.',
    'Appreciation does not buy authority or replace proof. REST preserves access and recognition.',
]


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def _index(rows):
    if not isinstance(rows, list):
        return {}
    result, duplicates = {}, set()
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get('id')):
            continue
        identity = row['id']
        if identity in result:
            duplicates.add(identity)
        result[identity] = row
    for identity in duplicates:
        result.pop(identity, None)
    return result


def _evidence(items, identity):
    path = 'app/complexity.py' if identity == 'decomposition' else 'PROJECT_CHARTER.md'
    if not isinstance(items, list):
        return [], False
    valid = all(isinstance(e, dict) and set(e) == {'path', 'sha256', 'kind'}
                and e['path'] == path and isinstance(e['sha256'], str)
                and re.fullmatch(r'[a-f0-9]{64}', e['sha256']) is not None
                and e['kind'] in ('source', 'behavior') for e in items)
    return (copy.deepcopy(items), True) if valid else ([], False)


def build_adoption(definition, scorecard):
    """Return independent guidance without I/O, mutation or inferred acceptance."""
    definition_ok = (isinstance(definition, dict)
                     and definition.get('schema_version') == 'ASE-v1'
                     and _text(definition.get('definition')))
    score_ok = (isinstance(scorecard, dict)
                and scorecard.get('schema_version') == 'ase-narrow-v1')
    properties = _index(definition.get('properties')) if definition_ok else {}
    assessments = _index(scorecard.get('properties')) if score_ok else {}
    capabilities = []
    for identity, references in REFERENCES.items():
        linked, issues = [], []
        for reference in references:
            prop = properties.get(reference)
            if not (prop and _text(prop.get('text')) and _text(prop.get('status'))):
                issues.append('Missing or invalid property reference: ' + reference)
            else:
                linked.append({key: prop[key] for key in ('id', 'text', 'status')})
        row = assessments.get(identity)
        status, reported, evidence, conflicts = 'gap', 'not assessed', [], []
        scope, reason = 'not assessed', 'Missing or invalid assessment'
        if row:
            reported = row.get('status') if _text(row.get('status')) else 'not assessed'
            scope = row.get('scope') if _text(row.get('scope')) else 'not assessed'
            reason = row.get('reason') if _text(row.get('reason')) else reason
            evidence, evidence_ok = _evidence(row.get('evidence'), identity)
            conflicts_ok = _strings(row.get('conflicts'))
            conflicts = list(row['conflicts']) if conflicts_ok else []
            structure_ok = (set(row) == {'id', 'status', 'scope', 'reason', 'evidence', 'conflicts'}
                            and reported in ('pass', 'partial', 'gap')
                            and _text(row.get('scope')) and _text(row.get('reason'))
                            and evidence_ok and conflicts_ok)
            source = any(e['kind'] == 'source' for e in evidence)
            if structure_ok:
                if reported == 'gap':
                    status = 'gap'
                elif source:
                    status = 'partial'
                    if (reported == 'pass' and identity == 'decomposition' and not conflicts
                            and len({e['sha256'] for e in evidence}) == 1
                            and any(e['kind'] == 'behavior' for e in evidence)):
                        status = 'pass'
                else:
                    issues.append('Missing source evidence; behavior not assessed')
            else:
                issues.append('Malformed or unsupported assessment; not assessed')
            if reported == 'pass' and status != 'pass':
                issues.append('Reported pass is not supported by the supplied narrow evidence')
        else:
            issues.append('Missing assessment: ' + identity)
        # Invalid references cannot support adoption claims, even with a probe pass.
        if len(linked) != len(references):
            status = 'gap'
        label = ' '.join(word.capitalize() for word in identity.split('_'))
        capabilities.append({
            'id': identity, 'label': label, 'property_refs': list(references),
            'properties': linked, 'status': status, 'reported_status': reported,
            'scope': scope, 'reason': reason, 'evidence': evidence,
            'conflicts': conflicts, 'issues': issues,
            'action': 'Inspect ' + label + ' evidence offline; propose only a bounded LOW if needed.',
            'verification': 'Compare referenced properties, source fingerprints and named checks; retain gaps and conflicts.',
            'next_step': ('Request separate human review of the scoped result; do not infer acceptance.'
                          if status == 'pass' else
                          'Resolve missing, partial or conflicting evidence through authorized checks, or REST with a work-only checkpoint.'),
        })
    limits = list(LIMITATIONS)
    for model, key in ((definition if definition_ok else {}, 'limits'),
                       (scorecard if score_ok else {}, 'limitations')):
        if _strings(model.get(key)):
            limits.extend(model[key])
        else:
            limits.append('Supplied ' + key + ' unavailable; not assessed.')
    return {
        'schema_version': 'ase-adoption-v1',
        'definition': definition['definition'] if definition_ok else 'ASE definition unavailable; not assessed.',
        'scope': scorecard['scope'] if score_ok and _text(scorecard.get('scope')) else 'not assessed',
        'capabilities': capabilities, 'workflow': copy.deepcopy(WORKFLOW),
        'gates': list(GATES), 'limitations': limits,
    }
