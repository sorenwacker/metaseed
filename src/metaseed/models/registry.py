"""The error a model lookup raises when generation cannot resolve a name.

The ``ModelRegistry`` cache that lived here was one of TWO caches for
generated models — the other being the ``ModelContext`` that nested-entity
resolution reads — and the two could hold different classes for the same
entity. ``get_model`` now reads and writes the context store alone, so the
registry is gone and only its error remains.
"""


class ModelNotFoundError(Exception):
    """Raised when a requested model is not found or cannot be generated."""
