"""One Tasks workspace entry with a local Browse / My tasks / Post task row (task 8ca606da)."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


def test_one_tasks_entry_and_local_row_replace_three_tabs():
    for page in ('index.html', 'dashboard.html'):
        nav = re.search(r'<nav aria-label="Workspace">(.*?)</nav>', (STATIC / page).read_text(encoding='utf-8')).group(1)
        # Decisions (the human-decision digest, task acbeeff0) sits right after Tasks on the main page.
        expected = ['open', 'signoffs', 'gremlins', 'agents', 'wallet'] if page == 'index.html' else ['open', 'gremlins', 'agents', 'wallet']
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


def test_post_lock_identity_snapshot_and_cancel():
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for posting race checks')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const posting = source.slice(source.indexOf("$('post-form').onsubmit = e => {"), source.indexOf("if (typeof window !== 'undefined') window.addEventListener('hashchange'"));
const mutation = source.slice(source.indexOf('async function mutate('), source.indexOf('const acceptStages'));
function fixture() {
  let release;
  const fields = {title: 'Original', goal: 'Goal', criteria: 'One', repository: '', context_links: '', complexity: 'LOW', work_type: 'implementation', gold: '150', target: ''};
  const controls = [{disabled: false}, {disabled: true}, {disabled: false, value: 'chosen.zip'}];
  const form = {elements: controls, resets: 0, reset() { this.resets++; fields.title = ''; controls[2].value = ''; }};
  const picker = {value: 'steve', disabled: false};
  const cancel = {};
  const nodes = {'post-form': form, user: picker, 'post-cancel': cancel};
  const c = {user: 'steve', session: null, treeEpoch: 0, postPending: false, calls: [], messages: [], encodes: 0, confirmation: false,
    $: id => nodes[id], document: {querySelectorAll: () => []},
    FormData: class { constructor() { this.values = {...fields}; } get(key) { return this.values[key]; } },
    confirm: () => c.confirmation,
    message: (text, error) => c.messages.push([text, error]),
    run: async operation => { try { await operation(); } catch (error) { c.message(error.message, true); } },
    postSourceZip: () => { c.encodes++; assert.ok(picker.disabled); assert.ok(controls.every(x => x.disabled)); return new Promise(resolve => { release = resolve; }); },
    api: async (path, body) => { c.calls.push({path, body, actor: c.user, token: c.session?.access_token}); return {id: 'task-1'}; },
    stats: async () => {}, show: async () => {},
    renderAuth: () => { picker.disabled = !!c.session || c.postPending; }
  };
  vm.runInNewContext(mutation + '\n' + posting, c);
  return {c, form, controls, picker, cancel, fields, submit: () => form.onsubmit({target: form, preventDefault() {}}), release: () => release('ZIP')};
}
(async () => {
  let f = fixture();
  const pending = f.submit();
  assert.equal(f.c.encodes, 1);
  await f.submit();
  f.cancel.onclick();
  assert.equal(f.form.resets, 0);
  assert.equal(f.c.encodes, 1);
  f.fields.title = 'Changed programmatically';
  f.release(); await pending;
  assert.equal(f.c.calls.length, 1);
  assert.equal(f.c.calls[0].actor, 'steve');
  assert.equal(f.c.calls[0].body.title, 'Original');
  assert.equal(f.c.calls[0].body.source_zip, 'ZIP');
  assert.equal(f.form.resets, 1);
  assert.deepEqual(f.controls.map(x => x.disabled), [false, true, false]);
  assert.equal(f.picker.disabled, false);
  for (const change of [
    f => { f.c.user = 'other'; },
    f => { f.picker.value = 'other'; },
    f => { f.c.session = {access_token: 'new', user_id: 'steve'}; },
    f => { f.c.session.access_token = 'rotated'; },
    f => { f.c.session = null; },
    f => { f.c.treeEpoch++; }
  ]) {
    f = fixture();
    f.c.session = {access_token: 'initial', user_id: 'steve'};
    const p = f.submit(); change(f); f.release(); await p;
    assert.equal(f.c.calls.length, 0);
    assert.equal(f.form.resets, 0);
    assert.ok(f.c.messages.some(([text, error]) => error && text.includes('Nothing was posted')));
    assert.equal(f.c.postPending, false);
  }
  f = fixture();
  f.c.postSourceZip = async () => { throw new Error('encoding failed'); };
  await f.submit();
  assert.equal(f.c.calls.length, 0);
  assert.equal(f.c.postPending, false);
  assert.equal(f.picker.disabled, false);
  assert.deepEqual(f.controls.map(x => x.disabled), [false, true, false]);
  f = fixture();
  f.cancel.onclick();
  assert.equal(f.form.resets, 0);
  f.c.confirmation = true; f.cancel.onclick();
  assert.equal(f.form.resets, 1);
  assert.equal(f.fields.title, '');
  assert.equal(f.controls[2].value, '');
  assert.equal(f.c.calls.length, 0);
  const html = fs.readFileSync('app/static/index.html', 'utf8');
  assert.match(html, /<form id="post-form">[\s\S]*?<button id="post-cancel" type="button">Cancel<\/button>[\s\S]*?<\/form>/);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_post_draft_owner_return_switch_and_reset():
    import shutil
    import subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for draft ownership checks')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const helpers = source.slice(source.indexOf('let postDraftOwner = null;'), source.indexOf('function identityHeaders()'));
const navigation = source.slice(source.indexOf('const TASK_VIEWS ='), source.indexOf('async function mutate('));
const binding = source.slice(source.indexOf("if (typeof document !== 'undefined' && $('post-form'))"), source.indexOf("$('post-form').onsubmit = e => {"));
function fixture() {
  const nodes = {}, listeners = {};
  const form = {value: '', zip: '', resets: 0,
    before(label) { nodes[label.id] = label; },
    addEventListener(type, handler) { listeners[type] = handler; },
    reset() { listeners.reset(); this.value = ''; this.zip = ''; this.resets++; }};
  nodes['post-form'] = form;
  const c = {user: 'steve', session: null, view: 'post', selected: null,
    aiPoll: null, proofPoll: null, clearTimeout() {}, messages: [],
    $: id => nodes[id] || (nodes[id] = {hidden: true}),
    document: {createElement: () => ({setAttribute() {}, textContent: ''}), querySelectorAll: () => []},
    history: {replaceState() {}}, location: {pathname: '/', search: ''},
    message: text => c.messages.push(text), stats: async () => {}, board: async () => {}};
  vm.runInNewContext(helpers + navigation + binding, c);
  return {c, form, listeners, nodes};
}
(async () => {
  let f = fixture();
  f.form.value = 'Private draft'; f.form.zip = 'chosen.zip'; f.listeners.input();
  assert.match(f.nodes['post-draft-owner'].textContent, /Draft owner: steve \(demo\)/);
  assert.equal(f.nodes['post-draft-owner'].hidden, false);
  await f.c.navigate('open'); await f.c.navigate('post');
  assert.equal(f.form.value, 'Private draft');
  assert.equal(f.form.zip, 'chosen.zip');
  assert.equal(f.form.resets, 0);
  assert.match(f.nodes['post-draft-owner'].textContent, /Draft owner: steve/);
  for (const change of [
    c => { c.user = 'other'; },
    c => { c.session = {access_token: 'new', user_id: 'steve'}; },
    c => { c.session.access_token = 'rotated'; },
    c => { c.session = {...c.session}; },
    c => { c.session = null; }
  ]) {
    f = fixture();
    f.c.session = {access_token: 'initial', user_id: 'steve'};
    f.form.value = 'Private draft'; f.form.zip = 'chosen.zip'; f.listeners.change();
    assert.match(f.nodes['post-draft-owner'].textContent, /steve \(signed in\)/);
    change(f.c); await f.c.navigate('post');
    assert.equal(f.form.value, ''); assert.equal(f.form.zip, '');
    assert.equal(f.form.resets, 1);
    assert.match(f.nodes['post-draft-owner'].textContent, /Draft cleared.*identity or session changed/);
    assert.ok(f.c.messages.some(text => text.includes('Nothing was transferred')));
    f.form.value = 'New draft'; f.listeners.input();
    assert.match(f.nodes['post-draft-owner'].textContent, /Draft owner:/);
    f.form.reset();
    assert.equal(f.nodes['post-draft-owner'].hidden, true);
  }
  // The auth and picker entry points must reach the ownership check.
  const auth = source.slice(source.indexOf('function renderAuth()'), source.indexOf('function clearSession()'));
  assert.ok(auth.includes('syncPostDraftOwner()'));
  const picker = source.slice(source.indexOf("$('user').onchange"), source.indexOf("$('signin-form').onsubmit"));
  assert.ok(picker.includes("await navigate('open')"));
  // Helpers are safe to define and synchronize without a DOM.
  vm.runInNewContext(helpers + '\nsyncPostDraftOwner();', {user: 'steve', session: null});
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
