import importlib.util
import json
from pathlib import Path

import pytest

from app.decomposition_teaching import build_teaching
from app.decomposition_visibility import project_decomposition_visibility


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/decomposition_visibility_v1.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', FIXTURE['cases'], ids=lambda case: case['name'])
def test_visibility_projection_matches_fixture(case):
    original = json.dumps(case['input'], sort_keys=True)
    assert project_decomposition_visibility(**case['input']) == case['expected']
    assert json.dumps(case['input'], sort_keys=True) == original


def test_visibility_fixture_on_both_surfaces():
    # Load the sibling harness explicitly; do not depend on tests being a package.
    spec = importlib.util.spec_from_file_location(
        '_visibility_view_harness', ROOT / 'tests/test_decomposition_visibility_view.py')
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    harness.run_node(r'''
const labels = {valid: 'Valid split', violation: 'Violation',
  unknown: 'Unknown', not_yet_split: 'Not yet split'};
freeze(input.fixture);
freeze(input.teaching);
for (const sample of input.fixture.cases) {
  const expected = sample.expected.tickets;
  for (const render of [window.renderDecompositionHierarchy, window.renderDecompositionFlow]) {
    const calls = [];
    const host = element('div');
    const root = render({hostNode: host, visibility: sample.expected,
      teaching: input.teaching, onNavigate: id => calls.push(id)});
    assert.equal(root.children[0], host);
    const panel = root.children[1];
    const rows = nodes(panel).filter(n => n.attrs['data-ticket-id'] !== undefined);
    assert.deepEqual(rows.map(row => row.attrs['data-ticket-id']), expected.map(row => row.id));
    assert.deepEqual(rows.map(row => row.attrs['data-visibility-state']), expected.map(row => row.status));
    rows.forEach((row, index) => {
      const record = expected[index];
      const control = row.children[0];
      assert.equal(control.tag, 'button');
      assert.equal(control.textContent, record.id);
      assert.equal(row.children[1].textContent, record.title);
      assert.equal(row.children[2].textContent, labels[record.status]);
      const reasonNodes = nodes(row).filter(n => n.attrs['data-visibility-reason'] !== undefined);
      assert.deepEqual(reasonNodes.map(n => n.textContent), record.reasons);
      assert.deepEqual(reasonNodes.map(n => n.attrs['data-visibility-reason']), record.reasons);
      control.listeners.click();
    });
    assert.deepEqual(calls, expected.map(row => row.id));
    assert.ok(texts(panel).includes(input.teaching.explanation));
  }
}
assert.equal(sideEffects, 0);
''', fixture=FIXTURE, teaching=build_teaching())
