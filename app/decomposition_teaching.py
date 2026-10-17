"""Offline teaching derived from canonical policy; no consumer wiring or I/O."""
import hashlib
import json

from app.complexity import DECOMPOSITION, MIN_CHILDREN, validate_bounty_split


SOURCE = 'app.complexity:DECOMPOSITION,MIN_CHILDREN,validate_bounty_split'
BEGIN = '<!-- BEGIN GENERATED DECOMPOSITION_TEACHING V1 -->'
END = '<!-- END GENERATED DECOMPOSITION_TEACHING V1 -->'


def _explanation(rules, minimum):
    count = 'two' if minimum == 2 else str(minimum)
    sentences = []
    for parent, children in rules.items():
        if not children:
            sentences.append(f'A {parent} never splits.')
            continue
        choices = ' or '.join(f'{count} or more {child}s' for child in children)
        suffix = ', never a mix' if len(children) > 1 else ''
        sentences.append(f'A {parent} splits into {choices}{suffix}.')
    for parent, children in rules.items():
        if parent in children:
            sentences.append(f'{parent}-to-{parent} decomposition may repeat.')
    sentences.extend([
        'Counts follow grounded work, not a fixed three.',
        'Structural examples do not authorize agent launches.',
    ])
    return ' '.join(sentences)


def _example(identifier, explanation, trace):
    splits = [{'parent': parent, 'children': list(children)}
              for parent, children in trace]
    valid = True
    for split in splits:
        try:
            validate_bounty_split(split['parent'], split['children'])
        except ValueError:
            valid = False
    return {'id': identifier, 'explanation': explanation,
            'splits': splits, 'valid': valid}


def build_teaching():
    """Return fresh JSON-compatible data; examples are probes, not policy."""
    rules = {parent: list(children) for parent, children in DECOMPOSITION.items()}
    semantics = {'rules': rules, 'min_children': MIN_CHILDREN}
    encoded = json.dumps(semantics, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True).encode('utf-8')
    examples = [
        _example('high-two-medium', 'Two MEDIUM children are valid.',
                 [('HIGH', ['MEDIUM', 'MEDIUM'])]),
        _example('medium-four-low', 'Four LOW children are valid.',
                 [('MEDIUM', ['LOW'] * 4)]),
        _example('high-repeat', 'A HIGH child may itself split into HIGH children.',
                 [('HIGH', ['HIGH', 'HIGH']), ('HIGH', ['HIGH', 'HIGH'])]),
        _example('high-mixed', 'Mixed HIGH and MEDIUM children are invalid.',
                 [('HIGH', ['HIGH', 'MEDIUM'])]),
        _example('low-split', 'LOW children cannot be created beneath a LOW.',
                 [('LOW', ['LOW', 'LOW'])]),
        _example('high-single', 'One child is not a split.',
                 [('HIGH', ['HIGH'])]),
    ]
    return {'version': 1, 'source': SOURCE, 'min_children': MIN_CHILDREN,
            'rules': rules, 'explanation': _explanation(rules, MIN_CHILDREN),
            'examples': examples, 'fingerprint': hashlib.sha256(encoded).hexdigest()}


def render_markdown(teaching=None):
    """Render supplied teaching verbatim; None selects canonical generation."""
    if teaching is None:
        teaching = build_teaching()
    lines = [BEGIN, f"Source: `{teaching['source']}`", '',
             teaching['explanation'], '']
    for example in teaching['examples']:
        trace = '; '.join(
            f"{split['parent']} -> {', '.join(split['children'])}"
            for split in example['splits'])
        outcome = 'valid' if example['valid'] else 'invalid'
        lines.append(f"- {example['id']}: {trace} [{outcome}]")
    return '\n'.join(lines + [END, ''])
