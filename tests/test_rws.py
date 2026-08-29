import unittest
from pathlib import Path

from specjam.rws import load_rwsa, validate_rwsa


SKILLS = Path(__file__).parents[1] / "src/specjam/payload/workspace/skills"


class RWSATests(unittest.TestCase):
    def test_bundled_contracts_validate(self):
        for path in SKILLS.glob("*/rws.json"):
            profile = load_rwsa(path)
            self.assertFalse(validate_rwsa(profile), path)
            self.assertEqual(profile.routing.name, path.parent.name)

    def test_contract_has_workflow_and_attachments(self):
        profile = load_rwsa(SKILLS / "specjam-trace-to-skill/rws.json")
        self.assertGreaterEqual(len(profile.workflow), 2)
        self.assertTrue(profile.attachments)
        self.assertIn("failure paths remain visible", profile.semantics.invariants)


if __name__ == "__main__":
    unittest.main()

