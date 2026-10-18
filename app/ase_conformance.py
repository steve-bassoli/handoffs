"""Narrow, read-only ASE evidence; fingerprints identify bytes, not certification."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat

LIMIT = 131072
ALLOWLIST = ('app/complexity.py', 'PROJECT_CHARTER.md')
VALIDATOR_SOURCE = '''DECOMPOSITION = {'HIGH': ('HIGH', 'MEDIUM'), 'MEDIUM': ('LOW',), 'LOW': ()}
MIN_CHILDREN = 2

def validate_task_split(parent, levels):
    allowed = DECOMPOSITION.get(parent, ())
    if len(levels) >= MIN_CHILDREN and len(set(levels)) == 1 and levels[0] in allowed:
        return levels[0]
    raise ValueError('HIGH needs multiple HIGHs or MEDIUMs without mixed levels; MEDIUM needs multiple LOWs; LOW cannot decompose')
'''


def _extract_validator(raw, expected_sha256):
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('source-binding mismatch')
    tree = ast.parse(raw.decode('utf-8'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == 'validate_task_split']
    template = ast.parse(VALIDATOR_SOURCE).body[-1]
    if len(functions) != 1 or ast.dump(functions[0]) != ast.dump(template):
        raise ValueError('unsupported validator AST')
    constants = {}
    for name in ('DECOMPOSITION', 'MIN_CHILDREN'):
        assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                       and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                       and n.targets[0].id == name]
        if len(assignments) != 1:
            raise ValueError('unsupported constants')
        constants[name] = ast.literal_eval(assignments[0].value)
    if not isinstance(constants['DECOMPOSITION'], dict):
        raise ValueError('unsupported decomposition constant')
    if type(constants['MIN_CHILDREN']) is not int:
        raise ValueError('unsupported minimum constant')
    namespace = {'__builtins__': {'len': len, 'set': set, 'ValueError': ValueError}, **constants}
    module = ast.Module(body=[functions[0]], type_ignores=[])
    exec(compile(module, '<bounded-decomposition>', 'exec'), namespace)
    return namespace['validate_task_split']


def _descriptor_reads_available():
    return (all(hasattr(os, name) for name in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK'))
            and os.open in os.supports_dir_fd)


def _bounded_bytes(handle):
    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
        raise ValueError('source is not a regular file')
    raw = handle.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('source exceeds read bound')
    return raw


def _read_descriptor(root, relative):
    """Reject symlinks using descriptor-relative opens at every component."""
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = Path(relative).parts
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(source, 'rb') as handle:
            return _bounded_bytes(handle)
    finally:
        os.close(fd)


def _reject_link(info):
    # Windows junctions and other reparse points are not ordinary directories.
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0)
            & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
        raise ValueError('source path contains a link or reparse point')


def _read_fallback(root, relative):
    """Bounded ordinary reads for stable checkouts, not a race-proof sandbox.

    Inspect the selected root and each allowlisted component before opening.
    Never use this backend to inspect an adversarial concurrently changing tree.
    """
    base = Path(root)
    info = base.lstat()
    _reject_link(info)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('checkout root is not a directory')
    canonical_root = base.resolve(strict=True)
    target = base
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        target = target / part
        info = target.lstat()
        _reject_link(info)
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError('source parent is not a directory')
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('source is not a regular file')
    resolved = target.resolve(strict=True)
    if os.path.commonpath((str(canonical_root), str(resolved))) != str(canonical_root):
        raise ValueError('source escapes selected checkout')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(target, flags), 'rb') as handle:
        opened = os.fstat(handle.fileno())
        if not os.path.samestat(info, opened):
            raise ValueError('source changed during open')
        return _bounded_bytes(handle)


def _read(root, relative):
    """Read only an exact allowlisted source, bounded to LIMIT bytes."""
    if relative not in ALLOWLIST:
        raise ValueError('source is not allowlisted')
    if _descriptor_reads_available():
        return _read_descriptor(root, relative)
    return _read_fallback(root, relative)


def _probe(raw, digest):
    validator = _extract_validator(raw, digest)
    positive = [('HIGH', ['HIGH', 'HIGH']), ('HIGH', ['MEDIUM', 'MEDIUM']),
                ('MEDIUM', ['LOW', 'LOW'])]
    negative = [('HIGH', ['HIGH', 'MEDIUM']), ('HIGH', ['LOW', 'LOW']),
                ('MEDIUM', ['HIGH', 'HIGH']), ('MEDIUM', ['MEDIUM', 'MEDIUM']),
                ('LOW', ['LOW', 'LOW']), ('LOW', ['HIGH', 'HIGH']),
                ('LOW', ['MEDIUM', 'MEDIUM']), ('HIGH', []),
                ('HIGH', ['HIGH']), ('UNKNOWN', ['LOW', 'LOW'])]
    failures = []
    for parent, levels in positive:
        try:
            if validator(parent, levels[:]) != levels[0]:
                failures.append('valid split returned an unexpected result')
        except Exception:
            failures.append('valid split raised')
    for parent, levels in negative:
        try:
            validator(parent, levels[:])
            failures.append('invalid split accepted')
        except ValueError:
            pass
        except Exception:
            failures.append('invalid split raised an unexpected exception')
    return sorted(set(failures))


def build_scorecard(repo_root):
    root = os.path.abspath(os.fspath(repo_root))
    sources, errors = {}, {}
    for path in ALLOWLIST:
        try:
            sources[path] = _read(root, path)
        except (OSError, ValueError) as error:
            errors[path] = type(error).__name__ + ': source unavailable or unsupported'
    rows = []
    for identity in ('decomposition', 'human_gates', 'humane_limits'):
        path = 'app/complexity.py' if identity == 'decomposition' else 'PROJECT_CHARTER.md'
        row = dict(id=identity, status='gap', scope='Selected checkout: ' + root,
                   reason=errors.get(path, 'Insufficient relevant evidence'), evidence=[], conflicts=[])
        if path in sources:
            raw = sources[path]
            digest = hashlib.sha256(raw).hexdigest()
            row['evidence'] = [dict(path=path, sha256=digest, kind='source')]
            if identity == 'decomposition':
                row['scope'] += ('; source-extracted validator AST and bounded suite only; '
                                 'enclosing-module execution, runtime bindings and downstream enforcement are not assessed')
                try:
                    row['conflicts'] = _probe(raw, digest)
                    row['status'] = 'partial' if row['conflicts'] else 'pass'
                    row['reason'] = 'Probe contradictions' if row['conflicts'] else 'Named split suite succeeded'
                    if not row['conflicts']:
                        row['evidence'].append(dict(path=path, sha256=digest, kind='behavior'))
                except Exception as error:
                    row.update(status='partial', reason='Probe unavailable: ' + type(error).__name__)
            else:
                text = raw.decode('utf-8', errors='replace').lower()
                terms = ('human', 'approval', 'consent') if identity == 'human_gates' else ('pressure', 'rest', 'protected')
                if any(term in text for term in terms):
                    row.update(status='partial', reason='Relevant charter text only; enforcement untested')
        rows.append(row)
    return dict(schema_version='ase-narrow-v1', scope='Bounded selected-checkout evidence, not certification',
                properties=rows, limitations=['Per-request attribution unresolved.',
                'Realtime dashboard unverified.', 'Demonstrated/persistent learning unverified.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_scorecard(args.repo_root), sort_keys=True))


if __name__ == '__main__':
    main()
