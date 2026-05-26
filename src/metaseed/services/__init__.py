"""Metaseed services for external integrations.

This module provides centralized services for external API integrations
with caching, rate limiting, and consistent behavior across all metaseed
components (facade, MCP, CLI, UI).
"""

from metaseed.services.ontology import OntologyService, get_ontology_service

__all__ = [
    "OntologyService",
    "get_ontology_service",
]
