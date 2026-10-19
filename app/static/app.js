const $ = id => document.getElementById(id);
const SESSION_KEY = 'handoffs-session';
let session = null;
let postPending = false;
if (typeof sessionStorage !== 'undefined') try {
  const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
  if (saved && typeof saved.access_token === 'string' && saved.access_token &&
      typeof saved.user_id === 'string' && saved.user_id) session = saved;
  else sessionStorage.removeItem(SESSION_KEY);
} catch { sessionStorage.removeItem(SESSION_KEY); }
let user = session ? session.user_id : localStorage.getItem('handoffs-user') || 'steve';
// Steve, 2026-10-19: two people at one screen. Each extra person signs in with their own password and decides as
// themselves; nobody can decide for anyone else (docs/HUMAN_GATES.md section 6: the second door stays on).
const COSIGN_KEY = 'ase-cosigners';
let cosigners = [];
if (typeof sessionStorage !== 'undefined') try {
  const saved = JSON.parse(sessionStorage.getItem(COSIGN_KEY) || '[]');
  cosigners = Array.isArray(saved) ? saved.filter(person => person && typeof person.access_token === 'string' && person.access_token &&
    typeof person.user_id === 'string' && person.user_id) : [];
} catch { cosigners = []; }
function saveCosigners() { if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(COSIGN_KEY, JSON.stringify(cosigners)); }
let postDraftOwner = null;
function renderPostDraftOwner(note = '') {
  if (typeof document === 'undefined') return;
  const form = $('post-form');
  if (!form) return;
  let label = $('post-draft-owner');
  if (!label) {
    label = document.createElement('p');
    label.id = 'post-draft-owner';
    label.setAttribute('role', 'status');
    label.setAttribute('aria-live', 'polite');
    form.before(label);
  }
  label.textContent = postDraftOwner ? `Draft owner: ${postDraftOwner.principal} (${postDraftOwner.auth ? 'signed in' : 'demo'}). Not saved across reloads.` : note;
  label.hidden = !label.textContent;
}
function syncPostDraftOwner() {
  if (!postDraftOwner) return false;
  const owner = postDraftOwner;
  if (owner.user === user && owner.auth === session && owner.token === session?.access_token &&
      owner.principal === (session?.user_id || user)) return false;
  postDraftOwner = null;
  if (typeof document !== 'undefined') $('post-form')?.reset();
  const note = 'Draft cleared because the identity or session changed. Nothing was transferred to the new identity.';
  renderPostDraftOwner(note);
  message(note);
  return true;
}
function recordPostDraftOwner() {
  // A changed identity must discard old fields, not adopt them on the next input.
  if (syncPostDraftOwner()) return;
  if (!postDraftOwner) postDraftOwner = {
    user, auth: session, token: session?.access_token, principal: session?.user_id || user
  };
  renderPostDraftOwner();
}
function identityHeaders() {
  return session ? {Authorization: 'Bearer ' + session.access_token} : {'X-Demo-User': user};
}
function renderAuth() {
  $('signin-form').hidden = !!session;
  $('signin-form').style.display = session ? 'none' : 'flex';
  $('signed-in').hidden = !session;
  $('signed-in-label').textContent = session ? 'Signed in as ' + session.user_id : '';
  if (session) {
    user = session.user_id;
    if (![...$('user').options].some(option => option.value === user)) $('user').append(new Option(user, user));
  }
  if (typeof syncPostDraftOwner === 'function') syncPostDraftOwner();
  $('user').value = user;
  $('user').disabled = !!session || (typeof postPending !== 'undefined' && postPending);
  const people = session ? [session.user_id, ...(typeof cosigners !== 'undefined' ? cosigners.map(person => person.user_id) : [])] : [];
  document.title = people.length ? `ASE · ${people.join(' + ')}` : 'ASE · Ask freely. Share freely. Build together.';
  if ($('cosign')) {
    $('cosign').hidden = !session;
    $('cosign-list').textContent = cosigners.length ? 'Also signed in here: ' + cosigners.map(person => person.user_id).join(', ') : '';
  }
  syncSignoffAuth();
}
function clearSession() {
  session = null;
  sessionStorage.removeItem(SESSION_KEY);
  cosigners = []; sessionStorage.removeItem(COSIGN_KEY);  // Signing out clears everyone on this screen.
  renderAuth();
}
async function authenticatedFetch(url, options = {}) {
  const target = new URL(url, location.href);
  if (target.origin !== location.origin) throw new Error('Refusing to send identity to another origin.');
  const token = session?.access_token;
  const response = await fetch(target.href, {...options, redirect: 'error'});
  if (response.status === 401 && token && session?.access_token === token) {
    clearSession();
    ++treeEpoch; ++boardRequest;
    clearTimeout(aiPoll); clearTimeout(proofPoll); clearTimeout(acceptPoll);
    for (const id of ['board', 'post', 'wallet', 'detail', 'gremlins', 'agents', 'signoffs']) $(id).hidden = true;
    message('Session ended. Sign in again or choose a demo user.', true);
    throw new Error('Session ended. Sign in again or choose a demo user.');
  }
  return response;
}
let view = 'open', offset = 0, txOffset = 0, selected = null;
let treeEpoch = 0;
let aiPoll, proofPoll, acceptPoll;
const pageSize = 12;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function message(text, error = false) { $('notice').textContent = text; $('notice').className = error ? 'error' : ''; }
async function run(operation) {
  try { await operation(); } catch (error) { message(error.message, true); }
}
function requestCacheKey(value) {
  // Cache routing only, not an integrity hash. The server checks the full SHA-256.
  let a = 2166136261, b = 2246822519;
  for (let index = 0; index < value.length; index++) {
    a = Math.imul(a ^ value.charCodeAt(index), 16777619);
    b = Math.imul(b ^ value.charCodeAt(index), 3266489917);
  }
  return `handoffs-request:${value.length}:${a >>> 0}:${b >>> 0}`;
}
async function api(path, body) {
  const headers = identityHeaders();
  const options = {headers};
  let operation;
  if (body !== undefined) {
    operation = requestCacheKey(JSON.stringify([user, path, body]));
    let key = sessionStorage.getItem(operation);
    if (!key) { key = Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16)).join('-'); sessionStorage.setItem(operation, key); }
    headers['Idempotency-Key'] = key;
    headers['X-Action-Intent'] = 'user-directed';
    headers['Content-Type'] = 'application/json';
    options.method = 'POST'; options.body = JSON.stringify(body);
  }
  const response = await authenticatedFetch('/api/v1' + path, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
    error.status = response.status;
    error.detail = data.detail;
    throw error;
  }
  if (operation) sessionStorage.removeItem(operation);
  return data;
}
async function stats() {
  const data = await api('/me/stats');
  $('gold').textContent = data.available_gold.toLocaleString();
  $('reserved').textContent = `${data.reserved_gold.toLocaleString()} Gold reserved in tasks`;
  $('stats').replaceChildren();
  for (const [label, value] of [['Available Gold', data.available_gold], ['Reserved Gold', data.reserved_gold],
    ['Monthly grant', data.monthly_gold], ['Active work', data.active_count], ['Completed work', data.completed_count],
    ['Next allocation', new Date(data.next_allocation).toLocaleDateString()]]) {
    const box = element('div', undefined, 'stat'); box.append(element('span', label), element('strong', String(value))); $('stats').append(box);
  }
}
let boardRequest = 0;
async function board() {
  // Only the latest request may publish; a slower earlier response is dropped, errors included.
  const ticket = ++boardRequest;
  const mine = view === 'mine', picker = $('assigned-by');
  if ($('mine-filters')) $('mine-filters').hidden = !mine;
  // My Tasks hides closed work unless asked; the picker narrows to one poster.
  const filters = !mine || !picker ? '' : (($('show-closed').checked ? '' : '&status=open,pending,working,blocked,delivered,awaiting_approval') +
    (picker.value ? '&creator=' + encodeURIComponent(picker.value) : ''));
  const note = $('board-note');
  $('cards').replaceChildren(element('p', 'Loading tasks…'));
  if (note) note.textContent = `${mine ? 'My tasks' : 'Browse'} · loading`;
  $('previous').disabled = true; $('next').disabled = true;
  $('page-label').textContent = `Page ${offset / pageSize + 1}`;
  let result;
  try { result = await api(`/tasks?view=${view}&limit=${pageSize}&offset=${offset}&q=${encodeURIComponent($('search').value)}${filters}`); }
  catch (error) {
    if (ticket !== boardRequest) return;
    const box = element('div', undefined, 'error');
    const retry = element('button', 'Retry'); retry.onclick = () => run(() => board());
    box.append(element('p', 'Could not load tasks. ' + error.message), retry);
    $('cards').replaceChildren(box);
    if (note) note.textContent = `${mine ? 'My tasks' : 'Browse'} · load failed · result count unavailable`;
    return;
  }
  if (ticket !== boardRequest) return;
  if (mine && picker) {
    const chosen = picker.value; picker.replaceChildren(new Option('Anyone', ''));
    for (const name of new Set([...(result.creators || []), ...(chosen ? [chosen] : [])])) picker.append(new Option(name, name));
    picker.value = chosen;
  }
  $('cards').replaceChildren();
  if (!result.items.length) {
    const filtered = !!$('search').value || (mine && (picker?.value || !$('show-closed').checked));
    const box = element('div', undefined, 'empty');
    if (offset > 0) {
      const previous = element('button', 'Previous');
      previous.onclick = () => run(async () => { offset = Math.max(0, offset - pageSize); await board(); });
      box.append(element('p', 'No tasks on this page. Try the previous page.'), previous);
    } else if (filtered) {
      const clear = element('button', 'Clear filters');
      clear.onclick = () => run(async () => {
        $('search').value = ''; offset = 0;
        if (mine) { $('show-closed').checked = false; if (picker) picker.value = ''; }
        await board();
      });
      box.append(element('p', 'No tasks match these filters.'), clear);
    } else box.append(element('p', mine ? 'Tasks you post or volunteer for will appear here.' : 'Nothing open right now. Post a task when you have useful work to share.'));
    $('cards').append(box);
  }
  for (const item of result.items) {
    const card = element('article', undefined, 'card');
    if (item.phase === 'Closed') card.classList.add('closed-card');
    const top = element('div'); top.append(element('span', item.phase || item.status, 'pill'), element('span', item.complexity, 'pill'));
    if (item.funded) top.append(element('span', `${item.gold} GOLD`, 'pill task-gold'));
    const button = element('button', 'View task'); button.onclick = () => run(() => show(item.id));
    card.append(top, element('h3', item.title), element('div', `${item.creator} · ${item.claimant ? 'Claimed by ' + item.claimant : item.target ? 'Offered to ' + item.target + ' · not claimed' : 'Available to claim'} · ${item.disposition || item.status.replaceAll('_', ' ')}${item.funded ? '' : ' · Unfunded'}`, 'meta'), button);
    $('cards').append(card);
  }
  if (mine && note) {
    // Say what the toggle did, so an empty change still reads as working.
    const closed = result.items.filter(item => item.phase === 'Closed').length;
    const who = picker.value ? ` from ${picker.value}` : '';
    note.textContent = !$('show-closed').checked ? `${result.items.length} open shown${who} · closed hidden` :
      closed ? `${result.items.length} shown${who} · ${closed} closed` : `No closed tasks${who} on this page · ${result.items.length} open shown`;
  }
  if (note) {
    if (!mine) note.textContent = `${result.items.length} open shown · closed hidden`;
    note.textContent = `${mine ? 'My tasks' : 'Browse'} · ${note.textContent} · this page${$('search').value ? ' · search: ' + $('search').value : ''}`;
  }
  $('previous').disabled = offset === 0; $('next').disabled = result.items.length < pageSize;
  $('page-label').textContent = `Page ${offset / pageSize + 1}`;
}
async function transactions() {
  // Say what is shown; a failed load must not leave old rows posing as current (same rule as the task lists).
  $('transactions').replaceChildren(element('p', 'Loading transactions…'));
  let rows;
  try { rows = await api(`/me/transactions?limit=${pageSize}&offset=${txOffset}`); }
  catch (error) {
    const retry = element('button', 'Retry'); retry.onclick = () => run(transactions);
    $('transactions').replaceChildren(element('p', 'Could not load transactions: ' + error.message, 'error'), retry);
    return;
  }
  $('transactions').replaceChildren();
  for (const item of rows) {
    const row = element('div', undefined, 'tx'); const label = element('div', item.kind.replaceAll('_', ' '));
    label.append(element('small', `${item.account_kind} · ${new Date(item.created_at).toLocaleString()}`));
    row.append(label, element('strong', `${item.amount > 0 ? '+' : ''}${item.amount} Gold`)); $('transactions').append(row);
  }
  if (!rows.length) $('transactions').append(element('p', txOffset ? 'No transactions on this page. Use Previous to go back.' : 'No transactions yet.'));
  else $('transactions').prepend(element('p', `Page ${txOffset / pageSize + 1} · ${rows.length} transaction${rows.length === 1 ? '' : 's'} shown, newest first`, 'meta'));
  $('tx-previous').disabled = txOffset === 0; $('tx-next').disabled = rows.length < pageSize;
  $('tx-page').textContent = `Page ${txOffset / pageSize + 1}`;
}
async function agentRoster() {
  $('agents-refresh').disabled = true;
  $('agents-summary').textContent = 'Loading registered agents…';
  $('agent-rows').replaceChildren();
  try {
    let data;
    try { data = await api('/agents'); }
    catch (error) { if (view === 'agents') $('agents-summary').textContent = 'Could not load agents: ' + error.message + '. Refresh to retry.'; return; }
    if (view !== 'agents') return;
    const mode = await api('/automation-mode');
    $('agents-mode').textContent = mode.mode ? `Mode: ${mode.mode} · ${mode.summary}` : '';
    $('agents-summary').textContent = !data.available ? 'Agent registry unavailable.' :
      data.items.length ? `${data.items.length} registered runs · refresh to check for changes` : 'No registered Astra runs yet.';
    for (const agent of data.items) {
      const row = element('tr');
      const name = element('td', `Astra ${agent.name || agent.id.slice(0, 8)}`); name.title = agent.id;
      name.append(element('small', `${agent.role} · level ${agent.level}${agent.session ? ' · ' + agent.session : ''}`)); row.append(name);
      row.append(element('td', {active: 'Working?', released: 'Resting', failed: 'Stopped'}[agent.state] || '?'));
      const work = element('td', agent.task_id || agent.task ? undefined : '—');
      if (agent.task_id) {
        const link = element('a', `task ${agent.task_id.slice(0, 8)}`); link.href = '#task=' + encodeURIComponent(agent.task_id);
        link.onclick = event => { event.preventDefault(); run(() => show(agent.task_id)); }; work.append(link);
      }
      if (agent.task) work.append(element('small', agent.task));
      if (agent.directive) work.append(element('small', agent.directive));
      row.append(work);
      row.append(element('td', agent.resting === true ? 'Resting' : agent.resting === false ? '—' : '?'));
      $('agent-rows').append(row);
    }
  } finally { $('agents-refresh').disabled = false; }
}
let digestCountRequest = 0;
let signoffRequest = 0;
let digestBusy = false;
let digestUncertain = false;
let digestEntries = [];
let digestBatchButton = null;
let digestPickers = [];
function applyDigestSearch() {
  // Hidden cards are unselected so a batch never includes something you cannot see.
  const query = (typeof document !== 'undefined' && $('digest-search')?.value || '').trim().toLowerCase();
  for (const node of document.querySelectorAll('#signoff-cards [data-search]')) node.hidden = !!query && !node.dataset.search.includes(query);
  for (const entry of digestEntries) if (entry.choice && entry.card.hidden) entry.choice.checked = false;
  for (const [button, text, chosen] of digestPickers) button.textContent = `${text} (${chosen().length})`;
  syncSignoffAuth();
}
function digestCount(data) {
  if (typeof document === 'undefined') return;
  const entry = $('human-decisions-entry');
  if (!entry) return;
  // Only what a click can complete now (Steve, 2026-10-18: "it's too complicated").
  const total = Number.isInteger(data?.counts?.ready) ? data.counts.ready : data?.counts?.total;
  const known = Number.isInteger(total) && total >= 0;
  // The label span keeps the icon (task 5b86fe29).
  (entry.querySelector('.nav-label') || entry).textContent = known ? `Decisions · ${total}` : 'Decisions · ?';
  entry.setAttribute('aria-label', known ? `Human decisions; ${total} ready for you` : 'Human decisions; waiting count unavailable');
}
async function refreshDigestCount() {
  const ticket = ++digestCountRequest, auth = session, actor = user;
  digestCount(null);
  try {
    const data = await api('/digest');
    if (ticket === digestCountRequest && auth === session && actor === user) digestCount(data);
  } catch {
    if (ticket === digestCountRequest) digestCount(null);
  }
}
function syncSignoffAuth() {
  if (typeof document === 'undefined') return;
  if ($('signoffs-hint')) $('signoffs-hint').hidden = !!session;
  const locked = !session || digestBusy || digestUncertain;
  for (const control of document.querySelectorAll('#signoffs [data-digest-control]')) {
    control.disabled = locked;
  }
  if ($('signoffs-refresh')) $('signoffs-refresh').disabled = digestBusy;
  if (digestBatchButton) {
    const count = digestEntries.filter(entry => entry.choice?.checked).length;
    digestBatchButton.textContent = `Accept selected (${count})`;
    digestBatchButton.disabled = locked || !count;
  }
}
function digestReference(item) {
  return {kind: item.kind, id: item.id, revision: item.revision,
    recommendation_id: item.recommendation?.status === 'unavailable' ? null : item.recommendation?.id || null};
}
function digestEligible(item) {
  // Eligibility here is transport validity, never proof or inferred acceptance.
  return ['signoff', 'intake_veto', 'human_close', 'rule_texts'].includes(item.kind) &&
    typeof item.id === 'string' && !!item.id &&
    typeof item.revision === 'string' && item.revision.length === 64;
}
function digestNote(labelText) {
  const label = element('label', labelText), note = element('textarea');
  note.maxLength = 2000;
  note.dataset.digestControl = 'true';
  note.style.width = '100%'; note.style.boxSizing = 'border-box';
  label.append(note);
  return {label, note};
}
async function personFetch(person, path, body) {
  // A cosigner's own token; same origin only, like authenticatedFetch.
  const headers = {Authorization: 'Bearer ' + person.access_token};
  if (body !== undefined) Object.assign(headers, {'Content-Type': 'application/json', 'X-Action-Intent': 'user-directed',
    'Idempotency-Key': Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16)).join('-')});
  const response = await fetch('/api/v1' + path, {method: body === undefined ? 'GET' : 'POST', redirect: 'error', headers,
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (response.status === 401) { cosigners = cosigners.filter(other => other !== person); saveCosigners(); renderAuth(); }
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
    error.status = response.status; error.detail = data.detail;
    throw error;
  }
  return data;
}
async function submitDigest(path, body, auth, actor, person = null) {
  if (!session || session !== auth || user !== actor || digestBusy || digestUncertain) return;
  if (person && !cosigners.includes(person)) return;
  digestBusy = true; syncSignoffAuth();
  const outcomes = $('digest-outcomes');
  outcomes.replaceChildren(element('p', 'Recording decision…'));
  let confirmed = false;
  try {
    const result = person ? await personFetch(person, path, body) : await api(path, body);
    confirmed = true;
    outcomes.replaceChildren();
    if (path === '/digest/decide-batch') {
      outcomes.append(element('p', `${result.decided} recorded · ${result.failed} failed`));
      for (const row of result.results || []) {
        const entry = digestEntries.find(entry => entry.item.kind === row.kind && entry.item.id === row.id);
        const label = entry?.item.title || row.id;
        const detail = row.ok ? 'Accepted' : row.status === 409 ? 'Changed since you looked; refresh' :
          `Not recorded: ${typeof row.detail === 'string' ? row.detail : JSON.stringify(row.detail)}`;
        outcomes.append(element('p', `${row.kind} · ${label}: ${detail}`, row.ok ? 'meta' : 'error'));
      }
    } else outcomes.append(element('p', typeof result?.message === 'string' ? result.message : 'Decision recorded.'));
    // Refresh reads only; never retry a write or automatically select failed items.
    try { await signoffs(); }
    catch (error) {
      digestUncertain = true;
      outcomes.append(element('p', `Decision recorded; refresh failed (${error.message}). Do not submit it again. Refresh to review current items.`, 'error'));
    }
  } catch (error) {
    if (error.status === 409) {
      outcomes.replaceChildren(element('p', 'Changed since you looked; refresh', 'error'));
      try { await signoffs(); }
      catch (refreshError) {
        digestUncertain = true;
        outcomes.append(element('p', 'Refresh failed: ' + refreshError.message, 'error'));
      }
    } else {
      // A missing response or server error does not prove the write failed.
      const unknown = !error.status || error.status >= 500;
      digestUncertain = unknown;
      outcomes.replaceChildren(element('p', unknown ?
        'Outcome unknown. No automatic retry. Refresh and reconcile before deciding again.' :
        'Decision not recorded: ' + error.message, 'error'));
    }
  } finally {
    digestBusy = false;
    syncSignoffAuth();
    // Includes error paths; the count must never remain an old success value.
    await refreshDigestCount();
  }
}
function renderSignoffs(items) {
  // Steve, 2026-10-18: Accept / Decline / Change reads clearer than Yes / No / Change; the API values stay yes/no/change.
  const DIGEST_CHOICES = [['Accept', 'yes'], ['Decline', 'no'], ['Change', 'change']];
  const DIGEST_MEANING = {
    signoff: 'Accept approves this request (nothing runs yet). Decline rejects it. Change asks for a revision and keeps it waiting.',
    intake_veto: "Accept lets this task go ahead despite the screen's objection. Decline keeps it blocked. Change asks for a revised task.",
    human_close: 'Accept accepts the proof and completes the task. Decline rejects the proof; the task stays open. Change asks for more work.',
    rule_texts: 'Accept records your own approval of these exact texts; they apply when a second person accepts too. Decline blocks them. Change asks for a revised proposal.'};
  const list = $('signoff-cards'); list.replaceChildren();
  digestEntries = []; digestBatchButton = null; digestPickers = [];
  const auth = session, actor = user;
  const waiting = items.filter(item => item.ready === false);
  items = items.filter(item => item.ready !== false);
  if (!items.length) list.append(element('p', 'Nothing needs you right now.'));
  for (const item of items) {
    const card = element('article', undefined, 'card');
    card.style.minWidth = '0'; card.style.overflowWrap = 'anywhere';
    const effect = item.effect || {};
    const reversibility = String(effect.reversibility || '').toLowerCase();
    const tag = reversibility === 'reversible' ? 'Reversible' : reversibility === 'irreversible' ? 'Irreversible' : 'Reversibility unknown';
    card.append(element('h3', `${item.action || 'Decision'} — ${item.title || item.id}`),
      element('span', item.kind, 'pill'),
      element('span', `${tag} · ${effect.gate || 'Gate unspecified'}`, 'pill'),
      element('p', effect.reason || 'Consequence details unavailable.', 'meta'),
      element('p', item.why_waiting));
    if (item.kind === 'rule_texts' && Array.isArray(item.details?.changed)) {
      // Task 2c56ad7a: the people deciding read every changed text, old and new.
      const texts = element('details');
      texts.append(element('summary', `${item.details.changed.length} rule texts change · digest ${String(item.revision).slice(0, 12)}…`));
      for (const change of item.details.changed) {
        const old = element('p', 'Old: ' + change.old, 'meta'), next = element('p', 'New: ' + change.new);
        old.style.whiteSpace = next.style.whiteSpace = 'pre-wrap';
        texts.append(element('h4', change.name), old, next);
      }
      card.append(texts);
    }
    const recommendation = item.recommendation;
    const advised = DIGEST_CHOICES.find(([, decision]) => decision === recommendation?.disposition)?.[0] || recommendation?.disposition;
    card.append(element('p', !recommendation || recommendation.status === 'unavailable' ? 'No recommendation yet' :
      `Recommended: ${advised} · ${recommendation.rationale}`));
    const provenance = item.provenance || {};
    card.append(element('small', `Requested by ${provenance.requested_by || 'unknown'} · ${provenance.requested_principal || 'unknown'}${provenance.construction ? ' · Construction: ' + String(provenance.construction) : ''}`));
    card.dataset.search = [item.title, item.id, item.kind, item.why_waiting, item.action].join(' ').toLowerCase();
    const entry = {item, choice: null, card}; digestEntries.push(entry);
    if (digestEligible(item)) {
      if (item.kind !== 'rule_texts') {  // Rule texts are always decided one at a time.
        const selectLabel = element('label', 'Include in Accept selected');
        const choice = element('input'); choice.type = 'checkbox'; choice.checked = false;
        choice.dataset.digestControl = 'true'; choice.style.width = 'auto';
        choice.onchange = syncSignoffAuth;
        selectLabel.prepend(choice); card.append(selectLabel); entry.choice = choice;
      }
      const {label, note} = digestNote('Note (needed for Decline or Change)');
      const controls = element('div', undefined, 'actions');
      controls.style.display = 'flex'; controls.style.flexWrap = 'wrap'; controls.style.gap = '8px';
      // Who on this screen can still decide this item: the signed-in person and/or a cosigner, each as themselves.
      const deciders = Array.isArray(item.deciders) && item.deciders.length ? item.deciders : [null];
      for (const [text, decision] of DIGEST_CHOICES) {
        const people = decision === 'yes' ? deciders : [deciders.includes(null) ? null : deciders[0]];
        for (const person of people) {
          const name = person ? person.user_id : session?.user_id || user;
          // Always name who a click acts as (2026-10-19: Steve clicked in Nate's session without noticing).
          const button = element('button', session || person ? `${text} as ${name}` : text); button.type = 'button';
          button.dataset.digestControl = 'true'; button.dataset.decision = decision;
          button.onclick = () => run(async () => {
            if (!session || session !== auth || actor !== user || digestBusy || digestUncertain) return;
            if (decision !== 'yes' && !note.value.trim()) { note.required = true; note.reportValidity(); note.focus(); note.required = false; return; }
            await submitDigest('/digest/decide', {...digestReference(item), decision, note: note.value.trim() || 'Accepted'}, auth, actor, person);
          });
          controls.append(button);
        }
      }
      card.append(element('p', DIGEST_MEANING[item.kind] || '', 'meta'), label, controls);
    } else card.append(element('p', 'Decision unavailable: missing or unsupported item version.', 'error'));
    if (!session) card.append(element('p', 'Sign in to decide', 'meta'));
    list.append(card);
  }
  if (waiting.length) {
    // One folded line for everything a click cannot complete yet, each with what it waits on.
    const fold = element('details', undefined, 'card');
    fold.append(element('summary', `${waiting.length} waiting on others`));
    for (const item of waiting) {
      const line = element('p', `${item.title || item.id} — ${item.waiting_on || 'not ready'}`, 'meta');
      line.dataset.search = [item.title, item.id, item.kind, item.waiting_on].join(' ').toLowerCase();
      fold.append(line);
    }
    list.append(fold);
  }
  if (digestEntries.some(entry => entry.choice)) {
    const bar = element('div', undefined, 'card');
    const {label, note} = digestNote('Note for selected decisions (optional)');
    digestBatchButton = element('button', 'Accept selected (0)', 'primary');
    digestBatchButton.type = 'button'; digestBatchButton.dataset.digestControl = 'true';
    digestBatchButton.onclick = () => run(async () => {
      if (!session || session !== auth || actor !== user || digestBusy || digestUncertain) return;
      const selected = digestEntries.filter(entry => entry.choice?.checked);
      if (!selected.length) return;
      if (selected.length > 50) { message('Select at most 50 items for one batch.', true); return; }
      await submitDigest('/digest/decide-batch', {items: selected.map(entry => digestReference(entry.item)), note: note.value.trim() || 'Accepted'}, auth, actor);
    });
    // Steve, 2026-10-18: "add accept all, it's a lot". Selecting stays explicit; Accept selected still needs a note.
    // Selection follows the search box: only cards that are showing can be selected.
    const shown = () => digestEntries.filter(entry => entry.choice && !entry.card.hidden);
    const advised = () => shown().filter(entry => entry.item.recommendation?.disposition === 'yes');
    const pick = element('div', undefined, 'actions');
    pick.style.display = 'flex'; pick.style.flexWrap = 'wrap'; pick.style.gap = '8px';
    digestPickers = [];
    for (const [text, chosen] of [['Select recommended', advised], ['Select all', shown], ['Clear', () => []]]) {
      const button = element('button', text); button.type = 'button'; button.dataset.digestControl = 'true';
      button.onclick = () => { const picked = chosen(); for (const entry of digestEntries) if (entry.choice) entry.choice.checked = picked.includes(entry); syncSignoffAuth(); };
      if (text !== 'Clear') digestPickers.push([button, text, chosen]);
      pick.append(button);
    }
    bar.append(pick, label, digestBatchButton); list.prepend(bar);
  }
  if ($('digest-search')) { $('digest-search').oninput = applyDigestSearch; applyDigestSearch(); }
  else syncSignoffAuth();
}
function coverageGaps(coverage) {
  if (typeof coverage === 'string') return ` · ${coverage}`;
  const gaps = Object.entries(coverage || {}).filter(([, state]) => state !== 'complete').map(([kind, state]) => `${kind.replace(/_/g, ' ')}s ${state}`);
  return gaps.length ? ` · ${gaps.join(', ')}` : '';
}
async function signoffs() {
  const ticket = ++signoffRequest, countTicket = ++digestCountRequest;
  const epoch = treeEpoch, auth = session, actor = user;
  digestCount(null);
  $('signoff-cards').replaceChildren(element('p', 'Loading decisions…'));
  digestEntries = []; digestBatchButton = null; digestPickers = [];
  syncSignoffAuth();
  let data;
  try { data = await api('/digest'); }
  catch (error) {
    if (ticket === signoffRequest && epoch === treeEpoch && auth === session && actor === user) {
      $('signoff-cards').replaceChildren(element('p', 'Could not load decisions. Refresh to retry.', 'error'));
      $('human-decisions-scope').textContent = 'Waiting count unavailable.';
    }
    throw error;
  }
  if (ticket !== signoffRequest || epoch !== treeEpoch || auth !== session || actor !== user || view !== 'signoffs') return;
  if (countTicket === digestCountRequest) digestCount(data);
  // Rule texts need two different people: a cosigner on this screen gets their own Accept on the cards still waiting on them.
  const merged = new Map(data.items.map(item => [`${item.kind}:${item.id}`, {...item, deciders: [null]}]));
  for (const person of (typeof cosigners !== 'undefined' ? [...cosigners] : [])) {
    let theirs;
    try { theirs = await personFetch(person, '/digest'); } catch { continue; }
    for (const item of theirs.items.filter(item => item.kind === 'rule_texts')) {
      const key = `${item.kind}:${item.id}`;
      if (merged.has(key)) merged.get(key).deciders.push(person); else merged.set(key, {...item, deciders: [person]});
    }
  }
  if (ticket !== signoffRequest || epoch !== treeEpoch || auth !== session || actor !== user || view !== 'signoffs') return;
  const items = [...merged.values()], ready = items.filter(item => item.ready !== false).length;
  $('human-decisions-scope').textContent = `${ready} ready for you · ${items.length - ready} waiting on others`;
  // An unknown write remains locked even after a read: reconcile its audit first.
  renderSignoffs(items);
}
const TASK_VIEWS = new Set(['open', 'mine', 'post']), WORKSPACE_BUTTONS = 'nav[aria-label="Workspace"] button[data-view]';
async function navigate(nextView) {
  if (typeof syncPostDraftOwner === 'function') syncPostDraftOwner();
  const epoch = typeof treeEpoch !== 'undefined' ? ++treeEpoch : null;
  clearTimeout(aiPoll);
  clearTimeout(proofPoll);
  view = nextView; selected = null;
  if (typeof refreshDigestCount === 'function' && typeof session !== 'undefined' && nextView !== 'signoffs') void refreshDigestCount();
  if (typeof boardRequest !== 'undefined') boardRequest++;
  if (typeof window !== 'undefined' && window.commonsNavigation) window.commonsNavigation.update(view, user);
  else {
    if ($('dashboard-link')) $('dashboard-link').href = '/dashboard?user=' + encodeURIComponent(user);
    history.replaceState(null, '', location.pathname + location.search + (view === 'agents' ? '#agents' : ''));
  }
  for (const id of ['board', 'post', 'wallet', 'detail', 'gremlins', 'agents', 'signoffs']) $(id).hidden = true;
  // One Tasks entry covers browse, my work and posting; the local row says which one is current.
  for (const button of document.querySelectorAll(WORKSPACE_BUTTONS)) button.classList.toggle('selected', button.dataset.view === (TASK_VIEWS.has(view) ? 'open' : view));
  if ($('tasks-toolbar')) $('tasks-toolbar').hidden = !TASK_VIEWS.has(view);
  for (const button of document.querySelectorAll('[data-task-view]')) button.dataset.taskView === view ? button.setAttribute('aria-current', 'page') : button.removeAttribute('aria-current');
  await stats();
  if (epoch !== null && epoch !== treeEpoch) return;
  if (view === 'post') $('post').hidden = false;
  else if (view === 'gremlins') $('gremlins').hidden = false;
  else if (view === 'agents') { $('agents').hidden = false; await agentRoster(); }
  else if (view === 'signoffs') { $('signoffs').hidden = false; await signoffs(); }
  else if (view === 'wallet') { $('wallet').hidden = false; await transactions(); }
  else { $('board').hidden = false; $('board-title').textContent = view === 'mine' ? 'My tasks' : 'Open tasks'; await board(); }
}
async function mutate(path, body = {}, created = '') {
  $('user').disabled = true;
  for (const button of document.querySelectorAll('button:not(:disabled)')) { button.dataset.busy = 'true'; button.disabled = true; }
  try {
    const result = await api(path, body);
    message(result.status === 'settled' ? 'Verified completion recorded. Reserved demo Gold was paid.' : created ? `${created} ${result.id}.` : 'Saved.');
    try {
      await stats();
      await show(result.id);
    } catch (error) {
      // The write is confirmed; a failed follow-up read must not look like a failed post (a retry would duplicate it).
      if (!created) throw error;
      message(`${created} ${result.id}. Refreshing the page failed (${error.message}); do not post it again.`, true);
    }
    return result;
  } finally {
    if (typeof renderAuth === 'function') renderAuth(); else $('user').disabled = false;
    for (const button of document.querySelectorAll('button[data-busy]')) { button.disabled = false; delete button.dataset.busy; }
  }
}
const acceptStages = {
  queued: ['Accepted · queued for AI preparation', 'working'],
  running: ['Accepted · AI is preparing', 'working'],
  needs_input: ['AI has questions for you', 'attention'],
  followups_pending: ['Child proposals await your approval', 'attention'],
  ready: ['Preparation ready · not verified', 'done'],
  completed: ['Preparation complete', 'done'],
  failed: ['AI preparation failed · retry from the task', 'error'],
};
function acceptNotice(id, title, text, state) {
  // One top-right notice, replaced in place as the accepted task moves through AI preparation.
  let box = $('accept-notice');
  if (!box) { box = element('aside'); box.id = 'accept-notice'; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite'); document.body.append(box); }
  const link = element('a', title); link.href = '#task=' + encodeURIComponent(id);
  link.onclick = e => { e.preventDefault(); run(() => show(id)); };
  const close = element('button', '×', 'notice-close'); close.setAttribute('aria-label', 'Dismiss notification');
  close.onclick = () => { clearTimeout(acceptPoll); box.remove(); };
  box.className = state; box.replaceChildren(close, element('strong', text), link);
}
async function trackAccept(id, title) {
  clearTimeout(acceptPoll);
  const status = (await api('/tasks/' + encodeURIComponent(id))).ai_run?.status;
  const [text, state] = acceptStages[status] || ['Accepted', 'done'];
  acceptNotice(id, title, text, state);
  if (['queued', 'running'].includes(status)) acceptPoll = setTimeout(() => run(() => trackAccept(id, title)), 2000);
}
async function accept(data, button) {
  clearTimeout(acceptPoll);
  button.textContent = 'Accepting…'; button.classList.add('loading'); button.setAttribute('aria-busy', 'true');
  acceptNotice(data.id, data.title, 'Accepting · assigning you and starting AI preparation', 'working');
  try {
    await mutate(`/tasks/${data.id}/accept`, {model: data.ai_options.recommended});
  } catch (error) {
    button.textContent = 'Accept'; button.classList.remove('loading'); button.removeAttribute('aria-busy');
    acceptNotice(data.id, data.title, 'Not accepted · ' + error.message, 'error');
    throw error;
  }
  await trackAccept(data.id, data.title);
}
function checkpointSection(data) {
  const section = element('section', undefined, 'evidence');
  const link = (label, id) => {
    const anchor = element('a', label);
    anchor.href = '#task=' + encodeURIComponent(id);
    anchor.onclick = event => { event.preventDefault(); run(() => show(id)); };
    return anchor;
  };
  if (data.continuation_id) {
    section.append(element('h3', 'Progress saved'),
      element('p', 'This task was closed into a continuation. It was not marked complete.'),
      link('Open continuation', data.continuation_id));
  }
  if (data.checkpoint) {
    section.append(element('h3', 'Saved progress'), element('pre', data.checkpoint.notes, 'content'),
      link('Previous task and evidence', data.checkpoint.previous_task_id));
  }
  if (['open', 'working', 'blocked', 'decomposed', 'awaiting_approval', 'delivered'].includes(data.status)
      && [data.creator, data.claimant].includes(user)) {
    const button = element('button', 'Save checkpoint');
    button.type = 'button';
    button.onclick = () => {
      if (section.querySelector('form')) return;
      const form = element('form');
      const label = element('label', 'Progress, remaining work, evidence and next action');
      const notes = element('textarea'); notes.required = true; notes.maxLength = 30000;
      notes.placeholder = 'Done:\nRemaining:\nEvidence / commits:\nBlockers:\nNext action:';
      label.append(notes);
      const cancel = element('button', 'Keep working'); cancel.type = 'button'; cancel.onclick = () => form.remove();
      form.append(label, element('p', 'Closes this task and opens a linked task with the same scope. Work stays unaccepted and Gold stays reserved.'),
        element('button', 'Save and open continuation', 'primary'), cancel);
      form.onsubmit = event => {
        event.preventDefault();
        run(async () => {
          await mutate(`/tasks/${data.id}/checkpoint`, {notes: notes.value});
          message('Checkpoint saved. The continuation is open for later.');
        });
      };
      section.append(form); notes.focus();
    };
    section.append(button);
  }
  return section;
}

function intakeSection(data, detail) {
  // The independent intake screen's latest verdict, and a human-only override for a veto (task acbeeff0).
  const screens = (data.events || []).filter(e => e.kind === 'intake_screened');
  if (!screens.length) return;
  const last = screens[screens.length - 1].data || {};
  const overridden = (data.events || []).some(e => e.kind === 'intake_overridden' && e.data && e.data.text_sha256 === last.text_sha256);
  if (last.verdict === 'pass' && !overridden) return;
  const box = element('section', undefined, 'intake-box');
  box.append(element('h3', 'Intake screen'), element('p', `${overridden ? 'Veto overridden by a person' : 'Verdict: ' + last.verdict} (${last.mode || 'observe'} mode) · ${last.reason || 'no reason recorded'}`, 'content'));
  if (!overridden && ['veto', 'unavailable'].includes(last.verdict)) {
    const signedIn = typeof session !== 'undefined' && session;
    if (!signedIn) box.append(element('p', 'Only a signed-in person can override this veto. Sign in to decide.', 'meta'));
    else {
      const form = element('form'); const note = labeled(form, 'Why this is right (recorded with your name)', '', 'textarea'); note.required = true;
      form.append(element('button', `Override veto as ${session.user_id}`));
      form.onsubmit = event => { event.preventDefault(); run(() => mutate(`/tasks/${data.id}/intake-override`, {note: note.value})); };
      box.append(form);
    }
  }
  detail.append(box);
}
async function show(id) {
  // Late work from a page the user already left must not change history, sections or focus.
  const epoch = typeof treeEpoch !== 'undefined' ? ++treeEpoch : null, stale = () => epoch !== null && epoch !== treeEpoch;
  clearTimeout(aiPoll);
  clearTimeout(proofPoll);
  const data = await api('/tasks/' + encodeURIComponent(id));
  if (stale()) return;
  selected = id;
  for (const button of $('tasks-toolbar')?.querySelectorAll?.('[data-task-view]') || []) button.removeAttribute('aria-current');
  if (typeof window !== 'undefined' && window.commonsNavigation) window.commonsNavigation.update(view, user, id);
  else {
    if ($('dashboard-link')) $('dashboard-link').href = '/dashboard?user=' + encodeURIComponent(user) + '&task=' + encodeURIComponent(id);
    history.replaceState(null, '', '#task=' + encodeURIComponent(id));
  }
  for (const section of ['board', 'post', 'wallet', 'gremlins', 'agents']) $(section).hidden = true;
  const current = $('detail');
  $('signoffs').hidden = true;
  const refreshing = !current.hidden && current.querySelector('.detail-head code')?.textContent === id;
  const detail = element('div');
  const listView = typeof view !== 'undefined' && view === 'mine' ? 'mine' : 'open';
  const back = element('button', listView === 'mine' ? '← Back to my tasks' : '← Back to tasks'); back.onclick = () => run(() => navigate(listView));
  const dashboard = element('a', 'Open dashboard for this task');
  dashboard.href = '/dashboard?user=' + encodeURIComponent(user) + '&task=' + encodeURIComponent(id);
  const header = element('div', undefined, 'detail-head'); header.append(element('span', data.phase, 'pill'), element('span', data.complexity, 'pill'), element('span', `Target: ${data.profile?.validation_scope || 'Unclassified'}`, 'pill'));
  if (data.funded) header.append(element('span', `${data.gold} GOLD`, 'pill task-gold'));
  header.append(element('h2', data.title), element('code', data.id));
  detail.append(back, dashboard, header, element('h3', 'Goal'), element('p', data.goal, 'content'), element('h3', 'Completion criteria'));
  const rail = element('ol', undefined, 'phase-rail'); rail.setAttribute('aria-label', 'Task lifecycle');
  for (const phase of ['Posted', 'Claimed', 'Closed']) { const item = element('li', phase); if (phase === data.phase) item.setAttribute('aria-current', 'step'); rail.append(item); }
  header.append(rail, element('small', `${data.disposition || data.status.replaceAll('_', ' ')} · Target is declared, not evidence of execution.`));
  const criteria = element('ul'); data.criteria.forEach(text => criteria.append(element('li', text))); detail.append(criteria);
  if (data.repository) detail.append(element('p', 'Repository: ' + data.repository, 'content'));
  data.context_links.forEach(text => detail.append(element('p', text, 'content')));
  await workflowSection(data, detail);
  if (stale()) return;
  proofSection(data, detail);
  intakeSection(data, detail);
  await artifactsSection(data, detail);
  if (stale()) return;
  detail.append(element('p', `Requester: ${data.creator} · ${data.claimant ? 'Worker: ' + data.claimant : data.target ? 'Offered to ' + data.target + ' · not claimed' : 'Available to claim'} · ${data.funded ? 'Reserved demo Gold is released only on verified completion.' : 'Unfunded record. No new funding was created.'}`));
  const actions = element('div', undefined, 'actions');
  const treeLink = element('a', 'Tree');
  treeLink.href = '#tree=' + encodeURIComponent(id);
  actions.append(treeLink);
  if (data.creator === user && data.status === 'open' && !data.claimant) {
    const edit = element('button', 'Edit');
    edit.onclick = () => run(async () => {
      if (current.querySelector('[data-task-editor]')) return;
      clearTimeout(aiPoll); clearTimeout(proofPoll);
      const form = taskEditor(data); actions.after(form); form.querySelector('input').focus();
    });
    actions.append(edit);
  }
  const action = (label, suffix) => { const b = element('button', label); b.onclick = () => run(() => mutate(`/tasks/${id}/${suffix}`)); actions.append(b); };
  if ((data.funded || data.parent_id) && data.status === 'open') {
    if (user === data.creator) action(data.funded ? 'Cancel & refund' : 'Cancel', 'cancel');
    if (!data.target || data.target === user) {
      if (!data.ai_run && (!data.legacy || data.events.some(event => event.kind === 'reopened'))) {
        const button = element('button', 'Accept', 'primary');
        button.onclick = () => run(() => accept(data, button));
        actions.append(button);
      }
      action('Volunteer manually', 'take');
    }
  }
  if (!data.ai_run && ['completed', 'settled'].includes(data.status)
      && [data.creator, data.target, data.claimant, data.completed_by].includes(user)) {
    const reopen = element('button', 'Reopen as HIGH for decomposition');
    reopen.onclick = () => run(() => mutate(`/tasks/${id}/reopen`, {complexity: 'HIGH',
      note: 'Reopened for bounded child-task proposals. Prior completion and evidence preserved; no new acceptance or rewards.'}));
    actions.append(reopen);
  }
  detail.append(actions);
  detail.append(checkpointSection(data));
  await aiSection(data, detail);
  if (data.funded && !data.ai_run && data.claimant === user && ['working', 'blocked'].includes(data.status)) {
    const progress = element('form');
    const noteLabel = element('label', 'Progress note'); const note = element('textarea'); noteLabel.append(note);
    const progressButton = element('button', data.status === 'blocked' ? 'Resume work' : 'Mark blocked');
    progress.append(noteLabel, progressButton);
    progress.onsubmit = e => { e.preventDefault(); run(() => mutate(`/tasks/${id}/status`, {status: data.status === 'blocked' ? 'working' : 'blocked', note: note.value})); };
    detail.append(progress, element('h3', 'Deliver your PR'));
    const form = element('form'); const urlLabel = element('label', 'PR URL'); const url = element('input'); url.type = 'url'; url.required = true; url.placeholder = 'https://github.com/owner/repo/pull/123'; urlLabel.append(url);
    const evidenceLabel = element('label', 'Completion evidence'); const evidence = element('textarea'); evidence.required = true; evidenceLabel.append(evidence);
    form.append(urlLabel, evidenceLabel, element('p', 'PR delivery cannot bypass the proof gate above.'), element('button', 'Submit PR with verified proof', 'primary'));
    form.onsubmit = e => { e.preventDefault(); run(() => mutate(`/tasks/${id}/deliveries`, {pr_url: url.value, evidence: evidence.value})); };
    detail.append(form);
  }
  for (const delivery of data.deliveries) {
    const box = element('div', undefined, 'evidence');
    box.append(element('h3', 'Delivered PR'), element('p', delivery.pr_url, 'content'), element('p', delivery.evidence, 'content'), element('small', delivery.simulated ? 'Verification: simulated' : 'Verification: recorded'));
    detail.append(box);
  }
  if (data.funded && data.creator === user && data.deliveries.length) {
    const review = element('form'); const label = element('label', 'Review note'); const note = element('textarea'); note.required = true; label.append(note);
    const choice = element('select'); ['acknowledged', 'accepted', 'rejected'].forEach(value => { const o = element('option', value); o.value = value; choice.append(o); });
    review.append(element('h3', 'Record your review'), label, choice, element('button', 'Save review'));
    review.onsubmit = e => { e.preventDefault(); run(() => mutate(`/tasks/${id}/reviews`, {decision: choice.value, note: note.value})); };
    detail.append(review);
  }
  if (data.legacy) {
    detail.append(element('h3', 'Legacy context'), element('p', `Source revision: ${data.legacy.revision}`, 'content'));
    for (const document of data.legacy.documents) {
      detail.append(element('h3', document.path), element('p', document.content, 'content'));
    }
  }
  if (window.renderHistory) detail.append(window.renderHistory(data.events, {element, link: id => '#task=' + encodeURIComponent(id)}));
  else for (const event of data.events) {
    const row = element('div', undefined, 'event'); row.append(element('span', `${event.actor} · ${event.kind}${event.data.note ? ' · ' + event.data.note : ''}`), element('span', new Date(event.created_at).toLocaleString())); detail.append(row);
  }
  const x = window.scrollX, y = window.scrollY;
  const panel = current.querySelector('.ai-panel')?.getBoundingClientRect();
  const anchor = panel && panel.bottom > 0 && panel.top < window.innerHeight ? panel.top : null;
  if (refreshing) {
    const expanded = new Map([...current.querySelectorAll('details')].map(node => [node.querySelector('summary').textContent, node.open]));
    for (const node of detail.querySelectorAll('details')) {
      const summary = node.querySelector('summary').textContent;
      if (expanded.has(summary)) node.open = expanded.get(summary);
    }
  }
  current.replaceChildren(...detail.childNodes);
  current.hidden = false;
  if (refreshing) {
    const nextPanel = current.querySelector('.ai-panel')?.getBoundingClientRect();
    window.scrollTo(x, y + (anchor !== null && nextPanel ? nextPanel.top - anchor : 0));
  }
}
// Read-only tree assembly. Artifact entries are files, not package records.
function evidencePackageCount(inventory) {
  if (!inventory || !Array.isArray(inventory.items)) return null;
  const packages = new Set();
  for (const item of inventory.items) {
    const match = typeof item?.path === 'string' && /^packages\/([^/]+)\//.exec(item.path);
    if (match) packages.add(match[1]);
  }
  return packages.size;
}
function assembleTicketTree(input, currentId) {
  const warnings = [], byId = new Map();
  for (const item of Array.isArray(input?.items) ? input.items : []) {
    if (!item || item.id === undefined || item.id === null || item.id === '') {
      warnings.push('Missing node ID in lineage.'); continue;
    }
    const id = String(item.id);
    if (byId.has(id)) { warnings.push('Duplicate node: ' + id); continue; }
    byId.set(id, {...item, id, parent_id: item.parent_id == null ? null : String(item.parent_id)});
  }
  const rootId = input?.root_id == null ? null : String(input.root_id);
  if (!rootId || !byId.has(rootId)) warnings.push('Missing root node: ' + (rootId || 'not supplied'));
  if (!byId.has(String(currentId))) warnings.push('Missing requested node: ' + currentId);
  for (const item of byId.values()) {
    if (item.parent_id && !byId.has(item.parent_id)) warnings.push('Missing parent node: ' + item.parent_id + ' (child ' + item.id + ')');
  }
  // Follow parent chains iteratively; do not recurse over untrusted lineage.
  const finished = new Set();
  for (const id of byId.keys()) {
    const path = new Set();
    let cursor = id;
    while (byId.has(cursor) && !finished.has(cursor)) {
      if (path.has(cursor)) { warnings.push('Cycle detected at node: ' + cursor); break; }
      path.add(cursor);
      cursor = byId.get(cursor).parent_id;
    }
    for (const seen of path) finished.add(seen);
  }
  return {lineage: {root_id: rootId, items: [...byId.values()]}, warnings};
}
function ticketHash(hash) {
  const params = new URLSearchParams(hash.slice(1));
  const tree = params.get('tree');
  if (tree) return {kind: 'tree', id: tree};
  const task = params.get('task') || params.get('opp') || params.get('bounty');
  return task ? {kind: 'task', id: task} : null;
}
async function openTicketHash(route) {
  if (!route) return;
  if (route.kind === 'tree') await showTree(route.id);
  else await show(route.id);
}
async function showTree(id) {
  const epoch = ++treeEpoch;
  clearTimeout(aiPoll); clearTimeout(proofPoll);
  selected = null;
  history.replaceState(null, '', '#tree=' + encodeURIComponent(id));
  for (const section of ['board', 'post', 'wallet', 'gremlins', 'agents']) $(section).hidden = true;
  const current = $('detail');
  current.hidden = false;
  $('signoffs').hidden = true;
  current.replaceChildren(element('h2', 'Task tree'), element('p', 'Loading hierarchy…'));
  try {
    const assembly = assembleTicketTree(await api('/tasks/' + encodeURIComponent(id) + '/lineage'), id);
    const detailsById = Object.create(null);
    const warnings = [...assembly.warnings];
    // Sequential, bounded request load: no retries and no write bodies.
    for (const item of assembly.lineage.items) {
      if (epoch !== treeEpoch) return;
      const path = '/tasks/' + encodeURIComponent(item.id);
      let detail = {};
      try { detail = await api(path); }
      catch (error) { warnings.push('Task details unavailable for ' + item.id + ': ' + error.message); }
      if (epoch !== treeEpoch) return;
      let packageCount = null;
      try {
        packageCount = evidencePackageCount(await api(path + '/artifacts'));
        if (packageCount === null) warnings.push('Invalid artifact inventory for ' + item.id);
      } catch (error) { warnings.push('Evidence packages unavailable for ' + item.id + ': ' + error.message); }
      detailsById[item.id] = {...detail, evidencePackageCount: packageCount};
    }
    if (epoch !== treeEpoch) return;
    const page = element('div');
    const back = element('button', '← Back to board'); back.onclick = () => run(() => navigate('open'));
    const task = element('a', 'Open requested task'); task.href = '#task=' + encodeURIComponent(id);
    page.append(back, task, element('h2', 'Task tree'),
      element('p', 'Read only · attached evidence packages are not verified completion. Unknown counts are not zero.'));
    for (const warning of warnings) page.append(element('p', warning, 'error'));
    if (typeof window.renderTicketFlow !== 'function') page.append(element('p', 'Tree renderer unavailable.', 'error'));
    else page.append(window.renderTicketFlow({lineage: assembly.lineage, currentId: id, detailsById, taskLinks: true}));
    current.replaceChildren(...page.childNodes);
  } catch (error) {
    if (epoch === treeEpoch) current.replaceChildren(element('h2', 'Task tree'), element('p', 'Hierarchy unavailable: ' + error.message, 'error'));
  }
}

async function encodeSourceZip(file) {
  if (!file) return '';
  if (file.size > 3000000) throw new Error('Choose a focused ZIP under 3 MB.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  let raw = ''; for (const byte of bytes) raw += String.fromCharCode(byte);
  return btoa(raw);
}

async function downloadArtifact(url, filename) {
  const response = await authenticatedFetch(url, {headers: identityHeaders()});
  if (!response.ok) throw new Error('Could not download this artifact.');
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = element('a'); link.href = objectUrl; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function artifactsSection(task, detail) {
  const id = task.id;
  const data = await api(`/tasks/${encodeURIComponent(id)}/artifacts`);
  const section = element('section', undefined, 'evidence');
  section.append(element('h3', 'Artifacts · available before acceptance'),
    element('p', 'Preview and download everything currently stored with this task. Downloads do not volunteer you or start AI work.'));
  const readiness = element('div', undefined, 'package-readiness');
  readiness.append(element('strong', data.readiness.status === 'needs_context' ? 'Missing inputs · review before starting' : 'Source supplied · verification still required'),
    element('p', `${data.readiness.criteria_count} criteria · ${data.readiness.source_file_count} source files`));
  for (const warning of data.readiness.missing) readiness.append(element('p', warning));
  readiness.append(element('small', data.readiness.verification)); section.append(readiness);
  const all = element('button', 'Download all artifacts (ZIP)', 'primary');
  all.onclick = () => run(() => downloadArtifact(data.download_url, `task-${id}-artifacts.zip`));
  section.append(all);
  const files = element('details'); files.append(element('summary', `${data.items.length} files · view individual downloads`));
  for (const file of data.items) {
    const row = element('div', undefined, 'event');
    const button = element('button', 'Download'); button.setAttribute('aria-label', `Download ${file.path}`);
    button.onclick = () => run(() => downloadArtifact(file.download_url, file.path.split('/').at(-1)));
    row.append(element('span', `${file.path} · ${file.size.toLocaleString()} bytes`), button); files.append(row);
  }
  section.append(files);
  for (const attachment of task.packages) {
    const record = element('div', undefined, 'package-record');
    record.append(element('strong', `${attachment.kind === 'response' ? 'Response' : 'Source / support'} package · ${attachment.actor}`),
      element('p', attachment.note || 'Attached evidence; not automatic verification.'),
      element('code', `SHA-256 ${attachment.sha256}`));
    if (attachment.kind === 'response') record.append(element('p', attachment.input_verified ? 'Original input ZIP hash and task ID matched.' : 'Original input linkage not independently checked; attach the original ZIP with the response to validate it.'));
    section.append(record);
  }
  if ([task.creator, task.target, task.claimant, task.completed_by].includes(user)) {
    const form = element('form');
    const kindLabel = element('label', 'Attach a package'); const kind = element('select');
    for (const [value, title] of [['response', 'Response from a fresh session'], ['support', 'Source / supporting evidence']]) {
      const option = element('option', title); option.value = value; kind.append(option);
    }
    kindLabel.append(kind);
    const zipLabel = element('label', 'Package ZIP · UTF-8 files with manifest.json and file hashes');
    const zip = element('input'); zip.type = 'file'; zip.accept = '.zip'; zip.required = true; zipLabel.append(zip);
    const originalLabel = element('label', 'Original task ZIP · optional, validates response linkage');
    const original = element('input'); original.type = 'file'; original.accept = '.zip'; originalLabel.append(original);
    kind.onchange = () => { originalLabel.hidden = kind.value !== 'response'; original.value = ''; };
    const noteLabel = element('label', 'Short note'); const note = element('input'); note.maxLength = 2000; noteLabel.append(note);
    form.append(kindLabel, zipLabel, originalLabel, noteLabel,
      element('p', 'Attaches evidence only. No code runs, status change, Gold payment, or follow-up creation.'), element('button', 'Attach package'));
    form.onsubmit = event => { event.preventDefault(); run(async () => mutate(`/tasks/${id}/packages`, {
      kind: kind.value, package_zip: await encodeSourceZip(zip.files[0]), input_zip: await encodeSourceZip(original.files[0]), note: note.value})); };
    section.append(form);
  }
  if (data.external_references.length) {
    section.append(element('p', 'External references below are not embedded in the ZIP. Files mentioned in context must be attached to be included.'));
    for (const reference of data.external_references) {
      if (/^https?:\/\//i.test(reference)) {
        const link = element('a', reference); link.href = reference; link.target = '_blank'; link.rel = 'noopener noreferrer';
        const row = element('p'); row.append(link); section.append(row);
      } else section.append(element('p', reference, 'content'));
    }
  }
  detail.append(section);
}

function labeled(form, title, value = '', tag = 'input', options = []) {
  const label = element('label', title), input = element(tag); input.value = value; input.setAttribute('aria-label', title);
  if (tag === 'select') { for (const text of options) { const option = element('option', text); option.value = text; input.append(option); } input.value = value; }
  label.append(input); form.append(label); return input;
}
function taskEditor(data) {
  const form = element('form'); form.dataset.taskEditor = 'true';
  form.append(element('h3', 'Edit task'), element('p', 'Editable only before anyone claims it. Saving preserves the task ID, links and prior history.'));
  const title = labeled(form, 'Title', data.title); title.required = true; title.maxLength = 160;
  const goal = labeled(form, 'Goal', data.goal, 'textarea'); goal.required = true;
  const criteria = labeled(form, 'Completion criteria · one per line', data.criteria.join('\n'), 'textarea');
  const complexity = labeled(form, 'Complexity', data.complexity, 'select', ['HIGH', 'MEDIUM', 'LOW']);
  const workType = labeled(form, 'Work type', data.work_type, 'select', ['implementation', 'verification']);
  const links = labeled(form, 'Context links · one per line', data.context_links.join('\n'), 'textarea');
  const repository = labeled(form, 'Repository', data.repository);
  const target = labeled(form, 'Offered to', '', 'select');
  target.append(...[...document.querySelector('[name=target]').options].map(option => option.cloneNode(true)));
  target.value = data.target || '';
  const gold = labeled(form, 'Gold', data.gold); gold.type = 'number'; gold.min = '1'; gold.step = '1'; gold.required = true;
  gold.disabled = !data.funded;
  const save = element('button', 'Save edits', 'primary'); save.type = 'submit';
  const cancel = element('button', 'Discard edits'); cancel.type = 'button'; cancel.onclick = () => form.remove();
  form.append(save, cancel);
  form.onsubmit = event => {
    event.preventDefault();
    run(async () => {
      await mutate(`/tasks/${data.id}/edit`, {title: title.value, goal: goal.value,
        criteria: nonemptyLines(criteria.value), complexity: complexity.value, work_type: workType.value,
        context_links: nonemptyLines(links.value), repository: repository.value, target: target.value || null, gold: Number(gold.value)});
    });
  };
  return form;
}
const nonemptyLines = value => value.split('\n').map(line => line.trim()).filter(Boolean);
async function workflowSection(data, detail) {
  const box = element('details', undefined, 'evidence'); box.append(element('summary', 'Context & constellation'));
  const profile = data.profile || {validation_scope: 'SIM', migration_stage: 'WRAP', knowledge: {}};
  box.append(element('p', 'SIM = synthetic · ORA = Oracle-targeted · LIVE = application-targeted. These are declared targets, not verified coverage. WRAP → REPLACE → RETIRE describes migration intent.'));
  const roles = element('div', undefined, 'three-columns');
  for (const [role, responsibility] of Object.entries(data.roles)) { const card = element('div'); card.append(element('strong', role), element('p', responsibility)); roles.append(card); }
  box.append(roles, element('small', 'Responsibilities, not a claim that three autonomous agents ran.'));
  const form = element('form');
  const scope = labeled(form, 'Validation target', profile.validation_scope, 'select', ['SIM', 'ORA', 'LIVE']);
  const stage = labeled(form, 'Migration intent', profile.migration_stage, 'select', ['WRAP', 'REPLACE', 'RETIRE']);
  const baseline = labeled(form, 'Pinned legacy / baseline revision', profile.baseline_revision || '');
  const candidate = labeled(form, 'Pinned candidate revision', profile.candidate_revision || '');
  const environment = labeled(form, 'Verification environment', profile.environment || '');
  const known = labeled(form, 'Known · one statement | source per line', (profile.knowledge.known || []).map(item => `${item.statement} | ${item.source}`).join('\n'), 'textarea');
  const assumed = labeled(form, 'Assumed · one per line', (profile.knowledge.assumed || []).join('\n'), 'textarea');
  const unknown = labeled(form, 'Unknown · one per line', (profile.knowledge.unknown || []).join('\n'), 'textarea');
  const editable = [data.creator, data.claimant].includes(user) && data.phase !== 'Closed';
  for (const input of form.querySelectorAll('input,textarea,select')) input.disabled = !editable;
  if (editable) {
    form.append(element('p', 'Changing bound context makes existing proof stale.'), element('button', 'Save context'));
    form.onsubmit = event => { event.preventDefault(); run(async () => {
      const facts = nonemptyLines(known.value).map(line => { const at = line.indexOf('|'); if (at < 1 || !line.slice(at + 1).trim()) throw new Error('Each Known item needs a statement | source.'); return {statement: line.slice(0, at).trim(), source: line.slice(at + 1).trim()}; });
      await mutate(`/tasks/${data.id}/profile`, {validation_scope: scope.value, migration_stage: stage.value,
        baseline_revision: baseline.value, candidate_revision: candidate.value, environment: environment.value,
        knowledge: {known: facts, assumed: nonemptyLines(assumed.value), unknown: nonemptyLines(unknown.value)}});
    }); };
  }
  box.append(form);
  const dependencies = element('form'); const ids = labeled(dependencies, 'Shared prerequisites · existing task IDs, one per line', data.depends_on.join('\n'), 'textarea'); ids.disabled = !editable;
  if (editable) { dependencies.append(element('button', 'Link prerequisites')); dependencies.onsubmit = event => { event.preventDefault(); run(() => mutate(`/tasks/${data.id}/dependencies`, {depends_on: nonemptyLines(ids.value)})); }; }
  box.append(dependencies);
  const graph = await api(`/tasks/${data.id}/constellation`);
  box.append(element('h3', 'Constellation'), element('p', 'Each task appears once. Arrows point from an outcome to required child work or a shared prerequisite.'));
  const nodes = element('div', undefined, 'constellation');
  for (const node of graph.nodes) { const button = element('button', `${node.title} · ${node.phase}`); button.className = node.id === data.id ? 'current-task' : ''; button.onclick = () => run(() => show(node.id)); nodes.append(button); }
  box.append(nodes);
  const title = id => graph.nodes.find(node => node.id === id)?.title || id;
  const edges = element('ul'); for (const edge of graph.edges) edges.append(element('li', `${title(edge.from)} → ${title(edge.to)} · ${edge.kind}`));
  box.append(edges); detail.append(box);
}
function proofSection(data, detail) {
  const box = element('section', undefined, 'evidence'); box.append(element('h3', 'One proof · bound to this outcome'));
  box.append(element('p', 'One sufficient text, image or video artifact. AI reviews the criteria; a human verifies each LOW. A parent requires separate integration proof. No automatic approval.'));
  const proof = data.proof, editable = [data.creator, data.claimant].includes(user) && data.phase === 'Claimed' && data.claimant;
  if (proof) {
    box.append(element('strong', `${proof.accepted ? (proof.verification_method === 'human-only' ? 'Human verified · no passing AI review' : 'Accepted') : proof.fresh ? 'Current · awaiting verification' : 'Stale · context changed'} · ${proof.filename}`), element('p', proof.description), element('code', `SHA-256 ${proof.sha256}`));
    const controls = element('div', undefined, 'actions'); const preview = element('div');
    const view = element('button', 'View proof'); view.onclick = () => run(async () => {
      const response = await authenticatedFetch(proof.download_url, {headers: identityHeaders()}); if (!response.ok) throw new Error('Could not open proof.');
      const blob = await response.blob(); preview.replaceChildren();
      if (['text/plain', 'application/json'].includes(proof.media_type)) preview.append(element('pre', await blob.text(), 'proof-text'));
      else { const media = element(proof.media_type.startsWith('image/') ? 'img' : 'video'); const url = URL.createObjectURL(blob); media.src = url; media.className = 'proof-media'; if (media.tagName === 'IMG') { media.alt = proof.description; media.onload = () => URL.revokeObjectURL(url); } else { media.controls = true; media.onloadeddata = () => URL.revokeObjectURL(url); } preview.append(media); }
    });
    const download = element('button', 'Download proof'); download.onclick = () => run(() => downloadArtifact(proof.download_url, proof.filename)); controls.append(view, download); box.append(controls, preview);
    const review = proof.review;
    box.append(element('p', review ? `AI review: ${review.verdict} · ${review.reason || 'Review in progress'}` : 'AI review: not requested'));
    if (review) {
      const usage = review.usage;
      const state = usage?.usage_state || 'unobserved';
      const calls = usage?.api_calls == null ? 'API calls unobserved' : `${usage.api_calls} API call(s)`;
      const tokens = state === 'reported' ? `${usage.input_tokens} reported input / ${usage.output_tokens} output tokens` : state === 'no_request' ? 'No provider request' : state === 'unknown' ? 'Token usage unknown' : 'Token usage unobserved';
      const elapsed = usage?.elapsed_ms == null ? 'Elapsed time unavailable' : `${(usage.elapsed_ms / 1000).toFixed(1)}s review elapsed`;
      box.append(element('p', `Proof review usage: ${calls} · ${tokens} · ${elapsed}`));
      if (state === 'unknown') box.append(element('small', 'The request was attempted, but complete token counts were not reported. Unknown usage is not zero usage.'));
      if (state === 'unobserved') box.append(element('small', 'This review has no provider usage observations. Its request count and token use are unobserved.'));
      if (state === 'no_request') box.append(element('small', usage.reason === 'unsupported_video' ? 'Video inspection is unsupported; no provider request was made.' : 'Provider access is unavailable; no provider request was made.'));
    }
    for (const criterion of review?.criteria || []) box.append(element('p', `${criterion.index + 1}. ${criterion.verdict} · ${criterion.reason}`));
    if (proof.human) box.append(element('p', `Human LOW verification: ${proof.human.accepted ? 'accepted' : 'rejected'} · ${proof.human.note}`));
    if (editable && proof.fresh && !['queued', 'running'].includes(review?.verdict)) { const request = element('button', 'Request AI proof review'); request.onclick = () => run(() => mutate(`/tasks/${data.id}/proof-review`)); box.append(request, element('small', 'Explicit request uses the configured provider. Missing access or unsupported video review stays inconclusive.')); }
    const humanOnly = !review || (review.verdict === 'inconclusive' && !review.criteria?.some(item => item.verdict === 'fail'));
    const mediumHumanOnly = data.complexity === 'MEDIUM' && !data.required_children?.length && humanOnly;
    if (editable && (data.complexity === 'LOW' || mediumHumanOnly) && proof.fresh && (review?.verdict === 'pass' || humanOnly)) {
      const human = element('form'); const decision = labeled(human, 'Human verification decision', 'Choose…', 'select', ['Choose…', 'Accept', 'Reject']);
      if (humanOnly) human.append(element('p', 'Human-only verification: review the evidence and record your decision. This does not record an AI pass.'));
      const note = labeled(human, 'What did you personally verify?', '', 'textarea'); note.required = true;
      human.append(element('button', 'Record human decision')); human.onsubmit = event => { event.preventDefault(); run(async () => { if (decision.value === 'Choose…') throw new Error('Explicitly accept or reject the proof.'); await mutate(`/tasks/${data.id}/proof-human`, {accepted: decision.value === 'Accept', note: note.value, review_basis: humanOnly ? 'human-only' : 'ai-reviewed'}); }); }; box.append(human);
    }
    if (editable && proof.accepted) { const form = element('form'); const note = labeled(form, 'Completion note', '', 'textarea'); note.required = true; form.append(element('button', data.funded ? 'Complete & release reserved demo Gold' : 'Complete verified task', 'primary')); form.onsubmit = event => { event.preventDefault(); run(() => mutate(`/tasks/${data.id}/complete`, {note: note.value})); }; box.append(form); }
    if (['queued', 'running'].includes(review?.verdict)) proofPoll = setTimeout(() => { if (selected === data.id) run(() => show(data.id)); }, 2000);
  } else box.append(element('p', data.phase === 'Closed' ? 'Historical closure · no accepted proof recorded. Not retroactively verified.' : 'No proof yet. Pin revisions and environment in Context before submitting.'));
  if (editable) {
    const form = element('form'); const file = labeled(form, 'Primary proof · text/JSON ≤200 KB, PNG/JPEG/MP4 ≤8 MB'); file.type = 'file'; file.accept = '.txt,.md,.json,.png,.jpg,.jpeg,.mp4'; file.required = true;
    const description = labeled(form, 'How this proves the criteria', '', 'textarea'); description.required = true;
    form.append(element('p', 'Use approved test data. No credentials or private records. A replacement preserves history and needs a new review.'), element('button', proof ? 'Attach replacement proof' : 'Attach proof'));
    form.onsubmit = event => { event.preventDefault(); run(async () => { const artifact = file.files[0]; if (!artifact || artifact.size > 8000000) throw new Error('Choose one artifact under 8 MB.'); const types = {txt: 'text/plain', md: 'text/plain', json: 'application/json', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', mp4: 'video/mp4'}; const media_type = types[artifact.name.split('.').at(-1).toLowerCase()]; if (!media_type) throw new Error('Unsupported proof format.'); let raw = ''; for (const byte of new Uint8Array(await artifact.arrayBuffer())) raw += String.fromCharCode(byte); await mutate(`/tasks/${data.id}/proofs`, {filename: artifact.name, media_type, content_base64: btoa(raw), description: description.value}); }); }; box.append(form);
  }
  if (data.proof_history.length > 1) { const history = element('details'); history.append(element('summary', 'Immutable proof history')); for (const record of data.proof_history) { const button = element('button', `Download ${record.filename} · ${record.sha256.slice(0, 12)}`); button.onclick = () => run(() => downloadArtifact(`/api/v1/tasks/${data.id}/proofs/${record.proof_id}`, record.filename)); history.append(button); } box.append(history); }
  detail.append(box);
}
function sourceInput(form) {
  const label = element('label', 'Source ZIP · focused UTF-8 files, up to 2 MB unpacked; exclude secrets and dependencies');
  const input = element('input'); input.type = 'file'; input.accept = '.zip'; label.append(input);
  form.insertBefore(label, form.querySelector('button[type="submit"]'));
  return () => encodeSourceZip(input.files[0]);
}

function modelInput(form, data) {
  const settings = data.ai_options;
  const label = element('label', 'Model'); const select = element('select');
  for (const model of settings.models) {
    const option = element('option', model.name); option.value = model.value; select.append(option);
  }
  select.value = data.ai_run?.model_choice || settings.recommended;
  label.append(select);
  const recommended = settings.models.find(model => model.value === settings.recommended);
  form.append(label, element('small', `Recommended: ${recommended.name}. Selection applies when you submit.`));
  return select;
}

async function aiSection(data, detail) {
  const id = data.id;
  const owner = data.ai_run?.actor === user;
  const box = element('section', undefined, 'ai-panel');
  box.append(element('h3', 'AI workbench'));
  if (!data.ai_run && (!data.legacy || data.events.some(event => event.kind === 'reopened')) && ['open', 'working', 'blocked'].includes(data.status)
      && (!data.claimant || data.claimant === user) && (!data.target || data.target === user)) {
    box.append(element('p', data.complexity === 'LOW'
      ? (data.work_type === 'verification'
        ? 'Verification-only LOW: AI prepares evidence for human review, not source changes or a commit. It does not run checks.'
        : 'Implementation LOW: AI prepares one minimal change for one managed commit. Local verification is required.')
      : `AI researches this ${data.complexity} task and proposes a grounded, criterion-covered split. Three only when it fits. You must approve the complete set. Decomposition does not complete the parent.`));
    const form = element('form');
    const model = modelInput(form, data);
    const label = element('label', 'Additional context'); const context = element('textarea'); label.append(context); form.append(label);
    const source = sourceInput(form);
    form.append(element('button', data.complexity === 'LOW' ? 'Start with AI' : 'Propose child tasks with AI', 'primary'));
    form.onsubmit = e => { e.preventDefault(); run(async () => mutate(`/tasks/${id}/ai/start`, {model: model.value, context: context.value, source_zip: await source()})); };
    box.append(form);
  }
  const ai = data.ai_run;
  if (ai) {
    const usage = ai.usage;
    box.append(element('span', ai.status.replaceAll('_', ' '), 'pill'),
      element('p', `${ai.model} · ${ai.question_count} questions · ${usage.api_calls} API calls · ${usage.input_tokens} input / ${usage.output_tokens} output tokens · ${(usage.elapsed_ms / 1000).toFixed(1)}s`));
    if (ai.next_model && ai.next_model !== ai.model) box.append(element('p', 'Earlier turns used a different model; their recorded history is preserved.'));
    if (ai.result) box.append(element('p', ai.result.summary, 'content'));
    if (ai.result?.action === 'evidence') box.append(element('p', 'Verification-only LOW · prepared evidence, no source patch or forced commit. The API agent has not executed checks. Human verification is still required.'));
    if (ai.result?.plan?.length) {
      const plan = element('details', undefined, 'complexity-plan'); plan.open = true;
      plan.append(element('summary', 'Implementation plan · only LOW leaves can commit'));
      const render = steps => {
        const list = element('ul');
        for (const step of steps) {
          const item = element('li', `${step.complexity} · ${step.title}`);
          if (step.children.length) item.append(render(step.children));
          list.append(item);
        }
        return list;
      };
      plan.append(render(ai.result.plan)); box.append(plan);
    }
    for (const turn of ai.conversation) {
      const list = element('ul');
      for (const text of turn.questions || turn.answers) list.append(element('li', text));
      box.append(element('strong', turn.questions ? 'AI asked' : 'Developer answered'), list);
    }
    if (ai.status === 'needs_input' && owner) {
      const form = element('form'); const answers = [];
      const model = modelInput(form, data);
      for (const question of ai.conversation.at(-1).questions) {
        const label = element('label', question); const answer = element('textarea'); answer.required = true; label.append(answer); form.append(label); answers.push(answer);
      }
      const source = sourceInput(form);
      form.append(element('button', 'Send answers to AI', 'primary'));
      form.onsubmit = e => { e.preventDefault(); run(async () => mutate(`/tasks/${id}/ai/answers`, {model: model.value, answers: answers.map(a => a.value), source_zip: await source()})); };
      box.append(form);
    }
    if (ai.download_url) {
      const button = element('button', ai.result.action === 'evidence' ? 'Download evidence ZIP' : 'Download fix ZIP', 'primary');
      button.onclick = () => run(async () => {
        const response = await authenticatedFetch(ai.download_url, {headers: identityHeaders()});
        if (!response.ok) throw new Error('Could not download the fix ZIP.');
        const url = URL.createObjectURL(await response.blob());
        const link = element('a'); link.href = url; link.download = `task-${id}.zip`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
      box.append(button, element('p', 'Drop the ZIP into a fresh Codex chat. Start with START_HERE.md. Local verification is still required.'));
    }
    if (ai.status === 'ready' && owner) box.append(element('p', 'Preparation is ready, not verified. Use One proof above to submit evidence, request AI review and record human LOW verification.'));
    if (ai.status === 'followups_pending') {
      box.append(element('h3', 'Proposed child tasks · awaiting your approval'),
        element('p', 'No child tasks exist yet. Approve the complete set to preserve the complexity rule. The parent remains unresolved until its acceptance criteria are verified.'));
      const form = element('form'); const choices = [];
      const covered = new Set(ai.result.proposals.flatMap(proposal => proposal.parent_criteria || []));
      const currentContract = ai.result.proposals.length >= 2 && ai.result.why_three?.trim()
        && data.criteria.every((_, index) => covered.has(index))
        && ai.result.proposals.every(proposal => proposal.work_type && proposal.parent_criteria?.length);
      if (ai.result.why_three) form.append(element('p', `Why this split: ${ai.result.why_three}`));
      if (!currentContract) form.append(element('p', 'Preserved draft: this set needs a refreshed review with work types, parent-criterion coverage and a grounded rationale before approval. No tasks were created.'));
      ai.result.proposals.forEach((proposal, index) => {
        const card = element('div', undefined, 'evidence'); const label = element('label', `${proposal.complexity} · ${proposal.title}`);
        const choice = element('input'); choice.type = 'checkbox'; choice.value = index; label.prepend(choice); card.append(label, element('p', proposal.goal));
        if (proposal.work_type) card.append(element('small', `${proposal.work_type} · parent criteria ${(proposal.parent_criteria || []).map(index => index + 1).join(', ')}`));
        const checks = element('ul'); proposal.criteria.forEach(text => checks.append(element('li', text))); card.append(checks); form.append(card); choices.push(choice);
      });
      if (owner) {
        const approve = element('button', `Approve all ${ai.result.proposals.length} child tasks`, 'primary'); approve.disabled = !currentContract;
        form.append(approve);
        form.onsubmit = e => { e.preventDefault(); run(() => mutate(`/tasks/${id}/ai/confirm-followups`, {indices: choices.filter(c => c.checked).map(c => Number(c.value))})); };
      } else choices.forEach(choice => { choice.disabled = true; });
      box.append(form);
    }
    if (ai.status === 'failed') {
      box.append(element('p', ai.error));
      if (owner) {
        const form = element('form'); const model = modelInput(form, data);
        form.append(element('button', 'Retry AI'));
        form.onsubmit = e => { e.preventDefault(); run(() => mutate(`/tasks/${id}/ai/retry`, {model: model.value})); }; box.append(form);
      }
    }
    if (['queued', 'running'].includes(ai.status)) {
      box.append(element('p', 'AI is investigating. You can leave this page and return.'));
      aiPoll = setTimeout(() => { if (selected === id) run(() => show(id)); }, 2000);
    }
  }
  if (box.childElementCount > 1) detail.append(box);
  const lineage = await api(`/tasks/${id}/lineage`);
  if (window.renderTicketFlow && lineage.items.length > 1) {
    try {
      const detailsById = {};
      await Promise.all(lineage.items.map(async item => { try { detailsById[item.id] = await api('/tasks/' + encodeURIComponent(item.id)); } catch (error) { /* enrichment is optional */ } }));
      detail.append(window.renderTicketFlow({lineage, currentId: id, detailsById, onNavigate: target => run(() => show(target))}));
      return;
    } catch (error) { /* fall back to the plain list below */ }
  }
  const tree = element('details', undefined, 'lineage'); tree.open = true; tree.append(element('summary', 'Task history & follow-ups'));
  const add = (parent, container) => {
    const list = element('ul');
    for (const node of lineage.items.filter(item => item.parent_id === parent)) {
      const item = element('li'); const button = element('button', node.title + ' · ' + node.status);
      button.className = node.id === id ? 'current-task' : ''; button.onclick = () => run(() => show(node.id));
      item.append(button); add(node.id, item); list.append(item);
    }
    if (list.childElementCount) container.append(list);
  };
  const root = lineage.items.find(item => item.id === lineage.root_id);
  const list = element('ul'); const item = element('li'); const button = element('button', root.title + ' · ' + root.status);
  button.className = root.id === id ? 'current-task' : ''; button.onclick = () => run(() => show(root.id)); item.append(button); add(root.id, item); list.append(item); tree.append(list); detail.append(tree);
}

$('gremlins-example').onclick = () => {
  const behavior = {result: {selected: null}, state: {run_status: 'unchanged'}, effects: []};
  const observation = {scenario: 'synthetic-cancel', identity: 'fixture-user', environment: 'isolated-simulator', revision: 'fixture-v1', behavior};
  $('gremlins-input').value = JSON.stringify({scope: 'SIM', case: {name: 'Cancel leaves run unchanged', source: 'SYNTHETIC example; not a Watson finding', preconditions: 'No real application or data', stimulus: {action: 'cancel'}, expected: behavior, preservation_rule: 'Do not invent a selected instrument on cancel'}, mirrors: {legacy: observation, rest: observation, mcp: observation}}, null, 2);
};
$('gremlins-form').onsubmit = event => { event.preventDefault(); run(async () => {
  const result = await api(`/gremlins/${$('gremlins-breed').value}`, JSON.parse($('gremlins-input').value));
  const text = JSON.stringify(result, null, 2); $('gremlins-output').textContent = text;
  $('gremlins-download').hidden = false; $('gremlins-download').onclick = () => { const url = URL.createObjectURL(new Blob([text], {type: 'application/json'})); const link = element('a'); link.href = url; link.download = 'gremlins-sim-report.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
}); };
$('agents-refresh').onclick = () => run(agentRoster);
$('signoffs-refresh').onclick = () => run(signoffs);
for (const button of document.querySelectorAll(WORKSPACE_BUTTONS + ', [data-task-view]')) button.onclick = () => run(async () => { button.closest('details')?.removeAttribute('open'); offset = 0; message(''); await navigate(button.dataset.view || button.dataset.taskView); });
$('user').onchange = () => run(async () => { if (session) { renderAuth(); return; } user = $('user').value; localStorage.setItem('handoffs-user', user); offset = txOffset = 0; message(''); await navigate('open'); });
$('signin-form').onsubmit = event => {
  event.preventDefault();
  run(async () => {
    const button = $('signin-form').querySelector('button');
    button.disabled = true;
    let issued;
    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST', redirect: 'error', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: $('signin-username').value, password: $('signin-password').value})
      });
      if (response.status === 401) clearSession();
      if (!response.ok) throw new Error('Sign-in failed. Check your credentials.');
      issued = await response.json();
      if (!issued.access_token || !issued.user_id) throw new Error('Invalid sign-in response.');
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({access_token: issued.access_token, user_id: issued.user_id}));
      session = {access_token: issued.access_token, user_id: issued.user_id};
      renderAuth();
      location.reload();
    } finally {
      $('signin-password').value = '';
      button.disabled = false;
    }
  });
};
if ($('cosign-form')) $('cosign-form').onsubmit = event => {
  event.preventDefault();
  run(async () => {
    // The second person types their own password here; the page keeps their sign-in beside the first person's.
    const button = $('cosign-form').querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST', redirect: 'error', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: $('cosign-username').value, password: $('cosign-password').value})
      });
      if (!response.ok) throw new Error('Sign-in failed for the second person. Check their credentials.');
      const issued = await response.json();
      if (!issued.access_token || !issued.user_id) throw new Error('Invalid sign-in response.');
      if (issued.user_id === session?.user_id || cosigners.some(person => person.user_id === issued.user_id)) {
        message(`${issued.user_id} is already signed in on this screen.`); return;
      }
      cosigners.push({access_token: issued.access_token, user_id: issued.user_id});
      saveCosigners(); renderAuth();
      $('cosign-username').value = '';
      message(`${issued.user_id} is signed in on this screen too and can now decide as themselves.`);
      if (view === 'signoffs') await signoffs();
    } finally {
      $('cosign-password').value = '';
      button.disabled = false;
    }
  });
};
$('signout').onclick = () => run(async () => {
  const token = session?.access_token, others = cosigners.map(person => person.access_token);
  clearSession();
  let revoked = !token;
  try {
    if (token) {
      const response = await fetch('/api/v1/auth/logout', {
        method: 'POST', redirect: 'error', headers: {Authorization: 'Bearer ' + token}
      });
      revoked = response.ok || response.status === 401;
    }
    for (const other of others) {  // Everyone signed in on this screen signs out together.
      const response = await fetch('/api/v1/auth/logout', {method: 'POST', redirect: 'error', headers: {Authorization: 'Bearer ' + other}});
      revoked = revoked && (response.ok || response.status === 401);
    }
  } catch { /* Local sign-out still succeeds; never automatically retry. */ }
  if (!revoked) sessionStorage.setItem('handoffs-signout-warning', 'Signed out locally; server revocation is unconfirmed.');
  location.reload();
});
renderAuth();
const signoutWarning = sessionStorage.getItem('handoffs-signout-warning');
if (signoutWarning) { sessionStorage.removeItem('handoffs-signout-warning'); message(signoutWarning, true); }
$('search').oninput = () => run(async () => { offset = 0; await board(); });
for (const id of ['show-closed', 'assigned-by']) if ($(id)) $(id).onchange = () => run(async () => { offset = 0; await board(); });
$('previous').onclick = () => run(async () => { offset = Math.max(0, offset - pageSize); await board(); });
$('next').onclick = () => run(async () => { offset += pageSize; await board(); });
$('tx-previous').onclick = () => run(async () => { txOffset = Math.max(0, txOffset - pageSize); await transactions(); });
$('tx-next').onclick = () => run(async () => { txOffset += pageSize; await transactions(); });
const postSourceZip = sourceInput($('post-form'));
if (typeof document !== 'undefined' && $('post-form')) {
  const form = $('post-form');
  form.addEventListener('input', recordPostDraftOwner);
  form.addEventListener('change', recordPostDraftOwner);
  form.addEventListener('reset', () => {
    postDraftOwner = null;
    renderPostDraftOwner();
  });
}
$('post-form').onsubmit = e => {
  e.preventDefault();
  if (postPending) return;
  const target = e.target, picker = $('user');
  const actor = user, auth = session, token = session?.access_token, principal = session?.user_id;
  const epoch = typeof treeEpoch !== 'undefined' ? treeEpoch : null;
  const pickerValue = picker.value, pickerDisabled = picker.disabled;
  postPending = true;
  return run(async () => {
    const controls = [...target.elements].map(control => [control, control.disabled]);
    try {
      // Capture successful controls before disabling them; FormData omits disabled fields.
      const form = new FormData(target);
      for (const [control] of controls) control.disabled = true;
      picker.disabled = true;
      const lines = name => form.get(name).split('\n').map(s => s.trim()).filter(Boolean);
      const body = {title: form.get('title'), goal: form.get('goal'), criteria: lines('criteria'),
        repository: form.get('repository'), context_links: lines('context_links'), complexity: form.get('complexity'), work_type: form.get('work_type'), gold: Number(form.get('gold')), target: form.get('target') || null,
        source_zip: await postSourceZip()};
      if (user !== actor || session !== auth || session?.access_token !== token || session?.user_id !== principal ||
          picker.value !== pickerValue || (epoch !== null && treeEpoch !== epoch)) {
        throw new Error('Identity, session or workspace changed. Nothing was posted. Review the draft and submit again.');
      }
      // No await between validation and mutate's synchronous entry into api/identityHeaders.
      const result = await mutate('/tasks', body, 'Task posted:');
      if (result) target.reset();
    } finally {
      postPending = false;
      for (const [control, disabled] of controls) control.disabled = disabled;
      if (typeof renderAuth === 'function') renderAuth(); else picker.disabled = pickerDisabled;
    }
  });
};
if ($('post-cancel')) $('post-cancel').onclick = () => {
  if (postPending || !confirm('Discard this task draft and chosen ZIP?')) return;
  $('post-form').reset();
  message('Draft cleared. Drafts are not saved across reloads.');
};
if (typeof window !== 'undefined') window.addEventListener('hashchange', () => {
  run(() => openTicketHash(ticketHash(location.hash)));
});
run(async () => {
  const link = new URLSearchParams(location.hash.slice(1));
  const linkedTree = link.get('tree');
  const linkedTask = link.get('task') || link.get('opp') || link.get('bounty');
  const linkedAgents = location.hash === '#agents';
  // Construction mode: say plainly when the door is off (task eabd11e7).
  if (typeof fetch === 'function' && $('door-banner')) fetch('/health').then(r => r.json()).then(h => {
    if (h.door !== 'off') return;
    $('door-banner').textContent = `Construction mode: the door is off until ${new Date(h.prototype_auto_signoff_cutoff).toLocaleDateString()}. Sign-in and sign-offs are not required; every bypass is labelled door-off.`;
    $('door-banner').hidden = false;
  }).catch(() => {});
  const users = await api('/users');
  const navigation = typeof window !== 'undefined' && window.commonsNavigation;
  const signedIn = typeof session !== 'undefined' && !!session;
  if (!signedIn && navigation && navigation.initialUser) user = navigation.initialUser;
  if (!signedIn && !users.some(item => item.id === user)) user = 'steve';
  for (const item of users) {
    const option = element('option', item.name); option.value = item.id; $('user').append(option);
    const targetOption = option.cloneNode(true); document.querySelector('[name=target]').append(targetOption);
  }
  if (typeof renderAuth === 'function') renderAuth(); else $('user').value = user;
  await navigate(navigation ? navigation.initialView : linkedAgents ? 'agents' : 'open');
  if (linkedTree) await showTree(linkedTree);
  else if (linkedTask) await show(linkedTask);
  if (navigation) navigation.restoring = false;
});
