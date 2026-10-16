from types import SimpleNamespace

import pytest

from app.jira_pr import main, pr_title


@pytest.mark.parametrize('summary', [
    '[CPC-123] Fix date picker', 'CPC-123: Fix date picker',
    'CPC-123 - Fix date picker', 'Fix date picker - CPC-123',
    'Fix date picker [CPC-123]', 'Fix date picker',
])
def test_issue_key_never_reaches_title(summary):
    assert pr_title(summary, 'CPC-123') == 'Fix date picker'


@pytest.mark.parametrize('summary', ['CPC-123', '[CPC-123]',
                                      'CPC-999: Fix picker', 'Fix\nCPC-123'])
def test_unsafe_title_stops_before_publication(summary):
    with pytest.raises(ValueError):
        pr_title(summary, 'CPC-123')


def test_actual_create_arguments_keep_key_out_of_title(monkeypatch):
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout='https://github.com/example/source/pull/1\n')
    monkeypatch.setattr('app.jira_pr.subprocess.run', run)
    main(['--repository', 'example/source', '--issue-key', 'CPC-123',
          '--summary', '[CPC-123] Fix date picker', '--body-file', 'evidence.md',
          '--base', 'main', '--head', 'codex/cpc-123-picker', '--draft'])
    assert len(commands) == 1
    command = commands[0]
    assert command[command.index('--title') + 1] == 'Fix date picker'
    assert command[command.index('--head') + 1] == 'codex/cpc-123-picker'
    assert command[command.index('--body-file') + 1] == 'evidence.md'
    assert '--draft' in command
