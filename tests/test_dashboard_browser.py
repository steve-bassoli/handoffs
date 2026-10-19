"""Real browser integration, isolated data and no provider calls."""
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest


def fixture_app():
    from app import main
    root = Path(os.environ['DASHBOARD_TEST_ROOT'])
    main.roster = lambda: {'available': True, 'items': [{'id': 'fixture-agent', 'name': 'bob',
        'state': 'active', 'resting': False, 'level': 1, 'session': 'session-test'}]}
    return main.create_app(root / 'tasks.sqlite')


NODE = r'''
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1400,height:1000},reducedMotion:'reduce'});
  const errors=[],reads=[],writes=[];let status=200;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.method());});
  await page.route('**/api/dashboard/live*',async route=>{
   reads.push(route.request());
   if(status==='ledger-failure'||status==='changed-ledger'){
    const response=await route.fetch(),data=await response.json();
    data.ops.sources.ledger={...data.ops.sources.ledger,status:'unavailable',data:null,error_code:'ledger_unavailable'};
    if(status==='changed-ledger')data.ops.sources.ledger.source_id='replacement-ledger';
    return route.fulfill({response,json:data});
   }
   if(status!==200)return route.fulfill({status,contentType:'application/json',body:'{}'});
   return route.continue();
  });
  await page.goto(process.argv[1]+'/#task='+process.argv[2]);
  await page.waitForFunction(()=>!document.querySelector('#detail').hidden);
  const workspace=()=>page.locator('nav[aria-label="Workspace"]').innerText();
  const mainNavigation=await workspace();
  const link=page.getByRole('link',{name:'Open dashboard for this task'});
  assert((await link.getAttribute('href')).includes('user=steve'));
  await link.click();
  await page.waitForFunction(()=>document.querySelector('[data-dashboard-status]').textContent.includes('last-good'));
  assert.equal(await workspace(),mainNavigation);
  assert.equal(await page.locator('#dashboard-link').getAttribute('aria-current'),'page');
  assert(await page.locator('#dashboard-link').evaluate(el=>el.classList.contains('selected')));
  assert.equal(await page.locator('#dashboard-user').inputValue(),'steve');
  assert.equal(await page.locator('#dashboard-task').inputValue(),process.argv[2]);
  assert((await page.locator('[data-dashboard-slot="flow"]').innerText()).includes('Browser integration task'));
  assert((await page.locator('[data-dashboard-slot="ops"]').innerText()).includes('Gold: 990'));
  assert((await page.locator('[data-dashboard-slot="ops"]').innerText()).includes('Codex allowance'));
  await page.locator('#dashboard-session').selectOption('session-test');
  await page.waitForFunction(()=>document.querySelector('[data-dashboard-slot="live"]').textContent.includes('Selected session hierarchy'));
  const graphButton=page.locator('.flow-card').first();await graphButton.focus();
  const focused=await graphButton.elementHandle();
  await page.waitForResponse(r=>r.url().includes('/api/dashboard/live')&&r.status()===200);
  assert(await focused.evaluate(el=>el===document.activeElement));
  status='ledger-failure';await page.locator('[data-dashboard-resume]').click();
  await page.waitForFunction(()=>document.querySelector('.dashboard-ops-card').textContent.includes('STALE'));
  assert((await page.locator('[data-dashboard-status]').innerText()).includes('last-good'));
  assert((await page.locator('.dashboard-ops-card').first().innerText()).includes('$1998.00'));
  status='changed-ledger';await page.locator('[data-dashboard-resume]').click();
  await page.waitForFunction(()=>document.querySelector('.dashboard-ops-card').textContent.includes('Source status: unavailable'));
  assert((await page.locator('.dashboard-ops-card').first().innerText()).includes('Source ceiling: Unknown'));
  status=200;await page.locator('[data-dashboard-resume]').click();
  await page.waitForFunction(()=>document.querySelector('.dashboard-ops-card').textContent.includes('Source status: ok'));
  await page.locator('[data-dashboard-pause]').focus();await page.keyboard.press('Enter');
  assert((await page.locator('[data-dashboard-status]').innerText()).includes('Paused'));
  assert((await page.locator('[data-dashboard-slot="ops"]').innerText()).includes('polling paused'));
  status=500;await page.locator('[data-dashboard-resume]').click();
  await page.waitForFunction(()=>document.querySelector('[data-dashboard-status]').textContent.includes('Snapshot read failed'));
  assert((await page.locator('[data-dashboard-slot="flow"]').innerText()).includes('Browser integration task'));
  assert((await page.locator('[data-dashboard-slot="ops"]').innerText()).includes('STALE'));
  status=200;await page.locator('#dashboard-user').selectOption('nate');
  await page.waitForFunction(()=>document.querySelector('#dashboard-context-status').textContent.includes('Selected user: nate')&&document.querySelector('[data-dashboard-slot="ops"]').textContent.includes('Gold: 0'));
  assert.equal(reads.at(-1).headers()['x-demo-user'],'nate');
  assert(!reads.at(-1).url().includes('steve'));
  status=403;await page.locator('[data-dashboard-resume]').click();
  await page.waitForFunction(()=>document.querySelector('[data-dashboard-status]').textContent.includes('Authentication stopped'));
  const stopped=reads.length;await page.locator('[data-dashboard-resume]').click();
  assert.equal(reads.length,stopped);
  await page.getByRole('link',{name:'← Back to Tasks'}).click();
  await page.waitForFunction(()=>document.querySelector('#user').value==='nate');
  assert.equal(await page.locator('#dashboard-link').innerText(),'Dashboard');
  // Every tab crosses the document boundary with context and a fresh view.
  status=200;
  for(const view of ['open','mine','post','gremlins','agents','wallet']){
   await page.locator(`nav[aria-label="Workspace"] [data-view="${view}"]`).click();
   await page.waitForFunction(view=>document.querySelector(`nav [data-view="${view}"]`).classList.contains('selected'),view);
   await page.locator('#dashboard-link').click();
   await page.waitForFunction(()=>document.querySelector('[data-dashboard-status]').textContent.includes('last-good'));
   assert.equal(await page.locator('#dashboard-user').inputValue(),'nate');
   assert.equal(await page.locator('#dashboard-task').inputValue(),process.argv[2]);
   assert.equal(await workspace(),mainNavigation);
   if(view==='agents')assert.equal(await page.locator('#agent-rows').count(),0);
   if(view!=='wallet'){
    await page.locator(`nav[aria-label="Workspace"] [data-view="${view}"]`).click();
    await page.waitForFunction(view=>document.querySelector(`nav [data-view="${view}"]`).classList.contains('selected'),view);
   }
  }
  await page.locator('nav [data-view="post"]').click();
  await page.waitForFunction(()=>!document.querySelector('#post').hidden);
  await page.locator('#post input[name="title"]').fill('Draft must not survive reset');
  await page.locator('#dashboard-link').click();
  await page.waitForFunction(()=>document.querySelector('[data-dashboard-status]').textContent.includes('last-good'));
  await page.goBack();
  await page.waitForFunction(()=>document.querySelector('#post')&&!document.querySelector('#post').hidden&&document.querySelector('#post input[name="title"]').value==='');
  assert.equal(await page.locator('#user').inputValue(),'nate');
  await page.goForward();
  await page.waitForFunction(()=>document.querySelector('[data-dashboard-status]')?.textContent.includes('last-good'));
  assert.equal(await page.locator('#dashboard-task').inputValue(),process.argv[2]);
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  // A fresh, invalid selection never guesses another identity.
  const other=await browser.newPage();let unselected=0;
  await other.route('**/api/dashboard/live*',r=>{unselected++;return r.continue()});
  await other.goto(process.argv[1]+'/dashboard?user=unknown');
  await other.waitForFunction(()=>document.querySelector('#dashboard-context-status').textContent.includes('Choose a registered user'));
  assert.equal(unselected,0);await other.close();
  console.log('PASS real browser: all tabs, matching workspace navigation, Dashboard selection, user/task preservation, clean back/forward reset, explicit identities, snapshots, session, flow/Ops, focus, pause, stale data, 403 stop, no mutations or guessed identity.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
'''


def test_dashboard_connected_browser(tmp_path):
    node = shutil.which('node')
    if not node or subprocess.run([node, '-e', "require.resolve('playwright')"], capture_output=True).returncode:
        pytest.skip('Playwright/Node unavailable; real-browser integration is unverified')
    session = tmp_path / 'astra-tree/session-test'
    session.mkdir(parents=True)
    (session / 'plan.json').write_text('{"tree":{"bob":{"level":1,"parent":null}}}', encoding='utf-8')
    (session / 'summary.json').write_text('{"requests":1,"unknown_usage":false,"upper_bound_cents_for_reported_usage":5}', encoding='utf-8')
    (session / 'board.jsonl').write_text('{"event":"checkpoint","at_utc":"2026-10-17T20:00:00Z"}\n', encoding='utf-8')
    with sqlite3.connect(tmp_path / 'api-budget.sqlite') as connection:
        connection.executescript('CREATE TABLE budget(id INTEGER,ceiling INTEGER,baseline INTEGER);'
            'INSERT INTO budget VALUES(1,199800,0); CREATE TABLE calls(id TEXT,state TEXT,held INTEGER);')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'DASHBOARD_TEST_ROOT': str(tmp_path), 'OPENAI_API_KEY': '',
           'PYTHONPATH': os.pathsep.join((str(root), str(root / 'tests')))}
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'test_dashboard_browser:fixture_app',
        '--factory', '--host', '127.0.0.1', '--port', str(port)], cwd=tmp_path, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail('Isolated dashboard service exited')
            try:
                if httpx.get(base + '/health', timeout=1).is_success:
                    break
            except httpx.RequestError:
                pass
            time.sleep(.1)
        else:
            pytest.fail('Isolated dashboard service did not become ready')
        posted = httpx.post(base + '/api/v1/tasks', headers={'X-Demo-User': 'steve',
            'Idempotency-Key': 'browser-fixture'}, json={'title': 'Browser integration task', 'goal': 'Read-only display',
            'criteria': ['Works'], 'gold': 10, 'complexity': 'LOW'}).raise_for_status().json()
        result = subprocess.run([node, '-e', NODE, base, posted['id']], capture_output=True,
                                text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        process.terminate()
        process.wait(timeout=5)
