"""OpenAI provider package.

Submodules are intentionally loaded by explicit import. Importing the package
must not initialize optional runtime clients or database-backed secret stores.
"""

__all__ = ["adapter", "embeddings", "responses"]
