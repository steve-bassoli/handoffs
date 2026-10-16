import json

import httpx

from app.proof_reviewer import ProofReviewer
from test_proofs import upload


def test_proof_call_is_separate_tool_free_bound_and_does_not_expose_key(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
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
    proof = {**upload(), 'proof_id': 'bound-proof', 'binding': 'bound-revision'}
    assert ProofReviewer(httpx.MockTransport(handler)).review(task, proof)['verdict'] == 'pass'


def test_missing_key_and_unsupported_video_cannot_pass(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    task = {'criteria': ['Observed']}
    assert ProofReviewer().review(task, upload())['verdict'] == 'inconclusive'
    assert ProofReviewer().review(task, {**upload(), 'media_type': 'video/mp4'})['verdict'] == 'inconclusive'
