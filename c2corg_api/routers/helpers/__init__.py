"""Shared helpers for FastAPI routers — the equivalent of the Pyramid
base view classes (``DocumentRest``, ``DocumentInfoRest``,
``DocumentVersionRest``, etc.).

Instead of class-based inheritance these are plain functions that accept
the model class, schema, and other parameters so every document-type
router can reuse them.
"""
