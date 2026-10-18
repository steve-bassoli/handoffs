"""Push one authorized existing commit and record exact remote delivery."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit


def publish(repository, remote, branch, expected_url, commit, receipt, authorized=False):
    result = {'state': 'blocked', 'published': False, 'commit': commit,
              'remote': remote, 'branch': branch, 'push_attempted': False,
              'remote_commit': None, 'next_action': 'Resolve the reported blocker and rerun with the same commit.'}
    destination = Path(receipt)

    def save():
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.tmp')
        temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
        os.replace(temporary, destination)

    def git(*args, allow_failure=False):
        process = subprocess.run(['git', '-c', 'safe.directory=' + str(root),
            '-c', 'push.followTags=false', '-C', str(root), *args],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
        if process.returncode and not allow_failure:
            # Do not copy arbitrary remote output, credentials or source into receipts.
            raise ValueError('Git operation failed: ' + args[0] + ' (exit ' + str(process.returncode) + ')')
        return process

    try:
        save()
        if not authorized:
            raise ValueError('Publication authorization is required; preserve task-specific approval requirements')
        root = Path(repository).resolve(strict=True)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', remote):
            raise ValueError('Invalid remote name')
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
            raise ValueError('Use the full existing commit SHA')
        git('check-ref-format', 'refs/heads/' + branch)
        urls = git('remote', 'get-url', '--push', '--all', remote).stdout.splitlines()
        if urls != [expected_url]:
            raise ValueError('Push destination does not match the verified intended URL')
        parsed = urlsplit(expected_url)
        if parsed.scheme in ('http', 'https') and (parsed.username or parsed.password):
            raise ValueError('Use a credential-free remote URL')
        mirror = git('config', '--bool', '--get', 'remote.' + remote + '.mirror', allow_failure=True)
        if mirror.stdout.strip() == 'true':
            raise ValueError('Mirror remotes are not supported')
        if git('branch', '--show-current').stdout.strip() != branch:
            raise ValueError('Current branch differs from the intended branch')
        if git('rev-parse', 'HEAD').stdout.strip() != commit:
            raise ValueError('Commit must be the current branch HEAD; do not publish unrelated commits')
        ref = 'refs/heads/' + branch
        def remote_head():
            lines = git('ls-remote', '--refs', remote, ref).stdout.splitlines()
            if not lines:
                return None
            if len(lines) != 1 or lines[0].split()[1] != ref:
                raise ValueError('Remote branch verification returned unexpected refs')
            return lines[0].split()[0]
        result['remote_commit'] = remote_head()
        if result['remote_commit'] != commit:
            result['push_attempted'] = True
            save()
            git('push', '--no-follow-tags', remote, commit + ':' + ref)
            result['remote_commit'] = remote_head()
        if result['remote_commit'] != commit:
            raise ValueError('Push returned but exact remote HEAD verification failed')
        result.update(state='published', published=True, next_action=None)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        result['error'] = str(error) if isinstance(error, ValueError) else type(error).__name__
    save()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'remote', 'branch', 'expected-url', 'commit', 'receipt'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--authorized', action='store_true',
                        help='Attest applicable user/standing publication authority; not an authentication mechanism')
    args = vars(parser.parse_args())
    result = publish(**args)
    print(json.dumps(result))
    return 0 if result['published'] else 1


if __name__ == '__main__':
    sys.exit(main())
