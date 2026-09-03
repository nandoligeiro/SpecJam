import unittest
import warnings
from unittest.mock import patch

from specjam.embeddings import FastEmbedProvider, LocalEmbeddingUnavailable


class FakeTextEmbedding:
    def __init__(self, **options):
        self.options = options

    @staticmethod
    def list_supported_models():
        return [{"model": "test/multilingual", "dim": 3}]

    def embed(self, texts):
        return iter(((1.0, 0.0, 0.0),))


class FastEmbedProviderTests(unittest.TestCase):
    def test_discovers_dimensions_and_embeds_without_network(self):
        with patch.object(FastEmbedProvider, "_text_embedding_type", return_value=FakeTextEmbedding):
            provider = FastEmbedProvider("test/multilingual")
            self.assertEqual(provider.dimensions, 3)
            self.assertEqual(tuple(provider.embed("contrato de cartão")), (1.0, 0.0, 0.0))
            self.assertTrue(provider._engine.options["local_files_only"])

    def test_empty_text_is_rejected_before_model_loading(self):
        with patch.object(FastEmbedProvider, "_text_embedding_type", return_value=FakeTextEmbedding):
            provider = FastEmbedProvider("test/multilingual")
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                provider.embed("  ")

    def test_missing_cached_model_has_actionable_error(self):
        class MissingModel(FakeTextEmbedding):
            def embed(self, texts):
                raise OSError("not cached")

        with patch.object(FastEmbedProvider, "_text_embedding_type", return_value=MissingModel):
            provider = FastEmbedProvider("test/multilingual")
            with self.assertRaisesRegex(LocalEmbeddingUnavailable, "memory prepare"):
                provider.embed("test")

    def test_suppresses_only_the_known_pooling_compatibility_warning(self):
        class NoisyTextEmbedding(FakeTextEmbedding):
            def __init__(self, **options):
                warnings.warn(
                    "The model test/multilingual now uses mean pooling instead of CLS embedding.",
                    UserWarning,
                )
                warnings.warn("provider diagnostic", RuntimeWarning)
                super().__init__(**options)

        with patch.object(FastEmbedProvider, "_text_embedding_type", return_value=NoisyTextEmbedding):
            provider = FastEmbedProvider("test/multilingual")
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                provider.embed("test")
        self.assertEqual([str(item.message) for item in captured], ["provider diagnostic"])


if __name__ == "__main__":
    unittest.main()
