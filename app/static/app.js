const $ = id => document.getElementById(id);
let user = localStorage.getItem('handoffs-user') || 'steve';
let view = 'open', offset = 0, txOffset = 0, selected = null;
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
async function api(path, body) {
  const headers = {'X-Demo-User': user};
  const options = {headers};
  let operation;
  if (body !== undefined) {
    operation = JSON.stringify([user, path, body]);
    let key = sessionStorage.getItem(operation);
    if (!key) { key = crypto.randomUUID(); sessionStorage.setItem(operation, key); }
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
  $('reserved').textContent = `${data.reserved_gold.toLocaleString()} Gold reserved in bounties`;
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
  if (!result.items.length) $('cards').append(element('div', view === 'mine' ? 'Your posted and taken bounties will appear here.' : 'A clear board. Post the first bounty and put your Gold to work.', 'empty'));
  for (const item of result.items) {
    const card = element('article', undefined, 'card');
    const top = element('div'); top.append(element('span', item.status, 'pill'), element('span', `${item.gold} GOLD`, 'pill bounty-gold'));
    const button = element('button', 'View bounty'); button.onclick = () => run(() => show(item.id));
    card.append(top, element('h3', item.title), element('div', `${item.creator} → ${item.claimant || item.target || 'Open'}${item.funded ? '' : ' · Historical / unfunded'}`, 'meta'), button);
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
  view = nextView; selected = null;
  for (const id of ['board', 'post', 'wallet', 'detail']) $(id).hidden = true;
  for (const button of document.querySelectorAll('nav button')) button.classList.toggle('selected', button.dataset.view === view);
  await stats();
  if (view === 'post') $('post').hidden = false;
  else if (view === 'wallet') { $('wallet').hidden = false; await transactions(); }
  else { $('board').hidden = false; $('board-title').textContent = view === 'mine' ? 'My work' : 'Open bounties'; await board(); }
}
async function mutate(path, body = {}) {
  $('user').disabled = true;
  for (const button of document.querySelectorAll('button')) button.disabled = true;
  try {
    const result = await api(path, body);
    message(result.status === 'settled' ? 'PR recorded. Demo verification passed and Gold was paid.' : 'Saved.');
    await stats();
    await show(result.id);
    return result;
  } finally {
    $('user').disabled = false;
    for (const button of document.querySelectorAll('button')) button.disabled = false;
  }
}
async function show(id) {
  const data = await api('/bounties/' + encodeURIComponent(id));
  selected = id;
  for (const section of ['board', 'post', 'wallet']) $(section).hidden = true;
  const detail = $('detail'); detail.hidden = false; detail.replaceChildren();
  const back = element('button', '← Back to board'); back.onclick = () => run(() => navigate('open'));
  const header = element('div', undefined, 'detail-head'); header.append(element('span', data.status, 'pill'), element('span', `${data.gold} GOLD`, 'pill bounty-gold'), element('h2', data.title), element('code', data.id));
  detail.append(back, header, element('h3', 'Goal'), element('p', data.goal, 'content'), element('h3', 'Completion criteria'));
  const criteria = element('ul'); data.criteria.forEach(text => criteria.append(element('li', text))); detail.append(criteria);
  if (data.repository) detail.append(element('p', 'Repository: ' + data.repository, 'content'));
  data.context_links.forEach(text => detail.append(element('p', text, 'content')));
  detail.append(element('p', `Requester: ${data.creator} · Worker: ${data.claimant || data.target || 'Available'} · ${data.funded ? 'Gold reserved at posting. Demo-verified PR delivery pays automatically; review remains separate.' : 'Historical import. No spendable Gold or new funding was created.'}`));
  const actions = element('div', undefined, 'actions');
  const action = (label, suffix) => { const b = element('button', label); b.onclick = () => run(() => mutate(`/bounties/${id}/${suffix}`)); actions.append(b); };
  if (data.funded && data.status === 'open') {
    if (user === data.creator) action('Cancel & refund', 'cancel');
    else if (!data.target || data.target === user) action('Take bounty', 'take');
  }
  detail.append(actions);
  if (data.funded && data.claimant === user && ['working', 'blocked'].includes(data.status)) {
    const progress = element('form');
    const noteLabel = element('label', 'Progress note'); const note = element('textarea'); noteLabel.append(note);
    const progressButton = element('button', data.status === 'blocked' ? 'Resume work' : 'Mark blocked');
    progress.append(noteLabel, progressButton);
    progress.onsubmit = e => { e.preventDefault(); run(() => mutate(`/bounties/${id}/status`, {status: data.status === 'blocked' ? 'working' : 'blocked', note: note.value})); };
    detail.append(progress, element('h3', 'Deliver your PR'));
    const form = element('form'); const urlLabel = element('label', 'PR URL'); const url = element('input'); url.type = 'url'; url.required = true; url.placeholder = 'https://github.com/owner/repo/pull/123'; urlLabel.append(url);
    const evidenceLabel = element('label', 'Completion evidence'); const evidence = element('textarea'); evidence.required = true; evidenceLabel.append(evidence);
    form.append(urlLabel, evidenceLabel, element('button', 'Submit PR & receive demo payment', 'primary'));
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
}
for (const button of document.querySelectorAll('nav button')) button.onclick = () => run(async () => { offset = 0; message(''); await navigate(button.dataset.view); });
$('user').onchange = () => run(async () => { user = $('user').value; localStorage.setItem('handoffs-user', user); offset = txOffset = 0; message(''); await navigate('open'); });
$('search').oninput = () => run(async () => { offset = 0; await board(); });
$('previous').onclick = () => run(async () => { offset = Math.max(0, offset - pageSize); await board(); });
$('next').onclick = () => run(async () => { offset += pageSize; await board(); });
$('tx-previous').onclick = () => run(async () => { txOffset = Math.max(0, txOffset - pageSize); await transactions(); });
$('tx-next').onclick = () => run(async () => { txOffset += pageSize; await transactions(); });
$('post-form').onsubmit = e => {
  e.preventDefault();
  run(async () => {
    const form = new FormData(e.target);
    const lines = name => form.get(name).split('\n').map(s => s.trim()).filter(Boolean);
    const result = await mutate('/bounties', {title: form.get('title'), goal: form.get('goal'), criteria: lines('criteria'),
      repository: form.get('repository'), context_links: lines('context_links'), gold: Number(form.get('gold')), target: form.get('target') || null});
    if (result) e.target.reset();
  });
};
run(async () => {
  const users = await api('/users');
  if (!users.some(item => item.id === user)) user = 'steve';
  for (const item of users) {
    const option = element('option', item.name); option.value = item.id; $('user').append(option);
    const targetOption = option.cloneNode(true); document.querySelector('[name=target]').append(targetOption);
  }
  $('user').value = user;
  await navigate('open');
});
