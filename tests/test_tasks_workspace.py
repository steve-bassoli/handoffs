"""One Tasks workspace entry with a local Browse / My tasks / Post task row (task 8ca606da)."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


def test_one_tasks_entry_and_local_row_replace_three_tabs():
    for page in ('index.html', 'dashboard.html'):
        nav = re.search(r'<nav aria-label="Workspace"[^>]*>(.*?)</nav>', (STATIC / page).read_text(encoding='utf-8'), re.S).group(1)
        # Focused navigation (task 5b86fe29): Decisions first, Tasks second, Gremlins > Watson, then More.
        assert re.findall(r'data-view="(\w+)"', nav) == ['signoffs', 'bobsue', 'gallery', 'open', 'gremlins', 'agents', 'wallet'], page
        more = re.search(r'<details class="workspace-disclosure workspace-more">(.*?)</details>', nav, re.S).group(1)
        assert 'id="dashboard-link"' in more and 'data-view="agents"' in more and 'data-view="wallet"' in more, page
        assert 'Watson · simulation' in re.search(r'workspace-gremlins">(.*?)</details>', nav, re.S).group(1), page
        assert 'My Tasks' not in nav and 'Post Task' not in nav
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    # Gold lives under More with its ids intact; the Decisions count says what it counts.
    assert html.count('id="gold"') == 1 and 'id="gold"' in re.search(r'workspace-more">(.*?)</details>', html, re.S).group(1)
    assert 'Zero is not blanket approval.' in html and 'aria-describedby="decisions-count-note"' in html
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


def test_long_titles_wrap_inside_task_cards():
    # Bob team free play (caaaa25b): one unbroken 160-character title widened a 375px page to 2148px.
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert '#board #cards > .card { min-width: 0; overflow-wrap: anywhere; }' in css


def test_task_board_paging_buttons_are_thumb_sized():
    # Bob team free play #2 (e0250fcb): Previous and Next measured 36.8px tall at 375px.
    assert '#board .paging button { min-height: 44px; }' in (STATIC / 'styles.css').read_text(encoding='utf-8')


def test_task_search_is_16px_on_phones():
    # Bob team free play #3 (ac5f481e): phone browsers zoom into inputs under 16px on focus.
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert '#board #search { font-size: 16px; }' in css.split('@media (max-width: 640px)')[-1]


def test_watson_report_is_a_named_keyboard_region():
    # Bob team free play #5 (6e08fc7b): the scrollable comparison report gets a tab stop, a name and a focus ring.
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert '<pre id="gremlins-output" class="proof-text" tabindex="0" role="region" aria-label="Offline comparison report"' in html
    assert '#gremlins-output:focus-visible' in (STATIC / 'styles.css').read_text(encoding='utf-8')


def test_post_form_marks_optional_fields():
    # Bob team free play #6 (74bcc7d0): the server defaults repository and context_links to empty.
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert 'Source repository (optional)<input name="repository"' in html and 'Context links (optional) · one per line' in html
    from app.main import PostTask
    assert PostTask(title='t', goal='g', criteria=['c'], gold=1).repository == '' and PostTask(title='t', goal='g', criteria=['c'], gold=1).context_links == []


def test_task_detail_lineage_buttons_are_thumb_sized():
    # Bob team free play #7 (ef98fe3a): a one-line related-task button measured 39.6px.
    assert '#detail .lineage button { min-height: 44px; }' in (STATIC / 'styles.css').read_text(encoding='utf-8')


def test_header_wraps_instead_of_overflowing():
    # Bob team free play #8 (aef14fef): at 671px the sign-in form stuck out 9px (scrollWidth 680 vs 671).
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert 'header { min-height: 72px; display: flex; flex-wrap: wrap;' in css
    assert css.count('#signin-form { min-width: 0; max-width: 100%; }') == 1


def test_agent_roster_is_a_named_keyboard_region():
    # Bob team free play #9 (50c8cbbf): the roster scrolls sideways on phones; give keyboard users a handle.
    assert '<div class="agent-table-wrap" tabindex="0" role="region" aria-label="Registered agent runs">' in (STATIC / 'index.html').read_text(encoding='utf-8')
    assert '#agents .agent-table-wrap:focus-visible' in (STATIC / 'styles.css').read_text(encoding='utf-8')


def test_roster_working_on_column_wraps_with_a_readable_floor():
    # Bob team free play #10 (126b1cb5): Working on rendered 1947px wide at 375px; a first try without a floor collapsed it to 32px.
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert '#agents .agent-table td:nth-child(3) { min-width: 20rem; width: 28rem; max-width: 28rem; white-space: normal; overflow-wrap: anywhere; }' in css


def test_skip_link_moves_focus_without_changing_the_route():
    # Bob team free play #11 (7d37cc91): six Tab presses reached Decisions; the skip link must not rewrite the #view hash.
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert html.index('class="skip-link" href="#main-content"') < html.index('<header>') and '<main id="main-content" tabindex="-1">' in html
    assert "event.preventDefault(); $('main-content').focus();" in (STATIC / 'app.js').read_text(encoding='utf-8')


def test_menus_show_an_open_closed_chevron():
    # Bob team free play #12 (d3760307): the native disclosure marker is hidden, so Gremlins and More had no open cue.
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert '.workspace-nav .workspace-disclosure > summary::before' in css and '.workspace-nav .workspace-disclosure[open] > summary::before { transform: rotate(45deg); }' in css


def test_show_closed_toggle_is_thumb_sized():
    # Bob team free play #13 (275ce9c9): the Show closed label measured 16px tall at 375px.
    assert '#mine-filters label:has(> #show-closed) { min-height: 44px; }' in (STATIC / 'styles.css').read_text(encoding='utf-8')


def test_watson_page_says_how_to_start():
    # Bob team free play #14 (5db13aee): the Watson simulation page opened on a blank form with no starting step.
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    start = html.index('<p id="gremlins-start">')
    assert start < html.index('<button id="gremlins-example">') and 'Then choose Run offline comparison.' in html[start:start + 200]


def test_task_search_has_a_visible_label():
    # Bob team free play #15 (f2b87f1e): the placeholder was the only visible label and vanished while typing.
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert '<label class="task-search" for="search">Find a task<input id="search"' in html


def test_history_evidence_headers_toggle_from_the_whole_shaded_area():
    # Bob team free play #16 (4ffe2bc3): the summary was 16px tall inside a 42px shaded box, so taps on the padding did nothing.
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert '.history-event details > summary { cursor: pointer; padding: 12px 16px; min-height: 44px; }' in css


def test_watson_json_editor_is_16px_on_phones():
    # Bob team free play #17 (409326d7): the Watson simulation JSON editor inherited 14px on phones.
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert '#gremlins-input { font-size: 16px; }' in css.split('@media (max-width: 640px)')[-1]


def test_watson_mode_selector_says_what_it_controls():
    # Bob team free play #18 (9c339527): "Gremlin" did not say what the choice controls.
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    assert '<label>Comparison mode<select id="gremlins-breed">' in html and '<label>Gremlin<select' not in html


def test_agents_entry_says_runs_not_live_agents():
    # Bob team free play #19 (b996e5f3): the page lists finished runs too, so "Agents" overstated what is running.
    for page in ('index.html', 'dashboard.html'):
        html = (STATIC / page).read_text(encoding='utf-8')
        assert '<button data-view="agents" type="button">Agent runs</button>' in html and '>Agents</button>' not in html, page
    assert '<h2>Registered agent runs</h2>' in (STATIC / 'index.html').read_text(encoding='utf-8')
    assert "content: ' · Agent runs';" in (STATIC / 'styles.css').read_text(encoding='utf-8')
