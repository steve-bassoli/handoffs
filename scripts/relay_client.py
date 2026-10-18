"""Relay board writes MUST use this client: attribution is not authentication.
Pass user-directed only for an explicit human request; otherwise use autonomous
with the current tree ticket as --scope. Never retry an unknown outcome blindly.
"""
import argparse
import json
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--method', choices=('POST', 'PUT', 'PATCH', 'DELETE'), default='POST')
    parser.add_argument('--user', required=True)
    parser.add_argument('--intent', choices=('user-directed', 'autonomous'), required=True)
    parser.add_argument('--scope')
    parser.add_argument('--idempotency-key', required=True)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment:
        parser.error('Use an explicit HTTP(S) board URL without credentials or fragment')
    if args.intent == 'autonomous' and not args.scope:
        parser.error('Autonomous writes require --scope TASK_ID')
    body = sys.stdin.read()
    json.loads(body)
    headers = {'Content-Type': 'application/json', 'X-Demo-User': args.user,
               'X-Automation': 'relay', 'X-Action-Intent': args.intent,
               'Idempotency-Key': args.idempotency_key}
    if args.scope:
        headers['X-Automation-Scope'] = args.scope
    request = Request(args.url, data=body.encode('utf-8'), headers=headers, method=args.method)
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            print(response.read().decode('utf-8'))
    except HTTPError as error:
        print('HTTP ' + str(error.code), file=sys.stderr)
        print(error.read().decode('utf-8'), file=sys.stderr)
        return 1
    except OSError:
        print('Transport failure: outcome unknown; inspect history before any retry.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
