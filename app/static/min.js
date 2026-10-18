// MIN mode: one question (your pressure), then exactly three options. Reads only; nothing is written.
(function () {
  'use strict';
  const KEY = 'commons-min-pressure';
  const LEVELS = [
    {value: 1, label: 'Calm', hint: 'Room to take something on.'},
    {value: 2, label: 'Stretched', hint: 'Can look, not much more.'},
    {value: 3, label: 'Overloaded', hint: 'Needs to be easy or nothing.'},
  ];

  function options(pressure, user) {
    const u = encodeURIComponent(user || '');
    const board = '/?user=' + u;
    const dashboard = '/dashboard?user=' + u;
    if (pressure === 1) {
      return [
        {label: 'Take the next open task', kind: 'task', hint: 'Opens the newest open task. Taking it is still your choice.'},
        {label: 'Post a task', href: board + '#view=post', hint: 'Ask for help with something.'},
        {label: 'See the whole board', href: board, hint: 'The full experience.'},
      ];
    }
    if (pressure === 2) {
      return [
        {label: 'Read one open task', kind: 'task', hint: 'Just read it. No commitment.'},
        {label: 'See my tasks', href: board + '#view=mine', hint: 'Only what already has your name on it.'},
        {label: 'Step away for now', kind: 'rest', hint: 'Nothing here needs you right now.'},
      ];
    }
    return [
      {label: 'Read one open task', kind: 'task', hint: 'One title and one goal. That is all.'},
      {label: 'Watch, read-only', href: dashboard, hint: 'Mission control changes nothing.'},
      {label: 'Step away for now', kind: 'rest', hint: 'The board will still be here.'},
    ];
  }

  function render(root, deps) {
    const storage = deps.storage;
    const user = deps.user || 'steve';
    const el = (tag, text, className) => {
      const node = deps.document.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (className) node.className = className;
      return node;
    };
    const section = el('section', undefined, 'min');
    root.append(section);

    function read() {
      const value = Number(storage.get(KEY));
      return [1, 2, 3].includes(value) ? value : null;
    }

    function askPressure() {
      section.replaceChildren();
      section.append(el('h1', 'How much pressure are you under right now?'));
      const list = el('div', undefined, 'choices');
      for (const level of LEVELS) {
        const button = el('button', level.value + ' · ' + level.label, 'choice');
        button.type = 'button';
        button.append(el('small', level.hint));
        button.addEventListener('click', () => { storage.set(KEY, String(level.value)); showOptions(level.value); });
        list.append(button);
      }
      section.append(list);
      section.append(footer());
    }

    function footer() {
      const p = el('p', undefined, 'min-footer');
      const full = el('a', 'Full experience'); full.href = '/?user=' + encodeURIComponent(user);
      p.append(full);
      return p;
    }

    async function showOptions(pressure) {
      section.replaceChildren();
      const head = el('p', 'Pressure ' + pressure + ' · ' + LEVELS[pressure - 1].label + ' ', 'eyebrow');
      const change = el('button', 'change', 'link'); change.type = 'button';
      change.addEventListener('click', () => { storage.remove(KEY); askPressure(); });
      head.append(change);
      section.append(head, el('h1', 'Three options. Pick one or none.'));
      const list = el('div', undefined, 'choices');
      const items = options(pressure, user);
      let task = null, taskError = null;
      if (items.some(item => item.kind === 'task')) {
        try {
          const found = await deps.api('/bounties?limit=1');
          task = Array.isArray(found) && found.length ? found[0] : null;
        } catch (error) { taskError = error; }
      }
      for (const item of items) {
        const node = el(item.kind === 'rest' ? 'button' : 'a', item.label, 'choice');
        if (item.kind === 'rest') {
          node.type = 'button';
          node.addEventListener('click', () => rest(pressure));
          node.append(el('small', item.hint));
        } else if (item.kind === 'task') {
          if (task) {
            node.href = '/?user=' + encodeURIComponent(user) + '#task=' + encodeURIComponent(task.id);
            node.append(el('small', task.title || item.hint));
          } else {
            node.href = '/?user=' + encodeURIComponent(user);
            node.append(el('small', taskError ? 'Could not read the board; this opens it instead.' : 'No open task right now; this opens the board instead.'));
          }
        } else {
          node.href = item.href;
          node.append(el('small', item.hint));
        }
        list.append(node);
      }
      section.append(list, footer());
    }

    function rest(pressure) {
      section.replaceChildren();
      section.append(el('h1', 'Nothing here needs you right now.'));
      section.append(el('p', 'The board keeps. Nothing was started, claimed or spent.'));
      const back = el('button', 'Back to the three options', 'link'); back.type = 'button';
      back.addEventListener('click', () => showOptions(pressure));
      section.append(back, footer());
    }

    const remembered = read();
    if (remembered) showOptions(remembered); else askPressure();
    return section;
  }

  const api = {options, render, KEY};
  if (typeof window !== 'undefined') {
    window.minMode = api;
    if (typeof document !== 'undefined' && document.getElementById && document.getElementById('min-root')) {
      const params = new URLSearchParams(location.search);
      const session = {
        get: key => { try { return sessionStorage.getItem(key); } catch (e) { return null; } },
        set: (key, value) => { try { sessionStorage.setItem(key, value); } catch (e) { /* session memory is optional */ } },
        remove: key => { try { sessionStorage.removeItem(key); } catch (e) { /* ignore */ } },
      };
      const user = params.get('user') || 'steve';
      render(document.getElementById('min-root'), {
        document, storage: session, user,
        api: async path => {
          const response = await fetch('/api/v1' + path, {headers: {'X-Demo-User': user}});
          if (!response.ok) throw new Error('read failed');
          return response.json();
        },
      });
    }
  }
}());
