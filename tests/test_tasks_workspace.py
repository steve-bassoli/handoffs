"""One Tasks workspace entry with a local Browse / My tasks / Post task row (task 8ca606da)."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


def test_one_tasks_entry_and_local_row_replace_three_tabs():
    for page in ('index.html', 'dashboard.html'):
        nav = re.search(r'<nav aria-label="Workspace">(.*?)</nav>', (STATIC / page).read_text(encoding='utf-8')).group(1)
        expected = ['open', 'gremlins', 'agents', 'wallet']
        if page == 'index.html':
            expected.append('signoffs')
        assert re.findall(r'data-view="(\w+)"', nav) == expected, page
        assert 'My Tasks' not in nav and 'Post Task' not in nav
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    row = re.search(r'<div id="tasks-toolbar".*?</div>', html).group(0)
    assert re.findall(r'data-task-view="(\w+)"', row) == ['open', 'mine', 'post']


def test_selection_and_bindings_are_scoped_to_workspace_and_task_views():
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    assert "WORKSPACE_BUTTONS = 'nav[aria-label=\"Workspace\"] button[data-view]'" in script
    assert "querySelectorAll('nav button')" not in script
    assert "TASK_VIEWS.has(view) ? 'open' : view" in script and "setAttribute('aria-current', 'page')" in script
    # Legacy #view=open|mine|post links still route through the shared helper.
    assert "const views = new Set(['open', 'mine', 'post'," in (STATIC / 'workspace-navigation.js').read_text(encoding='utf-8')


def test_confirmed_post_stays_confirmed_when_refresh_fails():
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the pure JavaScript posting check')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const mutate = source.slice(source.indexOf('async function mutate('), source.indexOf('const acceptStages'));
const context = {messages: [], document: {querySelectorAll: () => []}, $: () => ({}),
  message(text, error) { context.messages.push([text, Boolean(error)]); },
  api: async () => ({id: 'task-1', status: 'pending'}),
  stats: async () => { throw new Error('stats offline'); }, show: async () => {}};
vm.runInNewContext(mutate + '\nthis.mutate = mutate;', context);
(async () => {
  const posted = await context.mutate('/tasks', {}, 'Task posted:');
  assert.equal(posted.id, 'task-1', 'the created task is still returned so the form resets');
  const [text, error] = context.messages.at(-1);
  assert.ok(error && text.includes('task-1') && text.includes('do not post it again'), text);
  await assert.rejects(context.mutate('/tasks/x/take', {}), /stats offline/, 'other writes keep their behavior');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_late_task_detail_cannot_pull_the_user_back():
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the pure JavaScript race check')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const show = source.slice(source.indexOf('async function show(id) {'), source.indexOf("  for (const section of ['board'")) + '}';
let release;
const writes = [];
const context = {treeEpoch: 0, aiPoll: null, proofPoll: null, selected: null, view: 'mine', user: 'steve', encodeURIComponent,
  clearTimeout() {}, api: () => new Promise(resolve => { release = resolve; }),
  history: {replaceState: (...args) => writes.push(args)}, $: () => null};
vm.runInNewContext(show + '\nthis.show = show;', context);
(async () => {
  const late = context.show('slow-task');
  context.treeEpoch++;  // The user navigated elsewhere while the task was loading.
  release({id: 'slow-task'});
  await late;
  assert.equal(context.selected, null, 'a stale detail must not select itself');
  assert.deepEqual(writes, [], 'a stale detail must not rewrite history');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
