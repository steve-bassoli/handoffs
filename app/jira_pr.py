"""Create a JIRA-linked review PR without putting issue keys in its title."""
import argparse
import re
import subprocess


def pr_title(summary: str, issue_key: str) -> str:
    if not re.fullmatch(r'[A-Z][A-Z0-9]+-[0-9]+', issue_key):
        raise ValueError('Invalid JIRA issue key')
    key = re.escape(issue_key)
    pattern = rf'\[\s*{key}\s*\]|(?<![\w-]){key}(?![\w-])'
    title = re.sub(pattern, '', summary, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip(' \t\r\n[]:|-\u2013\u2014')
    if not title or re.search(r'\b[A-Z][A-Z0-9]+-[0-9]+\b', title, re.IGNORECASE):
        raise ValueError('PR title must be nonempty and contain no JIRA issue keys')
    if '\n' in summary or '\r' in summary:
        raise ValueError('PR summary must be a single line')
    return title


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'issue-key', 'summary', 'body-file', 'base', 'head'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--draft', action='store_true')
    args = parser.parse_args(argv)
    title = pr_title(args.summary, args.issue_key)
    if args.head == args.base:
        raise ValueError('PR head must be a non-default issue branch, different from base')
    command = ['gh', 'pr', 'create', '--repo', args.repository, '--title', title,
               '--body-file', args.body_file, '--base', args.base, '--head', args.head]
    if args.draft:
        command.append('--draft')
    # No shell interpolation or automatic retry of this external write.
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    print(result.stdout.strip())


if __name__ == '__main__':
    main()
