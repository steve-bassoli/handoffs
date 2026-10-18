"""Offline rule approval checks; import deliberately requires a completed bootstrap."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.rules as rules


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.rules_path = self.directory / 'agent-rules.json'
        self.approvals_path = self.directory / 'APPROVALS.json'
        self.original = (rules.ROOT / 'rules/agent-rules.json').read_bytes()
        self.original_hash = hashlib.sha256(self.original).hexdigest()
        self.rules_path.write_bytes(self.original)

    def entry(self, names, digest=None, **extra):
        value = {
            'sha256': digest or self.original_hash,
            'approved_by': names,
            'approved_at': '2026-10-18T00:00:00+00:00',
            'note': 'Synthetic offline test fixture, not a repository approval.',
        }
        value.update(extra)
        return value

    def ledger(self, *entries):
        self.approvals_path.write_text(json.dumps(list(entries)), encoding='utf-8')

    def load(self):
        return rules.load_rules(self.rules_path, self.approvals_path)

    def modify(self):
        value = json.loads(self.original)
        value['texts']['COMMONS_RULES'] += 'TEST CHANGE'
        self.rules_path.write_text(json.dumps(value), encoding='utf-8')
        return hashlib.sha256(self.rules_path.read_bytes()).hexdigest()

    def test_repository_bootstrap_pin_is_filled_and_matches(self):
        self.assertEqual(rules.BOOTSTRAP_SHA256, self.original_hash)

    def test_bootstrap_accepts_exact_original_only(self):
        self.ledger(self.entry(['steve'], bootstrap=True))
        self.assertEqual(self.load()['RULES'], rules.RULES)
        self.modify()
        with self.assertRaises(rules.RulesError):
            self.load()

    def test_bootstrap_cannot_be_moved_by_editing_ledger(self):
        changed_hash = self.modify()
        self.ledger(self.entry(['steve'], digest=changed_hash, bootstrap=True))
        with self.assertRaises(rules.RulesError):
            self.load()

    def test_modified_file_requires_two_humans(self):
        changed_hash = self.modify()
        self.ledger(self.entry(['steve'], digest=changed_hash))
        with self.assertRaises(rules.RulesError):
            self.load()
        self.ledger(self.entry(['steve', 'nate'], digest=changed_hash))
        self.assertIn('TEST CHANGE', self.load()['COMMONS_RULES'])

    def test_normal_approval_does_not_require_steve(self):
        self.ledger(self.entry(['nate', 'will']))
        self.assertEqual(self.load()['SHARED'], rules.SHARED)

    def test_old_two_human_approval_does_not_cover_changed_file(self):
        self.ledger(self.entry(['steve', 'nate']))
        self.modify()
        with self.assertRaises(rules.RulesError):
            self.load()

    def test_duplicate_and_unknown_approvers_fail(self):
        for names in (['steve', 'steve'], ['steve', 'relay'], ['nate', 'agent'], ['Steve', 'nate']):
            with self.subTest(names=names):
                self.ledger(self.entry(names))
                with self.assertRaises(rules.RulesError):
                    self.load()

    def test_bootstrap_flag_is_required_for_single_human(self):
        self.ledger(self.entry(['steve']))
        with self.assertRaises(rules.RulesError):
            self.load()

    def test_wrong_code_pin_rejects_bootstrap(self):
        self.ledger(self.entry(['steve'], bootstrap=True))
        with patch.object(rules, 'BOOTSTRAP_SHA256', '0' * 64):
            with self.assertRaises(rules.RulesError):
                self.load()

    def test_missing_malformed_and_duplicate_json_fail(self):
        self.ledger(self.entry(['steve', 'nate']))
        for raw in (b'{', b'{}', b'{"texts": {}, "texts": {}, "compositions": {}}'):
            self.rules_path.write_bytes(raw)
            with self.assertRaises(rules.RulesError):
                self.load()
        self.rules_path.unlink()
        with self.assertRaises(rules.RulesError):
            self.load()

    def test_invalid_approval_metadata_fails(self):
        for changes in ({'approved_at': None}, {'approved_at': '2026-10-18'},
                        {'bootstrap': 'true'}, {'note': ''}):
            self.ledger(self.entry(['steve', 'nate'], **changes))
            with self.assertRaises(rules.RulesError):
                self.load()

    def test_missing_or_malformed_ledger_fails(self):
        for raw in ('{', '{}', '[]'):
            self.approvals_path.write_text(raw, encoding='utf-8')
            with self.assertRaises(rules.RulesError):
                self.load()
        self.approvals_path.unlink()
        with self.assertRaises(rules.RulesError):
            self.load()


if __name__ == '__main__':
    unittest.main()
