"""LLM assistant service for metadata guidance.

This module provides an LLM-powered assistant that helps users fill in metadata
according to profile schemas. It can be used by any UI (hub, CLI, etc.) that
needs to provide intelligent metadata assistance.

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

import logging
from typing import Any, Self

import httpx

from metaseed.specs.loader import SpecLoader

logger = logging.getLogger("metaseed.llm")


class LLMService:
    """Service for LLM-based metadata assistance.

    Provides context-aware responses to help users fill in metadata
    according to their project's profile schema.

    Args:
        api_url: OpenAI-compatible API endpoint URL.
        api_key: API key (optional for local models).
        model: Model name to use.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        model: str = "gpt-4",
    ) -> None:
        """Initialize the LLM service."""
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._loader = SpecLoader()

    @property
    def enabled(self) -> bool:
        """Check if LLM service is configured."""
        return bool(self.api_url)

    def build_system_prompt(self: Self, profile: str, version: str) -> str:
        """Build system prompt with profile schema context.

        Args:
            profile: Profile name (e.g., 'miappe', 'isa').
            version: Profile version (e.g., '1.2').

        Returns:
            System prompt with schema context.
        """
        try:
            spec = self._loader.load_profile(version, profile)
        except Exception as e:
            logger.warning(f"Failed to load profile {profile} v{version}: {e}")
            return self._build_fallback_prompt(profile, version)

        # Build entity descriptions
        entity_descriptions: list[str] = []
        for entity_name, entity_def in spec.entities.items():
            field_list = []
            for field in entity_def.fields:
                required = " (required)" if field.required else ""
                field_list.append(f"  - {field.name}: {field.type}{required}")

            entity_desc = f"### {entity_name}\n"
            if entity_def.description:
                entity_desc += f"{entity_def.description}\n"
            entity_desc += "\nFields:\n" + "\n".join(field_list)
            entity_descriptions.append(entity_desc)

        entities_text = "\n\n".join(entity_descriptions)

        return f"""You are a metadata assistant for scientific data management.
You help users fill in metadata according to the {spec.display_name or profile} v{version} standard.

## Profile: {spec.display_name or profile}
{spec.description or ''}

## Available Entities

{entities_text}

## Guidelines

1. Provide concise, helpful guidance for filling in metadata fields.
2. When suggesting values, explain why they fit the schema requirements.
3. Reference specific fields and their constraints when relevant.
4. If a field has ontology terms, mention them.
5. Be specific about required vs optional fields.
6. Keep responses focused and practical.
"""

    def _build_fallback_prompt(self: Self, profile: str, version: str) -> str:
        """Build a minimal prompt when profile can't be loaded."""
        return f"""You are a metadata assistant for scientific data management.
You help users fill in metadata according to the {profile} v{version} standard.

Provide concise, helpful guidance for filling in metadata fields.
When suggesting values, explain why they fit typical schema requirements.
"""

    async def get_response(
        self: Self,
        message: str,
        profile: str,
        version: str,
        entity_context: dict[str, Any] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Get LLM response with profile context.

        Args:
            message: User message.
            profile: Profile name.
            version: Profile version.
            entity_context: Optional context about current entity being edited.
            conversation_history: Optional list of previous messages for context.

        Returns:
            Assistant response text.

        Raises:
            RuntimeError: If LLM service is not configured or API call fails.
        """
        if not self.enabled:
            raise RuntimeError("LLM service is not configured (no api_url)")

        system_prompt = self.build_system_prompt(profile, version)

        # Add entity context if provided
        if entity_context:
            entity_type = entity_context.get("entity_type", "")
            field_name = entity_context.get("field_name", "")
            if entity_type:
                system_prompt += f"\n\nThe user is currently editing: {entity_type}"
                if field_name:
                    system_prompt += f", field: {field_name}"

        # Build messages list
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)

        # Add current user message
        messages.append({"role": "user", "content": message})

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 1024,
                    },
                )
                response.raise_for_status()

                data = response.json()
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            logger.exception("LLM API error: %s - %s", e.response.status_code, e.response.text)
            raise RuntimeError(f"LLM API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.exception("LLM request error")
            raise RuntimeError("Failed to connect to LLM service") from e
        except (KeyError, IndexError) as e:
            logger.exception("Unexpected LLM response format")
            raise RuntimeError("Invalid response from LLM service") from e

    def get_response_sync(
        self: Self,
        message: str,
        profile: str,
        version: str,
        entity_context: dict[str, Any] | None = None,
    ) -> str:
        """Synchronous version of get_response for CLI usage.

        Args:
            message: User message.
            profile: Profile name.
            version: Profile version.
            entity_context: Optional context about current entity being edited.

        Returns:
            Assistant response text.
        """
        import asyncio

        return asyncio.run(self.get_response(message, profile, version, entity_context))


__all__ = ["LLMService"]
