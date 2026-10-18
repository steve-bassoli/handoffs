(async function () {
  'use strict';
  const root = document.getElementById('dashboard');
  if (!root) return;
  const userSelect = document.getElementById('dashboard-user');
  const taskSelect = document.getElementById('dashboard-task');
  const sessionSelect = document.getElementById('dashboard-session');
  const contextStatus = document.getElementById('dashboard-context-status');
  const params = new URLSearchParams(location.search);
  let controller = null, generation = 0;
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function options(select, entries, empty, selected) {
    const desired = [['', empty], ...entries];
    const current = Array.from(select.options).map(option => [option.value, option.textContent]);
    if (JSON.stringify(current) !== JSON.stringify(desired)) {
      select.replaceChildren(...desired.map(([value, label]) => {
        const option = make('option', label); option.value = value; return option;
      }));
    }
    select.value = selected || '';
  }
  function connect() {
    generation += 1;
    const epoch = generation;
    if (controller) controller.destroy();
    else if (window.dashboard) window.dashboard.destroy();
    const user = userSelect.value;
    const task = taskSelect.value;
    const session = sessionSelect.value;
    const query = new URLSearchParams();
    if (task) query.set('task', task);
    if (session) query.set('session', session);
    const pageQuery = new URLSearchParams(query);
    if (user) pageQuery.set('user', user);
    history.replaceState(null, '', location.pathname + (pageQuery.size ? '?' + pageQuery : ''));
    contextStatus.textContent = user ? 'Connecting read-only observations…' : 'Choose a registered user to connect.';
    if (user) localStorage.setItem('handoffs-user', user);
    controller = window.createDashboard(root, user ? {
      endpoint: '/api/dashboard/live' + (query.size ? '?' + query : ''),
      headers: {'X-Demo-User': user},
      fetch: async (url, settings) => {
        const response = await fetch(url, settings);
        if (!response.ok) return response;
        const snapshot = await response.json();
        if (epoch === generation && snapshot.context) {
          options(taskSelect, snapshot.context.tasks.map(row => [row.id, row.title]), 'Recent tasks', task);
          options(sessionSelect, snapshot.context.sessions.map(id => [id, id]), 'No session selected', session);
          contextStatus.textContent = 'Selected user: ' + user + ' · ' +
            (task ? 'Selected task: ' + task : 'Task list') + ' · ' +
            (session ? 'Session: ' + session : 'No session selected');
        }
        return {ok: response.ok, status: response.status, redirected: response.redirected, json: async () => snapshot};
      }
    } : {});
    window.dashboard = controller;
    if (typeof window.connectDashboardPanels === 'function') window.connectDashboardPanels(controller, {make, user});
  }
  try {
    const response = await fetch('/api/v1/users', {credentials: 'same-origin', redirect: 'error', cache: 'no-store'});
    if (!response.ok) throw new Error('users');
    const users = await response.json();
    const selected = params.has('user') ? params.get('user') : localStorage.getItem('handoffs-user');
    options(userSelect, users.map(user => [user.id, user.name]), 'Choose a user', selected);
    if (params.get('task')) options(taskSelect, [[params.get('task'), params.get('task')]], 'Recent tasks', params.get('task'));
    if (params.get('session')) options(sessionSelect, [[params.get('session'), params.get('session')]], 'No session selected', params.get('session'));
    userSelect.addEventListener('change', connect);
    taskSelect.addEventListener('change', connect);
    sessionSelect.addEventListener('change', connect);
    connect();
  } catch (_) {
    contextStatus.textContent = 'User selection unavailable. No dashboard requests started; reload to retry.';
  }
}());
