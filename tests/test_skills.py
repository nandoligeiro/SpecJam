import unittest

from specjam.skills import InMemorySkillProvider, SkillReference, SkillResolver


class SkillResolverTests(unittest.TestCase):
    def test_parses_ligeiro_mindware_reference(self):
        reference = SkillReference.parse("ligeiro-mindware/observability-engineering@0.1.0")
        self.assertEqual(reference.provider, "ligeiro-mindware")
        self.assertEqual(reference.name, "observability-engineering")
        self.assertEqual(reference.version, "0.1.0")

    def test_resolves_and_hashes_skill(self):
        provider = InMemorySkillProvider({("observability-engineering", "0.1.0"): "# Skill"})
        resolver = SkillResolver({"ligeiro-mindware": provider})
        resolved = resolver.resolve((SkillReference.parse("ligeiro-mindware/observability-engineering@0.1.0"),))
        self.assertEqual(resolved[0].resolved_version, "0.1.0")
        self.assertTrue(resolved[0].content_hash.startswith("sha256:"))

    def test_optional_unknown_provider_is_ignored(self):
        resolver = SkillResolver({})
        reference = SkillReference.parse("optional/missing@1", required=False)
        self.assertEqual(resolver.resolve((reference,)), ())


if __name__ == "__main__":
    unittest.main()
