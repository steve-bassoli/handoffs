const $ = id => document.getElementById(id);
let user = localStorage.getItem('handoffs-user') || 'steve';
let view = 'open', offset = 0, txOffset = 0, selected = null;
let aiPoll, proofPoll;
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
  const headers = {'X-Demo-User': user};
  const options = {headers};
  let operation;
  if (body !== undefined) {
    operation = requestCacheKey(JSON.stringify([user, path, body]));
    let key = sessionStorage.getItem(operation);
    if (!key) { key = Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16)).join('-'); sessionStorage.setItem(operation, key); }
    headers['Idempotency-Key'] = key;
    headers['Content-Type'] = 'application/json';
    options.method = 'POST'; options.body = JSON.stringify(body);
  }
  const response = await fetch('/api/v1' + path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  if (operation) sessionStorage.removeItem(operation);
  return data;
}
async function stats() {
  const data = await api('/me/stats');
  $('gold').textContent = data.available_gold.toLocaleString();
  $('reserved').textContent = `${data.reserved_gold.toLocaleString()} Gold reserved in opportunities`;
  $('stats').replaceChildren();
  for (const [label, value] of [['Available Gold', data.available_gold], ['Reserved Gold', data.reserved_gold],
    ['Monthly grant', data.monthly_gold], ['Active work', data.active_count], ['Completed work', data.completed_count],
    ['Next allocation', new Date(data.next_allocation).toLocaleDateString()]]) {
    const box = element('div', undefined, 'stat'); box.append(element('span', label), element('strong', String(value))); $('stats').append(box);
  }
}
async function board() {
  const result = await api(`/bounties?view=${view}&limit=${pageSize}&offset=${offset}&q=${encodeURIComponent($('search').value)}`);
  $('cards').replaceChildren();
  if (!result.items.length) $('cards').append(element('div', view === 'mine' ? 'Opportunities you post or volunteer for will appear here.' : 'Nothing open right now. Post an opportunity when you have useful work to share.', 'empty'));
  for (const item of result.items) {
    const card = element('article', undefined, 'card');
    const top = element('div'); top.append(element('span', item.phase || item.status, 'pill'), element('span', item.complexity, 'pill'));
    if (item.funded) top.append(element('span', `${item.gold} GOLD`, 'pill bounty-gold'));
    const button = element('button', 'View opportunity'); button.onclick = () => run(() => show(item.id));
    card.append(top, element('h3', item.title), element('div', `${item.creator} · ${item.claimant ? 'Claimed by ' + item.claimant : item.target ? 'Offered to ' + item.target + ' · not claimed' : 'Available to claim'} · ${item.disposition || item.status.replaceAll('_', ' ')}${item.funded ? '' : ' · Unfunded'}`, 'meta'), button);
    $('cards').append(card);
  }
  $('previous').disabled = offset === 0; $('next').disabled = result.items.length < pageSize;
  $('page-label').textContent = `Page ${offset / pageSize + 1}`;
}
async function transactions() {
  const rows = await api(`/me/transactions?limit=${pageSize}&offset=${txOffset}`);
  $('transactions').replaceChildren();
  for (const item of rows) {
    const row = element('div', undefined, 'tx'); const label = element('div', item.kind.replaceAll('_', ' '));
    label.append(element('small', `${item.account_kind} · ${new Date(item.created_at).toLocaleString()}`));
    row.append(label, element('strong', `${item.amount > 0 ? '+' : ''}${item.amount} Gold`)); $('transactions').append(row);
  }
  if (!rows.length) $('transactions').append(element('p', 'No transactions on this page.'));
  $('tx-previous').disabled = txOffset === 0; $('tx-next').disabled = rows.length < pageSize;
  $('tx-page').textContent = `Page ${txOffset / pageSize + 1}`;
}
async function navigate(nextView) {
  clearTimeout(aiPoll);
  clearTimeout(proofPoll);
  view = nextView; selected = null;
  history.replaceState(null, '', location.pathname + location.search);
  for (const id of ['board', 'post', 'wallet', 'detail', 'gremlins']) $(id).hidden = true;
  for (const button of document.querySelectorAll('nav button')) button.classList.toggle('selected', button.dataset.view === view);
  await stats();
  if (view === 'post') $('post').hidden = false;
  else if (view === 'gremlins') $('gremlins').hidden = false;
  else if (view === 'wallet') { $('wallet').hidden = false; await transactions(); }
  else { $('board').hidden = false; $('board-title').textContent = view === 'mine' ? 'My work' : 'Open opportunities'; await board(); }
}
async function mutate(path, body = {}) {
  $('user').disabled = true;
  for (const button of document.querySelectorAll('button:not(:disabled)')) { button.dataset.busy = 'true'; button.disabled = true; }
  try {
    const result = await api(path, body);
    message(result.status === 'settled' ? 'Verified completion recorded. Reserved demo Gold was paid.' : 'Saved.');
    await stats();
    await show(result.id);
    return result;
  } finally {
    $('user').disabled = false;
    for (const button of document.querySelectorAll('button[data-busy]')) { button.disabled = false; delete button.dataset.busy; }
  }
}
async function show(id) {
  clearTimeout(aiPoll);
  clearTimeout(proofPoll);
  const data = await api('/bounties/' + encodeURIComponent(id));
  selected = id;
  history.replaceState(null, '', '#opp=' + encodeURIComponent(id));
  for (const section of ['board', 'post', 'wallet', 'gremlins']) $(section).hidden = true;
  const current = $('detail');
  const refreshing = !current.hidden && current.querySelector('.detail-head code')?.textContent === id;
  const detail = element('div');
  const back = element('button', '← Back to board'); back.onclick = () => run(() => navigate('open'));
  const header = element('div', undefined, 'detail-head'); header.append(element('span', data.phase, 'pill'), element('span', data.complexity, 'pill'), element('span', `Target: ${data.profile?.validation_scope || 'Unclassified'}`, 'pill'));
  if (data.funded) header.append(element('span', `${data.gold} GOLD`, 'pill bounty-gold'));
  header.append(element('h2', data.title), element('code', data.id));
  detail.append(back, header, element('h3', 'Goal'), element('p', data.goal, 'content'), element('h3', 'Completion criteria'));
  const rail = element('ol', undefined, 'phase-rail'); rail.setAttribute('aria-label', 'Opportunity lifecycle');
  for (const phase of ['Posted', 'Claimed', 'Closed']) { const item = element('li', phase); if (phase === data.phase) item.setAttribute('aria-current', 'step'); rail.append(item); }
  header.append(rail, element('small', `${data.disposition || data.status.replaceAll('_', ' ')} · Target is declared, not evidence of execution.`));
  const criteria = element('ul'); data.criteria.forEach(text => criteria.append(element('li', text))); detail.append(criteria);
  if (data.repository) detail.append(element('p', 'Repository: ' + data.repository, 'content'));
  data.context_links.forEach(text => detail.append(element('p', text, 'content')));
  await workflowSection(data, detail);
  proofSection(data, detail);
  await artifactsSection(data, detail);
  detail.append(element('p', `Requester: ${data.creator} · ${data.claimant ? 'Worker: ' + data.claimant : data.target ? 'Offered to ' + data.target + ' · not claimed' : 'Available to claim'} · ${data.funded ? 'Reserved demo Gold is released only on verified completion.' : 'Unfunded record. No new funding was created.'}`));
  const actions = element('div', undefined, 'actions');
  const action = (label, suffix) => { const b = element('button', label); b.onclick = () => run(() => mutate(`/bounties/${id}/${suffix}`)); actions.append(b); };
  if (data.funded && data.status === 'open') {
    if (user === data.creator) action('Cancel & refund', 'cancel');
    else if (!data.target || data.target === user) action('Volunteer manually', 'take');
  }
  if (!data.ai_run && ['completed', 'settled'].includes(data.status)
      && [data.creator, data.target, data.claimant, data.completed_by].includes(user)) {
    const reopen = element('button', 'Reopen as HIGH for decomposition');
    reopen.onclick = () => run(() => mutate(`/bounties/${id}/reopen`, {complexity: 'HIGH',
      note: 'Reopened for bounded child-bounty proposals. Prior completion and evidence preserved; no new acceptance or rewards.'}));
    actions.append(reopen);
  }
  detail.append(actions);
  await aiSection(data, detail);
  if (data.funded && !data.ai_run && data.claimant === user && ['working', 'blocked'].includes(data.status)) {
    const progress = element('form');
    const noteLabel = element('label', 'Progress note'); const note = element('textarea'); noteLabel.append(note);
    const progressButton = element('button', data.status === 'blocked' ? 'Resume work' : 'Mark blocked');
    progress.append(noteLabel, progressButton);
    progress.onsubmit = e => { e.preventDefault(); run(() => mutate(`/bounties/${id}/status`, {status: data.status === 'blocked' ? 'working' : 'blocked', note: note.value})); };
    detail.append(progress, element('h3', 'Deliver your PR'));
    const form = element('form'); const urlLabel = element('label', 'PR URL'); const url = element('input'); url.type = 'url'; url.required = true; url.placeholder = 'https://github.com/owner/repo/pull/123'; urlLabel.append(url);
    const evidenceLabel = element('label', 'Completion evidence'); const evidence = element('textarea'); evidence.required = true; evidenceLabel.append(evidence);
    form.append(urlLabel, evidenceLabel, element('p', 'PR delivery cannot bypass the proof gate above.'), element('button', 'Submit PR with verified proof', 'primary'));
    form.onsubmit = e => { e.preventDefault(); run(() => mutate(`/bounties/${id}/deliveries`, {pr_url: url.value, evidence: evidence.value})); };
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
    review.onsubmit = e => { e.preventDefault(); run(() => mutate(`/bounties/${id}/reviews`, {decision: choice.value, note: note.value})); };
    detail.append(review);
  }
  if (data.legacy) {
    detail.append(element('h3', 'Legacy context'), element('p', `Source revision: ${data.legacy.revision}`, 'content'));
    for (const document of data.legacy.documents) {
      detail.append(element('h3', document.path), element('p', document.content, 'content'));
    }
  }
  detail.append(element('h3', 'History'));
  for (const event of data.events) {
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
async function encodeSourceZip(file) {
  if (!file) return '';
  if (file.size > 3000000) throw new Error('Choose a focused ZIP under 3 MB.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  let raw = ''; for (const byte of bytes) raw += String.fromCharCode(byte);
  return btoa(raw);
}

async function downloadArtifact(url, filename) {
  const response = await fetch(url, {headers: {'X-Demo-User': user}});
  if (!response.ok) throw new Error('Could not download this artifact.');
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = element('a'); link.href = objectUrl; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function artifactsSection(bounty, detail) {
  const id = bounty.id;
  const data = await api(`/bounties/${encodeURIComponent(id)}/artifacts`);
  const section = element('section', undefined, 'evidence');
  section.append(element('h3', 'Artifacts · available before acceptance'),
    element('p', 'Preview and download everything currently stored with this opportunity. Downloads do not volunteer you or start AI work.'));
  const readiness = element('div', undefined, 'package-readiness');
  readiness.append(element('strong', data.readiness.status === 'needs_context' ? 'Missing inputs · review before starting' : 'Source supplied · verification still required'),
    element('p', `${data.readiness.criteria_count} criteria · ${data.readiness.source_file_count} source files`));
  for (const warning of data.readiness.missing) readiness.append(element('p', warning));
  readiness.append(element('small', data.readiness.verification)); section.append(readiness);
  const all = element('button', 'Download all artifacts (ZIP)', 'primary');
  all.onclick = () => run(() => downloadArtifact(data.download_url, `bounty-${id}-artifacts.zip`));
  section.append(all);
  const files = element('details'); files.append(element('summary', `${data.items.length} files · view individual downloads`));
  for (const file of data.items) {
    const row = element('div', undefined, 'event');
    const button = element('button', 'Download'); button.setAttribute('aria-label', `Download ${file.path}`);
    button.onclick = () => run(() => downloadArtifact(file.download_url, file.path.split('/').at(-1)));
    row.append(element('span', `${file.path} · ${file.size.toLocaleString()} bytes`), button); files.append(row);
  }
  section.append(files);
  for (const attachment of bounty.packages) {
    const record = element('div', undefined, 'package-record');
    record.append(element('strong', `${attachment.kind === 'response' ? 'Response' : 'Source / support'} package · ${attachment.actor}`),
      element('p', attachment.note || 'Attached evidence; not automatic verification.'),
      element('code', `SHA-256 ${attachment.sha256}`));
    if (attachment.kind === 'response') record.append(element('p', attachment.input_verified ? 'Original input ZIP hash and opportunity ID matched.' : 'Original input linkage not independently checked; attach the original ZIP with the response to validate it.'));
    section.append(record);
  }
  if ([bounty.creator, bounty.target, bounty.claimant, bounty.completed_by].includes(user)) {
    const form = element('form');
    const kindLabel = element('label', 'Attach a package'); const kind = element('select');
    for (const [value, title] of [['response', 'Response from a fresh session'], ['support', 'Source / supporting evidence']]) {
      const option = element('option', title); option.value = value; kind.append(option);
    }
    kindLabel.append(kind);
    const zipLabel = element('label', 'Package ZIP · UTF-8 files with manifest.json and file hashes');
    const zip = element('input'); zip.type = 'file'; zip.accept = '.zip'; zip.required = true; zipLabel.append(zip);
    const originalLabel = element('label', 'Original opportunity ZIP · optional, validates response linkage');
    const original = element('input'); original.type = 'file'; original.accept = '.zip'; originalLabel.append(original);
    kind.onchange = () => { originalLabel.hidden = kind.value !== 'response'; original.value = ''; };
    const noteLabel = element('label', 'Short note'); const note = element('input'); note.maxLength = 2000; noteLabel.append(note);
    form.append(kindLabel, zipLabel, originalLabel, noteLabel,
      element('p', 'Attaches evidence only. No code runs, status change, Gold payment, or follow-up creation.'), element('button', 'Attach package'));
    form.onsubmit = event => { event.preventDefault(); run(async () => mutate(`/bounties/${id}/packages`, {
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
      await mutate(`/bounties/${data.id}/profile`, {validation_scope: scope.value, migration_stage: stage.value,
        baseline_revision: baseline.value, candidate_revision: candidate.value, environment: environment.value,
        knowledge: {known: facts, assumed: nonemptyLines(assumed.value), unknown: nonemptyLines(unknown.value)}});
    }); };
  }
  box.append(form);
  const dependencies = element('form'); const ids = labeled(dependencies, 'Shared prerequisites · existing opportunity IDs, one per line', data.depends_on.join('\n'), 'textarea'); ids.disabled = !editable;
  if (editable) { dependencies.append(element('button', 'Link prerequisites')); dependencies.onsubmit = event => { event.preventDefault(); run(() => mutate(`/bounties/${data.id}/dependencies`, {depends_on: nonemptyLines(ids.value)})); }; }
  box.append(dependencies);
  const graph = await api(`/bounties/${data.id}/constellation`);
  box.append(element('h3', 'Constellation'), element('p', 'Each opportunity appears once. Arrows point from an outcome to required child work or a shared prerequisite.'));
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
    box.append(element('strong', `${proof.accepted ? 'Accepted' : proof.fresh ? 'Current · awaiting verification' : 'Stale · context changed'} · ${proof.filename}`), element('p', proof.description), element('code', `SHA-256 ${proof.sha256}`));
    const controls = element('div', undefined, 'actions'); const preview = element('div');
    const view = element('button', 'View proof'); view.onclick = () => run(async () => {
      const response = await fetch(proof.download_url, {headers: {'X-Demo-User': user}}); if (!response.ok) throw new Error('Could not open proof.');
      const blob = await response.blob(); preview.replaceChildren();
      if (['text/plain', 'application/json'].includes(proof.media_type)) preview.append(element('pre', await blob.text(), 'proof-text'));
      else { const media = element(proof.media_type.startsWith('image/') ? 'img' : 'video'); const url = URL.createObjectURL(blob); media.src = url; media.className = 'proof-media'; if (media.tagName === 'IMG') { media.alt = proof.description; media.onload = () => URL.revokeObjectURL(url); } else { media.controls = true; media.onloadeddata = () => URL.revokeObjectURL(url); } preview.append(media); }
    });
    const download = element('button', 'Download proof'); download.onclick = () => run(() => downloadArtifact(proof.download_url, proof.filename)); controls.append(view, download); box.append(controls, preview);
    const review = proof.review;
    box.append(element('p', review ? `AI review: ${review.verdict} · ${review.reason || 'Review in progress'}` : 'AI review: not requested'));
    for (const criterion of review?.criteria || []) box.append(element('p', `${criterion.index + 1}. ${criterion.verdict} · ${criterion.reason}`));
    if (proof.human) box.append(element('p', `Human LOW verification: ${proof.human.accepted ? 'accepted' : 'rejected'} · ${proof.human.note}`));
    if (editable && proof.fresh && !['queued', 'running'].includes(review?.verdict)) { const request = element('button', 'Request AI proof review'); request.onclick = () => run(() => mutate(`/bounties/${data.id}/proof-review`)); box.append(request, element('small', 'Explicit request uses the configured provider. Missing access or unsupported video review stays inconclusive.')); }
    if (editable && data.complexity === 'LOW' && proof.fresh && review?.verdict === 'pass') {
      const human = element('form'); const decision = labeled(human, 'Human verification decision', 'Choose…', 'select', ['Choose…', 'Accept', 'Reject']);
      const note = labeled(human, 'What did you personally verify?', '', 'textarea'); note.required = true;
      human.append(element('button', 'Record human decision')); human.onsubmit = event => { event.preventDefault(); run(async () => { if (decision.value === 'Choose…') throw new Error('Explicitly accept or reject the proof.'); await mutate(`/bounties/${data.id}/proof-human`, {accepted: decision.value === 'Accept', note: note.value}); }); }; box.append(human);
    }
    if (editable && proof.accepted) { const form = element('form'); const note = labeled(form, 'Completion note', '', 'textarea'); note.required = true; form.append(element('button', data.funded ? 'Complete & release reserved demo Gold' : 'Complete verified opportunity', 'primary')); form.onsubmit = event => { event.preventDefault(); run(() => mutate(`/bounties/${data.id}/complete`, {note: note.value})); }; box.append(form); }
    if (['queued', 'running'].includes(review?.verdict)) proofPoll = setTimeout(() => { if (selected === data.id) run(() => show(data.id)); }, 2000);
  } else box.append(element('p', data.phase === 'Closed' ? 'Historical closure · no accepted proof recorded. Not retroactively verified.' : 'No proof yet. Pin revisions and environment in Context before submitting.'));
  if (editable) {
    const form = element('form'); const file = labeled(form, 'Primary proof · text/JSON ≤200 KB, PNG/JPEG/MP4 ≤8 MB'); file.type = 'file'; file.accept = '.txt,.md,.json,.png,.jpg,.jpeg,.mp4'; file.required = true;
    const description = labeled(form, 'How this proves the criteria', '', 'textarea'); description.required = true;
    form.append(element('p', 'Use approved test data. No credentials or private records. A replacement preserves history and needs a new review.'), element('button', proof ? 'Attach replacement proof' : 'Attach proof'));
    form.onsubmit = event => { event.preventDefault(); run(async () => { const artifact = file.files[0]; if (!artifact || artifact.size > 8000000) throw new Error('Choose one artifact under 8 MB.'); const types = {txt: 'text/plain', md: 'text/plain', json: 'application/json', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', mp4: 'video/mp4'}; const media_type = types[artifact.name.split('.').at(-1).toLowerCase()]; if (!media_type) throw new Error('Unsupported proof format.'); let raw = ''; for (const byte of new Uint8Array(await artifact.arrayBuffer())) raw += String.fromCharCode(byte); await mutate(`/bounties/${data.id}/proofs`, {filename: artifact.name, media_type, content_base64: btoa(raw), description: description.value}); }); }; box.append(form);
  }
  if (data.proof_history.length > 1) { const history = element('details'); history.append(element('summary', 'Immutable proof history')); for (const record of data.proof_history) { const button = element('button', `Download ${record.filename} · ${record.sha256.slice(0, 12)}`); button.onclick = () => run(() => downloadArtifact(`/api/v1/bounties/${data.id}/proofs/${record.proof_id}`, record.filename)); history.append(button); } box.append(history); }
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
      : `Rule of three: AI researches this ${data.complexity} opportunity and proposes exactly three criterion-covered children. You must approve the complete set. Decomposition does not complete the parent.`));
    const form = element('form');
    const model = modelInput(form, data);
    const label = element('label', 'Additional context'); const context = element('textarea'); label.append(context); form.append(label);
    const source = sourceInput(form);
    form.append(element('button', data.complexity === 'LOW' ? 'Start with AI' : 'Propose child opportunities with AI', 'primary'));
    form.onsubmit = e => { e.preventDefault(); run(async () => mutate(`/bounties/${id}/ai/start`, {model: model.value, context: context.value, source_zip: await source()})); };
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
      form.onsubmit = e => { e.preventDefault(); run(async () => mutate(`/bounties/${id}/ai/answers`, {model: model.value, answers: answers.map(a => a.value), source_zip: await source()})); };
      box.append(form);
    }
    if (ai.download_url) {
      const button = element('button', ai.result.action === 'evidence' ? 'Download evidence ZIP' : 'Download fix ZIP', 'primary');
      button.onclick = () => run(async () => {
        const response = await fetch(ai.download_url, {headers: {'X-Demo-User': user}});
        if (!response.ok) throw new Error('Could not download the fix ZIP.');
        const url = URL.createObjectURL(await response.blob());
        const link = element('a'); link.href = url; link.download = `bounty-${id}.zip`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
      box.append(button, element('p', 'Drop the ZIP into a fresh Codex chat. Start with START_HERE.md. Local verification is still required.'));
    }
    if (ai.status === 'ready' && owner) box.append(element('p', 'Preparation is ready, not verified. Use One proof above to submit evidence, request AI review and record human LOW verification.'));
    if (ai.status === 'followups_pending') {
      box.append(element('h3', 'Proposed child opportunities · awaiting your approval'),
        element('p', 'No child tickets exist yet. Approve the complete set to preserve the complexity rule. The parent remains unresolved until its acceptance criteria are verified.'));
      const form = element('form'); const choices = [];
      const covered = new Set(ai.result.proposals.flatMap(proposal => proposal.parent_criteria || []));
      const currentContract = ai.result.proposals.length === 3 && ai.result.why_three?.trim()
        && data.criteria.every((_, index) => covered.has(index))
        && ai.result.proposals.every(proposal => proposal.work_type && proposal.parent_criteria?.length);
      if (ai.result.why_three) form.append(element('p', `Why these three: ${ai.result.why_three}`));
      if (!currentContract) form.append(element('p', 'Preserved draft: this set needs a refreshed review with work types, parent-criterion coverage and a three-way rationale before approval. No tickets were created.'));
      ai.result.proposals.forEach((proposal, index) => {
        const card = element('div', undefined, 'evidence'); const label = element('label', `${proposal.complexity} · ${proposal.title}`);
        const choice = element('input'); choice.type = 'checkbox'; choice.value = index; label.prepend(choice); card.append(label, element('p', proposal.goal));
        if (proposal.work_type) card.append(element('small', `${proposal.work_type} · parent criteria ${(proposal.parent_criteria || []).map(index => index + 1).join(', ')}`));
        const checks = element('ul'); proposal.criteria.forEach(text => checks.append(element('li', text))); card.append(checks); form.append(card); choices.push(choice);
      });
      if (owner) {
        const approve = element('button', `Approve all ${ai.result.proposals.length} child opportunities`, 'primary'); approve.disabled = !currentContract;
        form.append(approve);
        form.onsubmit = e => { e.preventDefault(); run(() => mutate(`/bounties/${id}/ai/confirm-followups`, {indices: choices.filter(c => c.checked).map(c => Number(c.value))})); };
      } else choices.forEach(choice => { choice.disabled = true; });
      box.append(form);
    }
    if (ai.status === 'failed') {
      box.append(element('p', ai.error));
      if (owner) {
        const form = element('form'); const model = modelInput(form, data);
        form.append(element('button', 'Retry AI'));
        form.onsubmit = e => { e.preventDefault(); run(() => mutate(`/bounties/${id}/ai/retry`, {model: model.value})); }; box.append(form);
      }
    }
    if (['queued', 'running'].includes(ai.status)) {
      box.append(element('p', 'AI is investigating. You can leave this page and return.'));
      aiPoll = setTimeout(() => { if (selected === id) run(() => show(id)); }, 2000);
    }
  }
  if (box.childElementCount > 1) detail.append(box);
  const lineage = await api(`/bounties/${id}/lineage`);
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
for (const button of document.querySelectorAll('nav button')) button.onclick = () => run(async () => { offset = 0; message(''); await navigate(button.dataset.view); });
$('user').onchange = () => run(async () => { user = $('user').value; localStorage.setItem('handoffs-user', user); offset = txOffset = 0; message(''); await navigate('open'); });
$('search').oninput = () => run(async () => { offset = 0; await board(); });
$('previous').onclick = () => run(async () => { offset = Math.max(0, offset - pageSize); await board(); });
$('next').onclick = () => run(async () => { offset += pageSize; await board(); });
$('tx-previous').onclick = () => run(async () => { txOffset = Math.max(0, txOffset - pageSize); await transactions(); });
$('tx-next').onclick = () => run(async () => { txOffset += pageSize; await transactions(); });
const postSourceZip = sourceInput($('post-form'));
$('post-form').onsubmit = e => {
  e.preventDefault();
  run(async () => {
    const form = new FormData(e.target);
    const lines = name => form.get(name).split('\n').map(s => s.trim()).filter(Boolean);
    const result = await mutate('/bounties', {title: form.get('title'), goal: form.get('goal'), criteria: lines('criteria'),
      repository: form.get('repository'), context_links: lines('context_links'), complexity: form.get('complexity'), work_type: form.get('work_type'), gold: Number(form.get('gold')), target: form.get('target') || null,
      source_zip: await postSourceZip()});
    if (result) e.target.reset();
  });
};
run(async () => {
  const link = new URLSearchParams(location.hash.slice(1));
  const linkedOpportunity = link.get('opp') || link.get('bounty');
  const users = await api('/users');
  if (!users.some(item => item.id === user)) user = 'steve';
  for (const item of users) {
    const option = element('option', item.name); option.value = item.id; $('user').append(option);
    const targetOption = option.cloneNode(true); document.querySelector('[name=target]').append(targetOption);
  }
  $('user').value = user;
  await navigate('open');
  if (linkedOpportunity) await show(linkedOpportunity);
});
