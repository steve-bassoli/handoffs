"""Three-way decomposition and a SMALL-only managed Git commit gate (stdlib only)."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


def validate_plan(steps):
    seen = set()
    leaves = []

    def visit(step, expected=None):
        if not isinstance(step, dict) or not isinstance(step.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', step['id']):
            raise ValueError('Every plan item needs a stable ID')
        if step['id'] in seen or len(seen) >= 200:
            raise ValueError('Plan IDs must be unique; at most 200 items')
        seen.add(step['id'])
        level = step.get('complexity', '').upper()
        level = 'SMALL' if level == 'LOW' else level
        if level not in ('HIGH', 'MEDIUM', 'SMALL') or (expected and level != expected):
            raise ValueError('HIGH requires MEDIUM children; MEDIUM requires SMALL children; LOW means SMALL')
        title = step.get('title')
        children = step.get('children')
        files = step.get('files')
        if not isinstance(title, str) or not title.strip() or not isinstance(children, list) or not isinstance(files, list):
            raise ValueError('Every item requires title, children, and files')
        if any(not isinstance(path, str) or not path or path != str(PurePosixPath(path)) or
               path.startswith('/') or '\\' in path or ':' in path or '..' in PurePosixPath(path).parts
               for path in files) or len(files) != len(set(files)):
            raise ValueError('Plan files must be distinct exact relative paths')
        if level == 'SMALL':
            if children:
                raise ValueError('SMALL is a leaf and cannot have children')
            leaves.append({**step, 'complexity': level})
            return {**step, 'complexity': level}
        if files or len(children) != 3:
            raise ValueError(level + ' must have exactly 3 children and no commit files')
        return {**step, 'complexity': level, 'children': [visit(child, 'MEDIUM' if level == 'HIGH' else 'SMALL') for child in children]}

    if not isinstance(steps, list) or not steps:
        raise ValueError('Provide at least one plan item')
    normalized = [visit(step) for step in steps]
    return normalized, leaves


def commit(repository, steps, step_id, message, run=subprocess.run):
    normalized, leaves = validate_plan(steps)
    leaf = next((item for item in leaves if item['id'] == step_id), None)
    if not leaf or not leaf['files']:
        raise ValueError('Only a SMALL leaf with declared files can commit')
    prefix = ['git', '-C', str(repository)]
    staged = run(prefix + ['diff', '--cached', '--name-only', '-z'], check=True, capture_output=True).stdout.decode().split('\0')
    paths = {path for path in staged if path}
    if not paths or not paths <= set(leaf['files']):
        raise ValueError('Stage only files declared by the selected SMALL leaf')
    fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    receipt = f"Complexity: SMALL\nPlan-step: {step_id}\nPlan-sha256: {fingerprint}"
    return run(prefix + ['commit', '-m', message, '-m', receipt], check=True, capture_output=True, text=True).stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'commit'))
    parser.add_argument('--plan', required=True)
    parser.add_argument('--step')
    parser.add_argument('--repository')
    parser.add_argument('--message')
    args = parser.parse_args(argv)
    try:
        document = json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
        steps = document['steps'] if isinstance(document, dict) else document
        if args.action == 'commit':
            if not args.step or not args.repository or not args.message:
                parser.error('commit requires --step, --repository, and --message')
            print(commit(args.repository, steps, args.step, args.message).strip())
        else:
            normalized, leaves = validate_plan(steps)
            print(json.dumps({'steps': normalized, 'small_leaves': len(leaves)}, indent=2))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
