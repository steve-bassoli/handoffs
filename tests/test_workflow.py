import pytest
from pydantic import ValidationError

from app.workflow import Profile, digest, disposition, phase, profile


def test_cube_keeps_runtime_target_separate_from_completion():
    assert phase('awaiting_approval') == phase('decomposed') == 'Claimed'
    assert phase('open') == 'Posted' and phase('settled') == 'Closed'
    assert disposition('cancelled') != disposition('completed')
    target = Profile(validation_scope='LIVE').model_dump()
    assert 'verified' not in target
    assert target['knowledge'] == {'known': [], 'assumed': [], 'unknown': []}


def test_known_facts_need_sources_and_unknown_context_is_not_promoted():
    with pytest.raises(ValidationError):
        Profile(knowledge={'known': [{'statement': 'Works'}]})
    value = Profile(knowledge={'known': [{'statement': 'Source declares version', 'source': 'repo@sha:path:12'}],
                              'assumed': ['Runtime matches source'], 'unknown': ['Actual build?']}).model_dump()
    assert profile([{'data': {'profile': value}}]) == value
    assert profile([]) is None
    assert digest({'b': 2, 'a': 1}) == digest({'a': 1, 'b': 2})
