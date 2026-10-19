"""The predicted door (docs/HUMAN_GATES.md section 6, task 70a841dc): no lock grows its own off switch, and the gate
that keeps people deciding never asks the construction switch."""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'app'
# Every setting that can loosen a lock, and the one module allowed to read it. Adding one is a reviewed decision.
LOCK_SWITCHES = {
    'ASE_DOOR': 'prototype.py',
    'ASE_PROTOTYPE_AUTO_SIGNOFF': 'prototype.py',
    'HANDOFFS_DEMO_IDENTITY': 'main.py',
    'HANDOFFS_INTAKE_SCREEN': 'main.py',
}
LOOKS_LIKE_A_SWITCH = re.compile(r'DOOR|BYPASS|SIGNOFF|SKIP|OVERRIDE|DISABLE|IDENTITY|INTAKE_SCREEN|UNSAFE|NO_?AUTH|TRUST|ALLOW', re.I)
HUMAN_DECISION_PATH = ('digest_decide.py', 'rule_proposals.py')
CONSTRUCTION_SWITCH = ('door_off', 'auto_signoff_active', 'bypass_label', 'prototype', 'ASE_DOOR')


def environment_reads(path):
    """String keys read through os.environ.get / os.environ[...] / os.getenv in one module."""
    keys = []
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        target = None
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            name = ast.unparse(node.func)
            if name in ('os.environ.get', 'os.getenv', 'environ.get', 'getenv'):
                target = node.args[0].value
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) in ('os.environ', 'environ') \
                and isinstance(node.slice, ast.Constant):
            target = node.slice.value
        if isinstance(target, str):
            keys.append(target)
    return keys


def test_no_lock_grows_its_own_off_switch():
    found = {}
    for path in APP.rglob('*.py'):
        for key in environment_reads(path):
            if LOOKS_LIKE_A_SWITCH.search(key) or key in LOCK_SWITCHES:
                found.setdefault(key, set()).add(path.name)
    unexpected = {key: files for key, files in found.items() if files != {LOCK_SWITCHES.get(key)}}
    assert not unexpected, f'Lock switches must go through the one construction switch and be reviewed: {unexpected}'


def test_the_human_decision_path_never_asks_the_construction_switch():
    for name in HUMAN_DECISION_PATH:
        source = (APP / name).read_text(encoding='utf-8')
        for word in CONSTRUCTION_SWITCH:
            assert not re.search(rf'\b{word}\b', source), f'{name} must not consult {word}: deciding always needs a signed-in person'


def test_the_scanner_would_catch_a_new_switch(tmp_path):
    sample = tmp_path / 'sample.py'
    sample.write_text("import os\nif os.environ.get('ASE_SKIP_REVIEW') == 'on' or os.getenv('X'):\n    pass\n", encoding='utf-8')
    assert sorted(environment_reads(sample)) == ['ASE_SKIP_REVIEW', 'X'] and LOOKS_LIKE_A_SWITCH.search('ASE_SKIP_REVIEW')
