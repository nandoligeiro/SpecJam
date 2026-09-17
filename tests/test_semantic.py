import json
import tempfile
import unittest
from pathlib import Path

from specjam.memory import MemoryKind, MemoryRecord
from specjam.meta_runtime import MetaHarnessRuntime
from specjam.semantic import SemanticRuntime
from specjam.sessions import SessionManager, SessionPolicy, SessionRequest


class FakeEmbedder:
    dimensions = 3
    model = "fake-3"

    def embed(self, text):
        normalized = text.lower()
        if "kafka" in normalized or "consumer" in normalized:
            return (1.0, 0.0, 0.0)
        return (0.0, 1.0, 0.0)


def write_config(root: Path, **memory_overrides) -> Path:
    config = root / ".specjam" / "config.json"
    config.parent.mkdir(parents=True)
    memory = {
        "enabled": True,
        "auto_wire": True,
        "backend": "exact",
        "path": "memory/specjam.db",
        "embedding": {"provider": "fake", "model": "fake-3", "dimensions": "auto"},
        "retrieval": "hybrid",
        "top_k": 2,
        "min_score": 0.0,
        "max_context_characters": 1000,
        **memory_overrides,
    }
    config.write_text(json.dumps({"memory": memory, "skill_providers": {}}), encoding="utf-8")
    return config


class SemanticRuntimeTests(unittest.TestCase):
    def test_implementation_request_is_enriched_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = SemanticRuntime(write_config(root), embedder=FakeEmbedder())
            store = runtime.connect()
            store.add(MemoryRecord.create(
                kind=MemoryKind.RECOVERY,
                content="Reset the Kafka consumer offset only after evidence review",
                embedding=(1.0, 0.0, 0.0),
                source_ref="trail://old/kafka",
                role="implementation",
                project="cards",
                repository="org/events",
            ))
            request = SessionRequest(
                "run-new", "inc-1", "implementation", "Repair Kafka consumer", "agent",
                SessionPolicy(),
                metadata={"project": "cards", "repository": "org/events"},
            )

            enriched = runtime.enrich(request)

            self.assertEqual(enriched.context_items[0].source_ref, "trail://old/kafka")
            self.assertTrue(enriched.metadata["semantic_memory"]["active"])
            self.assertEqual(enriched.metadata["semantic_memory"]["selected"], 1)

    def test_reviewers_remain_unprimed(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = SemanticRuntime(write_config(Path(directory)), embedder=FakeEmbedder())
            request = SessionRequest(
                "run", "inc", "review:security", "Review", "reviewer",
                SessionPolicy(read_only=True),
            )

            enriched = runtime.enrich(request)

            self.assertEqual(enriched.context_items, ())
            self.assertEqual(enriched.metadata["semantic_memory"]["reason"], "role_not_eligible")

    def test_first_execution_initializes_empty_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = SemanticRuntime(write_config(Path(directory)), embedder=FakeEmbedder())
            request = SessionRequest(
                "run", "inc", "implementation", "Build API", "agent", SessionPolicy(),
            )

            enriched = runtime.enrich(request)

            self.assertTrue(runtime.database_path.is_file())
            self.assertEqual(enriched.metadata["semantic_memory"]["reason"], "ready_empty")

    def test_harness_can_disable_automatic_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = SemanticRuntime(write_config(Path(directory)), embedder=FakeEmbedder())
            request = SessionRequest(
                "run", "inc", "implementation", "Build API", "agent", SessionPolicy(),
                metadata={"harness_config": {"memory": {"enabled": False}}},
            )

            enriched = runtime.enrich(request)

            self.assertFalse(enriched.metadata["semantic_memory"]["active"])
            self.assertEqual(enriched.metadata["semantic_memory"]["reason"], "disabled_by_harness")

    def test_meta_runtime_autowires_from_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            config = write_config(Path(directory))
            semantic = SemanticRuntime(config, embedder=FakeEmbedder())

            runtime = MetaHarnessRuntime.from_workspace(
                SessionManager(), config, semantic=semantic,
            )

            self.assertIsNotNone(runtime.memory)
            self.assertIsNotNone(runtime.embedder)
            self.assertTrue(runtime.memory_policy.enabled)


if __name__ == "__main__":
    unittest.main()
