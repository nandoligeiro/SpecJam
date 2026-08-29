import tempfile
import unittest
from pathlib import Path

from specjam.installer import install, scaffold_flow, update, verify


class InstallerTests(unittest.TestCase):
    def test_install_verify_preserve_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            first = install(target)
            self.assertIn("AGENTS.md", first.changed)
            self.assertEqual(verify(target).missing, ())
            second = install(target)
            self.assertEqual(second.changed, ())

            managed = target / ".specjam/graphs/delivery.json"
            managed.unlink()
            report = update(target)
            self.assertIn(".specjam/graphs/delivery.json", report.changed)
            self.assertTrue(managed.exists())

            bridge = target / "AGENTS.md"
            bridge.write_text("consumer instructions\n", encoding="utf-8")
            install(target)
            self.assertEqual(bridge.read_text(encoding="utf-8"), "consumer instructions\n")

    def test_modified_file_is_reported_and_preserved_on_update(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            install(target)
            managed = target / ".specjam/WORKSPACE.md"
            managed.write_text("local change\n", encoding="utf-8")
            report = verify(target)
            self.assertIn(".specjam/WORKSPACE.md", report.modified)
            update(target)
            self.assertEqual(managed.read_text(encoding="utf-8"), "local change\n")

    def test_scaffold_creates_durable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            install(target)
            work = scaffold_flow(target, "delivery", "demo")
            self.assertTrue((work / "spec.md").exists())
            self.assertTrue((work / "verification.md").exists())

            discovery = scaffold_flow(target, "discovery", "discovery-demo")
            self.assertTrue((discovery / "problem.md").exists())
            self.assertTrue((discovery / "discovery.md").exists())

            sdd = scaffold_flow(target, "sdd", "sdd-demo")
            self.assertTrue((sdd / "sdd.md").exists())
            self.assertTrue((sdd / "sdd-handoff.md").exists())

            postmortem = scaffold_flow(target, "postmortem", "incident-demo")
            self.assertTrue((postmortem / "timeline.md").exists())
            self.assertTrue((postmortem / "postmortem.md").exists())


if __name__ == "__main__":
    unittest.main()
