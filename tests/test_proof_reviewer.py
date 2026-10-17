import json

import httpx

from app.proof_reviewer import ProofReviewer
from test_proofs import upload


def test_proof_call_is_separate_tool_free_bound_and_does_not_expose_key(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    monkeypatch.setenv('HANDOFFS_PROOF_MODEL', 'fixture-model')
    task = {'title': 'Fixture', 'goal': 'Read', 'criteria': ['Observed'], 'profile': {'validation_scope': 'SIM'}}
    def handler(request):
        payload = json.loads(request.content)
        assert 'fixture-key' not in request.content.decode() and request.headers['Authorization'] == 'Bearer fixture-key'
        assert payload['store'] is False and 'tools' not in payload
        assert payload['text']['format']['strict'] is True
        assert 'bound-proof' in payload['input'][0]['content'][0]['text']
        verdict = {'verdict': 'pass', 'reason': 'Synthetic expected observation',
                   'criteria': [{'index': 0, 'verdict': 'pass', 'reason': 'Synthetic fixture'}]}
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message',
            'content': [{'type': 'output_text', 'text': json.dumps(verdict)}]}], 'usage': {'input_tokens': 20}})
    observations = []
    proof = {**upload(), 'proof_id': 'bound-proof', 'binding': 'bound-revision',
             '_record_usage': lambda **value: observations.append(value)}
    assert ProofReviewer(httpx.MockTransport(handler)).review(task, proof)['verdict'] == 'pass'
    assert observations == [{'stage': 'request_started', 'model': 'fixture-model'},
                            {'stage': 'response_received', 'model': 'fixture-model', 'usage_state': 'unknown',
                             'response_status': 'completed'}]


def test_missing_key_and_unsupported_video_cannot_pass(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    task = {'criteria': ['Observed']}
    observations = []
    proof = {**upload(), '_record_usage': lambda **value: observations.append(value)}
    assert ProofReviewer().review(task, proof)['verdict'] == 'inconclusive'
    assert ProofReviewer().review(task, {**proof, 'media_type': 'video/mp4'})['verdict'] == 'inconclusive'
    assert [value['stage'] for value in observations] == ['no_request', 'no_request']
    assert [value['reason'] for value in observations] == ['missing_key', 'unsupported_video']
