import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from specjam.cli import main
from specjam.skills import (
    FilesystemSkillProvider,
    GitSkillProvider,
    SkillLockfile,
    SkillReference,
    SkillResolver,
)


def write_skill(root: Path, name: str, description: str, triggers: list[str]) -> None:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    (skill / "rws.json").write_text(json.dumps({
        "routing": {
            "name": name,
            "description": description,
            "triggers": triggers,
            "anti_triggers": ["casual conversation"],
        },
        "workflow": [{
            "id": "execute", "objective": "Execute safely",
            "action": "Apply the skill", "verify": "Run checks", "next": [],
        }],
        "semantics": {"invariants": [], "decisions": [], "safety_rules": [], "rollback": []},
    }), encoding="utf-8")


class ExternalSkillTests(unittest.TestCase):
    def test_filesystem_catalog_selects_task_aware_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            write_skill(root, "domain-design", "Model business domains", ["bounded context", "aggregate"])
            write_skill(root, "kafka-guide", "Operate Kafka consumers", ["kafka", "consumer", "rebalance"])
            resolver = SkillResolver({"pack": FilesystemSkillProvider("pack", root)})
            candidates = tuple(
                SkillReference.parse(f"pack/{name}@latest")
                for name in ("domain-design", "kafka-guide")
            )

            selected = resolver.select("Repair Kafka consumer rebalance", candidates, max_skills=1)

            self.assertEqual(selected[0].name, "kafka-guide")

    def test_git_provider_pins_and_replays_cached_revision_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "mindware"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            write_skill(repository / "skills", "observability", "Investigate incidents", ["trace", "incident"])
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run([
                "git", "-C", str(repository), "-c", "user.name=SpecJam",
                "-c", "user.email=specjam@example.invalid", "commit", "-qm", "skills",
            ], check=True)
            subprocess.run(["git", "-C", str(repository), "tag", "0.1.0"], check=True)
            cache = root / "cache"
            lock = SkillLockfile(root / "skills.lock.json")
            reference = SkillReference.parse("mindware/observability@latest")
            online = SkillResolver({
                "mindware": GitSkillProvider("mindware", str(repository), cache_dir=cache),
            }, lock)

            first = online.resolve((reference,))[0]
            offline = SkillResolver({
                "mindware": GitSkillProvider(
                    "mindware", str(repository), cache_dir=cache, offline=True,
                ),
            }, SkillLockfile(root / "skills.lock.json"))
            replayed = offline.resolve((reference,))[0]

            self.assertEqual(first.resolved_version, "0.1.0")
            self.assertEqual(replayed.revision, first.revision)
            self.assertEqual(replayed.content_hash, first.content_hash)

    def test_cli_lists_syncs_and_verifies_filesystem_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_skill(root / "skills", "ddd", "Domain-driven design", ["aggregate"])
            config = root / "config.json"
            config.write_text(json.dumps({
                "skill_providers": {"workspace": {"type": "filesystem", "path": "skills"}},
            }), encoding="utf-8")
            lock = root / "skills.lock.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main([
                    "skills", "sync", "--config", str(config), "--lock", str(lock),
                    "--skill", "workspace/ddd@latest",
                ])
            payload = json.loads(output.getvalue())

            self.assertEqual(result, 0)
            self.assertEqual(payload["resolved"][0]["reference"], "workspace/ddd@latest")
            self.assertEqual(payload["resolved"][0]["source"], "skill://workspace/ddd@latest/SKILL.md")
            self.assertNotIn(directory, json.dumps(payload))
            self.assertTrue(lock.is_file())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "skills", "verify", "--config", str(config), "--lock", str(lock),
                ]), 0)

    def test_provider_rejects_skill_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FilesystemSkillProvider("workspace", directory)
            with self.assertRaises(ValueError):
                provider.resolve(SkillReference("workspace", "../secret", "latest"))


if __name__ == "__main__":
    unittest.main()
