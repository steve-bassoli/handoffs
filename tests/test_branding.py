from conftest import post_task


def test_commons_identity_is_served_with_existing_assets_and_technical_routes(client):
    page = client.get('/')
    assert page.status_code == 200
    assert '<title>The Commons · Ask freely. Share freely. Build together.</title>' in page.text
    assert '<h1>Ask freely. Share freely. Build together.</h1>' in page.text
    assert 'aria-label="Thermo Fisher Scientific The Commons home"' in page.text
    assert '>+ Post task</button>' in page.text
    assert 'Demo identity and PR verification' in page.text
    assert client.get('/static/thermo-fisher-logo.svg').status_code == 200
    assert client.get('/openapi.json').json()['info']['title'] == 'The Commons'
    health = client.get('/health').json()
    assert {key: health[key] for key in ('status', 'mode')} == {'status': 'ok', 'mode': 'demo'}
    original = post_task(client, gold=10).json()
    assert client.get('/api/v1/tasks/' + original['id']).json()['title'] == original['title']
    assert client.get('/api/v1/me/stats').json()['reserved_gold'] == 10
