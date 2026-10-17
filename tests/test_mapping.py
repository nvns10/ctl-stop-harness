import unittest

from stopharness.controls import load_controls
from stopharness.mapping import DISCLAIMER, load_mapping, render_mapping_section, validate
from stopharness.model import Outcome, Result


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.m = load_mapping()
        self.ids = {c.control_id for c in load_controls()}

    def test_mapping_is_valid_and_complete(self):
        self.assertEqual(validate(self.m, self.ids), [])

    def test_five_frameworks_covered(self):
        self.assertEqual(set(self.m["frameworks"]), {"mas_airg", "eu_ai_act", "iso_42001", "nist_ai_rmf", "imda_mgf"})
        used = {r["framework"] for rs in self.m["mappings"].values() for r in rs}
        self.assertEqual(used, set(self.m["frameworks"]))

    def test_validator_catches_bad_entries(self):
        bad = {"frameworks": {"x": {}}, "mappings": {"CTL-NOPE": [{"framework": "y", "ref": "1", "relation": "satisfies",
               "source_check": "trust_me", "note": "n"}]}}
        problems = validate(bad, {"CTL-STOP-003"})
        self.assertGreaterEqual(len(problems), 4)

    def test_no_mapping_claims_compliance(self):
        for rs in self.m["mappings"].values():
            for r in rs:
                self.assertIn(r["relation"], {"evidence_relevant_to", "partially_addresses"})

    def test_mas_entries_do_not_overclaim_kill_switch_requirement(self):
        note = next(r["note"] for r in self.m["mappings"]["CTL-STOP-003"] if r["ref"] == "5.23(b)")
        self.assertIn("does not require", note)

    def test_report_section_has_disclaimer_and_filters(self):
        o = [Outcome("CTL-STOP-003", "cessation", Result.FAIL)]
        text = render_mapping_section(self.m, o, ["mas_airg"])
        self.assertIn(DISCLAIMER, text)
        self.assertIn("5.23(b)", text)
        self.assertNotIn("Art. 14(4)(e)", text)

    def test_result_does_not_change_mapping(self):
        a = render_mapping_section(self.m, [Outcome("CTL-STOP-003", "cessation", Result.PASS)])
        b = render_mapping_section(self.m, [Outcome("CTL-STOP-003", "cessation", Result.FAIL)])
        self.assertEqual(a.replace("(PASS)", ""), b.replace("(FAIL)", ""))


if __name__ == "__main__":
    unittest.main()
