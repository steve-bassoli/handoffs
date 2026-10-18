"""Owner-selected campaign autonomy and agent layout; user-directed task actions remain available.

manual: 1 Terra agent; people and explicitly user-directed tools may update tasks; autonomous writes are refused.
light:  4 agents; 1 Sol root over 3 Terra workers; automation may write.
heavy:  4 agents; 1 Astra root over 3 Sol workers; automation may write.
max:    13 agents; 1 Astra root over 3 Sol leads, each over 3 Sol workers; automation may write (parked: too big a leap for now).

The mode is an explicit local owner setting (like the API ledger), never changed by a model or HTTP route.
A missing or unreadable setting means manual, the most restrictive mode.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

MODES = {
    'manual': {'agents': 1, 'levels': ('terra',), 'automated_writes': False,
               'summary': 'User-directed task actions; autonomous writes paused; 1 Terra agent'},
    'light': {'agents': 4, 'levels': ('sol', 'terra'), 'automated_writes': True,
              'summary': 'Autonomous campaign: 1 Sol over 3 Terra; user-directed tasks remain available'},
    'heavy': {'agents': 4, 'levels': ('astra', 'sol'), 'automated_writes': True,
              'summary': 'Autonomous campaign: 1 Astra over 3 Sol; user-directed tasks remain available'},
    'max': {'agents': 13, 'levels': ('astra', 'sol', 'sol'), 'automated_writes': True,
            'summary': '13 agents: 1 Astra over 3 Sol, each over 3 Sol; automation may write (parked)'},
}
# Provider id, reasoning effort, output ceiling. Sol/Terra/Luna use the workbench-proven 'low' effort and 12K output.
MODEL_SETTINGS = {
    'astra': ('gpt-6-astra', 'max', None),
    'sol': ('gpt-6.1-sol', 'low', 12000),
    'terra': ('gpt-5.6-terra', 'low', 12000),
    'luna': ('gpt-6-luna', 'low', 12000),
}
AUTOMATION_HEADER = 'X-Automation'
ACTION_INTENT_HEADER = 'X-Action-Intent'


def mode_path():
    database = Path(os.environ.get('HANDOFFS_DB', Path(__file__).resolve().parents[1] / '.data' / 'handoffs.sqlite'))
    return Path(os.environ.get('HANDOFFS_AUTOMATION_MODE', database.with_name('automation-mode.json')))


def current(path=None):
    """The active mode record; manual when the setting is missing or invalid."""
    try:
        record = json.loads(Path(path or mode_path()).read_text(encoding='utf-8'))
        if record.get('mode') in MODES:
            return {**record, **MODES[record['mode']]}
    except (OSError, ValueError, AttributeError):
        pass
    return {'mode': 'manual', 'set_by': None, 'set_utc': None, 'note': 'default (no owner setting)', **MODES['manual']}


def set_mode(mode, by, note, path=None):
    if mode not in MODES:
        raise ValueError('Mode must be one of ' + ', '.join(MODES))
    if not isinstance(by, str) or not by.strip() or not isinstance(note, str) or not note.strip():
        raise ValueError('An owner name and a reason are required')
    path = Path(path or mode_path())
    try:
        history = json.loads(path.read_text(encoding='utf-8')).get('history', [])
    except (OSError, ValueError, AttributeError):
        history = []
    stamp = datetime.now(timezone.utc).isoformat()
    record = {'mode': mode, 'set_by': by, 'set_utc': stamp, 'note': note,
              'history': history + [{'mode': mode, 'set_by': by, 'set_utc': stamp, 'note': note}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1), encoding='utf-8')
    return current(path)


def models_by_level(mode):
    """Model settings for tree levels 1..n under a mode."""
    return {level: MODEL_SETTINGS[name] for level, name in enumerate(MODES[mode]['levels'], start=1)}


def apply_agent_names(plan, base='bob'):
    """Name a plan's agents in tree order: base for the root, then base-2, base-3, ... level by level.

    light: bob (Sol) over bob-2..4 (Terra). heavy: bob (Astra) over bob-2..4 (Sol). max: bob over bob-2..4, with bob-5..7, bob-8..10 and bob-11..13 under them.
    The human only ever talks to the root.
    """
    plan = json.loads(json.dumps(plan))
    plan['root_name'] = base
    number = 2
    level = list(plan.get('children', plan.get('workers', [])))
    while level:
        for node in level:
            node['name'] = f'{base}-{number}'
            number += 1
        level = [child for node in level for child in node.get('children', [])]
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=('show', 'set'))
    parser.add_argument('--mode', choices=list(MODES))
    parser.add_argument('--by')
    parser.add_argument('--note')
    args = parser.parse_args()
    if args.action == 'set':
        if not (args.mode and args.by and args.note):
            parser.error('set requires --mode, --by and --note')
        set_mode(args.mode, args.by, args.note)
    record = current()
    print(json.dumps({key: record[key] for key in ('mode', 'summary', 'agents', 'automated_writes', 'set_by', 'set_utc', 'note')}, indent=1))


if __name__ == '__main__':
    main()
