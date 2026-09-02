"""Regression checks for the files exposed by a public distribution."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import unittest


FORBIDDEN_PUBLIC_MARKERS = (
    "Environment & " + "Infrastructure",
    "searchJira" + "IssuesUsingJql",
    "addWorklog" + "ToJiraIssue",
    ".devin/rules",
    ".engineering/skills",
    "jira-" + "timesheet",
    "LicenseRef-" + "Proprietary",
    "license: " + "Proprietary",
)


class PublicSurfaceTests(unittest.TestCase):
    def test_packaged_bridge_is_vendor_neutral(self) -> None:
        bridge = (
            files("specjam.payload")
            .joinpath("bridge", "AGENTS.md")
            .read_text(encoding="utf-8")
        )

        for marker in FORBIDDEN_PUBLIC_MARKERS:
            self.assertNotIn(marker, bridge)

    def test_bundled_skills_use_public_license(self) -> None:
        skills = files("specjam.payload").joinpath("workspace", "skills")
        for skill_file in Path(str(skills)).glob("*/SKILL.md"):
            content = skill_file.read_text(encoding="utf-8")
            self.assertIn("license: Apache-2.0", content)


if __name__ == "__main__":
    unittest.main()
