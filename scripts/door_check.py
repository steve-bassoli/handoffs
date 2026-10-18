"""Prove every ASE lock works with the door on (task eabd11e7). Run before taking the door off and after putting it back.

Usage: python scripts/door_check.py [--url http://127.0.0.1:8000]
Runs the lock test modules with ASE_DOOR=on and no prototype bypass, then reports the live door state if --url is given.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCKS = {
    'signed-in identity': 'tests/test_credentials.py',
    'human acceptance': 'tests/test_human_acceptance.py',
    'sign-offs': 'tests/test_signoffs.py',
    'sign-off executors': 'tests/test_executor_signoffs.py',
    'protected rules': 'tests/test_rules.py',
    'intake screen': 'tests/test_intake_wiring.py',
    'scoped autonomy': 'tests/test_automation_mode.py',
    'door switch': 'tests/test_door.py',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', help='Live ASE base URL to report the current door state')
    args = parser.parse_args()
    env = {k: v for k, v in os.environ.items() if k not in ('ASE_PROTOTYPE_AUTO_SIGNOFF', 'HANDOFFS_DB')}
    env['ASE_DOOR'] = 'on'
    failed = []
    with tempfile.TemporaryDirectory() as scratch:
        for lock, module in LOCKS.items():
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--basetemp', str(Path(scratch) / lock.replace(' ', '-')), module],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            summary = (result.stdout.strip().splitlines() or ['no output'])[-1]
            print(f"{'PASS' if result.returncode == 0 else 'FAIL'}  {lock:20} {summary}")
            if result.returncode:
                failed.append(lock)
    if args.url:
        health = json.load(urllib.request.urlopen(args.url.rstrip('/') + '/health', timeout=10))
        print(f"Live door: {health.get('door', 'unknown')} (cutoff {health.get('prototype_auto_signoff_cutoff')})")
    print('Door check: every lock holds with the door on.' if not failed else 'Door check FAILED: ' + ', '.join(failed))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
