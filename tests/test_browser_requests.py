"""Small pure-JavaScript check; no browser automation or model/network calls."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_request_cache_does_not_store_multi_megabyte_upload_bodies():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the pure JavaScript request-cache check')
    source = Path('app/static/app.js').read_text(encoding='utf-8').split('async function stats()')[0]
    checks = '''
const assert = require('node:assert/strict');
const large = JSON.stringify(['steve', '/packages', {package_zip: 'x'.repeat(6000000)}]);
const key = requestCacheKey(large);
assert.ok(key.length < 100);
assert.equal(key, requestCacheKey(large));
assert.notEqual(key, requestCacheKey(large + 'changed'));
assert.notEqual(requestCacheKey('steve:/packages'), requestCacheKey('nate:/packages'));
'''
    subprocess.run([node, '-e', "const localStorage = {getItem: () => null};\n" + source + checks], check=True, capture_output=True, text=True)
