import pytest
from pydantic import ValidationError

from app.workflow import Profile, constellation, digest, disposition, phase, profile, validate_dependencies


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


def test_shared_prerequisites_are_links_not_copied_work():
    nodes = [{'id': 'root'}, {'id': 'one', 'parent_id': 'root', 'depends_on': ['setup']},
             {'id': 'two', 'parent_id': 'root', 'depends_on': ['setup']}, {'id': 'setup'}]
    graph = constellation(nodes)
    assert len(graph['nodes']) == 4 and len(graph['edges']) == 4
    assert validate_dependencies(nodes, 'root', ['setup']) == ['setup']
    for source, targets in [('setup', ['one']), ('one', ['root']), ('root', ['root']), ('one', ['missing']), ('one', ['setup', 'setup'])]:
        with pytest.raises(ValueError):
            validate_dependencies(nodes, source, targets)
