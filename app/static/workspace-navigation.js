/* Shared cross-page routing; a page transition starts with a clean UI. */
(() => {
  'use strict';
  const views = new Set(['open', 'mine', 'post', 'gremlins', 'agents', 'wallet']);
  const params = new URLSearchParams(location.search);
  const hash = new URLSearchParams(location.hash.slice(1));
  let task = hash.get('task') || hash.get('opp') || hash.get('bounty') || params.get('task') || '';
  let selectedUser = params.get('user') || localStorage.getItem('handoffs-user') || '';
  const dashboard = location.pathname === '/dashboard';
  const url = (view, user, currentTask = task) => {
    const query = new URLSearchParams();
    if (user) query.set('user', user);
    if (currentTask) query.set('task', currentTask);
    return (view === 'dashboard' ? '/dashboard' : '/') + (query.size ? '?' + query : '') +
      (view === 'dashboard' ? '' : '#view=' + (views.has(view) ? view : 'open'));
  };
  const navigation = window.commonsNavigation = {
    restoring: true,
    initialUser: params.get('user'),
    initialView: views.has(hash.get('view')) ? hash.get('view') : location.hash === '#agents' ? 'agents' : 'open',
    update(view, user, currentTask) {
      if (selectedUser && selectedUser !== user) task = '';
      selectedUser = user;
      if (currentTask !== undefined) task = currentTask;
      const target = currentTask !== undefined
        ? url('open', user, task).split('#')[0] + '#task=' + encodeURIComponent(task)
        : url(view, user);
      if (location.pathname + location.search + location.hash !== target) {
        history[navigation.restoring ? 'replaceState' : 'pushState'](null, '', target);
      }
      const link = document.getElementById('dashboard-link');
      if (link) link.href = url('dashboard', user);
    },
    dashboardContext(user, currentTask) {
      selectedUser = user; task = currentTask;
      const home = document.getElementById('dashboard-home');
      if (home) home.href = url('open', user);
    },
  };
  if (dashboard) {
    const nav = document.querySelector('nav[aria-label="Workspace"]');
    for (const button of nav.querySelectorAll('button[data-view]')) {
      button.classList.remove('selected');
      button.addEventListener('click', () => location.assign(url(button.dataset.view, selectedUser)));
    }
    const active = nav.querySelector('#dashboard-link');
    active.classList.add('selected'); active.setAttribute('aria-current', 'page');
    active.addEventListener('click', event => {
      event.preventDefault(); location.assign(url('dashboard', selectedUser));
    });
  }
  // Restore the URL's state through normal startup, never a cached live DOM.
  window.addEventListener('popstate', () => location.reload());
  window.addEventListener('pageshow', event => {
    if (event.persisted) { location.reload(); return; }
    // Browsers can restore form values even without a back/forward-cache DOM.
    for (const form of document.querySelectorAll('form')) form.reset();
  });
})();
