"""Exercise the real checkpoint UI handler with a small DOM boundary double."""
from pathlib import Path
import shutil
import subprocess

import pytest

from app.services import RuleError
from conftest import write


def test_continuation_does_not_bypass_unmet_ro3_decomposition(client):
    original = write(client, '/tasks', {'title': 'Composite fixture', 'goal': 'Verify RO3',
        'criteria': ['Integrated evidence'], 'gold': 5, 'complexity': 'MEDIUM'}).json()
    response = write(client, f"/tasks/{original['id']}/checkpoint", {'notes': 'Draft saved; decomposition remains pending.'})
    assert response.status_code == 200
    continuation = response.json()
    assert continuation['complexity'] == 'MEDIUM' and continuation['required_children'] == []
    with pytest.raises(RuleError, match='approved decomposition'):
        client.app.state.service.proofs.require_dependencies(continuation)


def test_checkpoint_form_waits_for_notes_and_opens_without_claiming():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for UI handler test')
    source = Path('app/static/app.js').read_text(encoding='utf-8')
    handler = source[source.index('function checkpointSection(data) {'):source.index('async function show(id) {')]
    checks = r'''
const assert = require('node:assert/strict');
const writes = [], opened = [];
let finished;
const user = 'steve';
function element(tag, text, cls) {
  return {tag, text, cls, children: [], append(...items) { this.children.push(...items); },
    querySelector(tag) { return this.children.find(child => child.tag === tag) || null; },
    focus() {}, remove() { this.removed = true; }};
}
const run = operation => { finished = operation(); };
const mutate = async (path, body) => { writes.push({path, body}); return {id: 'next', status: 'open'}; };
const show = async id => opened.push(id);
const message = () => {};
(async () => {
  const section = checkpointSection({id: 'original', creator: 'steve', status: 'working'});
  assert.equal(writes.length, 0);
  section.children.find(child => child.text === 'Save checkpoint').onclick();
  const form = section.querySelector('form');
  const notes = form.children[0].children[0];
  assert.equal(notes.required, true);
  notes.value = 'Done: traced. Remaining: review. Evidence: draft. Next: verify.';
  form.onsubmit({preventDefault() {}}); await finished;
  assert.deepEqual(writes, [{path: '/tasks/original/checkpoint', body: {notes: notes.value}}]);
  assert.equal(writes.some(write => /accept|take/.test(write.path)), false);
  const saved = checkpointSection({id: 'next', creator: 'steve', status: 'open',
    checkpoint: {previous_task_id: 'original', notes: '<script>untrusted notes</script>'}});
  assert.equal(saved.children.find(child => child.tag === 'pre').text, '<script>untrusted notes</script>');
  saved.children.find(child => child.tag === 'a').onclick({preventDefault() {}}); await finished;
  assert.deepEqual(opened, ['original']);
  const closed = checkpointSection({id: 'original', creator: 'steve', status: 'superseded', continuation_id: 'next'});
  assert.equal(closed.children.some(child => child.text === 'Save checkpoint'), false);
  assert.equal(closed.children.find(child => child.tag === 'a').href, '#task=next');
  const outsider = checkpointSection({id: 'other', creator: 'nate', claimant: 'will', status: 'working'});
  assert.equal(outsider.children.length, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run([node, '-e', handler + checks], check=True, capture_output=True, text=True)
