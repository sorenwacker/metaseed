"""LLM assistant service for metadata guidance.

The implementation lives in :mod:`metaseed.llm.service`; this package re-exports
its public surface.

Example usage:
    from metaseed.llm import LLMService

    service = LLMService(
        api_url="http://localhost:11434/v1",
        model="llama2",
    )

    response = await service.get_response(
        message="What fields are required for Investigation?",
        profile="miappe",
        version="1.2",
    )
"""

from metaseed.llm.service import LLMService

__all__ = ["LLMService"]
