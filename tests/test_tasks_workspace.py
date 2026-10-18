"""One Tasks workspace entry with a local Browse / My tasks / Post task row (task 8ca606da)."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


def test_one_tasks_entry_and_local_row_replace_three_tabs():
    for page in ('index.html', 'dashboard.html'):
        nav = re.search(r'<nav aria-label="Workspace">(.*?)</nav>', (STATIC / page).read_text(encoding='utf-8')).group(1)
        assert re.findall(r'data-view="(\w+)"', nav) == ['open', 'gremlins', 'agents', 'wallet'], page
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
