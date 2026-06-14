"""Tests for the LLM assistant service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metaseed.llm import LLMService


class TestLLMService:
    """Tests for LLMService."""

    def test_init(self) -> None:
        """Test service initialization."""
        service = LLMService(
            api_url="http://localhost:11434/v1",
            api_key="test-key",
            model="llama2",
        )
        assert service.api_url == "http://localhost:11434/v1"
        assert service.api_key == "test-key"
        assert service.model == "llama2"

    def test_init_strips_trailing_slash(self) -> None:
        """Test that trailing slash is stripped from api_url."""
        service = LLMService(api_url="http://localhost:11434/v1/")
        assert service.api_url == "http://localhost:11434/v1"

    def test_enabled_with_url(self) -> None:
        """Test enabled returns True when api_url is set."""
        service = LLMService(api_url="http://localhost:11434/v1")
        assert service.enabled is True

    def test_enabled_without_url(self) -> None:
        """Test enabled returns False when api_url is empty."""
        service = LLMService(api_url="")
        assert service.enabled is False

    def test_build_system_prompt_with_valid_profile(self) -> None:
        """Test system prompt includes profile schema."""
        service = LLMService(api_url="http://localhost:11434/v1")
        prompt = service.build_system_prompt("miappe", "1.2")

        assert "metadata assistant" in prompt.lower()
        assert "MIAPPE" in prompt or "miappe" in prompt.lower()
        assert "Investigation" in prompt or "Study" in prompt

    def test_build_system_prompt_with_invalid_profile(self) -> None:
        """Test fallback prompt for invalid profile."""
        service = LLMService(api_url="http://localhost:11434/v1")
        prompt = service.build_system_prompt("nonexistent", "9.9")

        assert "metadata assistant" in prompt.lower()
        assert "nonexistent" in prompt

    @pytest.mark.asyncio
    async def test_get_response_not_enabled(self) -> None:
        """Test get_response raises when service not enabled."""
        service = LLMService(api_url="")

        with pytest.raises(RuntimeError, match="not configured"):
            await service.get_response(
                message="test",
                profile="miappe",
                version="1.2",
            )

    @pytest.mark.asyncio
    async def test_get_response_success(self) -> None:
        """Test successful LLM response."""
        service = LLMService(
            api_url="http://localhost:11434/v1",
            model="test-model",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            mock_post = mock_client.return_value.__aenter__.return_value.post

            result = await service.get_response(
                message="What is Investigation?",
                profile="miappe",
                version="1.2",
            )

            assert result == "Test response"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_response_with_entity_context(self) -> None:
        """Test response includes entity context in prompt."""
        service = LLMService(
            api_url="http://localhost:11434/v1",
            model="test-model",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Context response"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await service.get_response(
                message="Help with this field",
                profile="miappe",
                version="1.2",
                entity_context={
                    "entity_type": "Study",
                    "field_name": "title",
                },
            )

            # Verify the request included entity context
            call_args = mock_post.call_args
            request_body = call_args[1]["json"]
            system_message = request_body["messages"][0]["content"]
            assert "Study" in system_message
            assert "title" in system_message

    @pytest.mark.asyncio
    async def test_get_response_with_conversation_history(self) -> None:
        """Test response includes conversation history."""
        service = LLMService(
            api_url="http://localhost:11434/v1",
            model="test-model",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Follow-up response"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            history = [
                {"role": "user", "content": "What is Investigation?"},
                {"role": "assistant", "content": "Investigation is..."},
            ]

            await service.get_response(
                message="Tell me more",
                profile="miappe",
                version="1.2",
                conversation_history=history,
            )

            # Verify the request included history
            call_args = mock_post.call_args
            request_body = call_args[1]["json"]
            messages = request_body["messages"]
            # system + 2 history + 1 current = 4 messages
            assert len(messages) == 4

    @pytest.mark.asyncio
    async def test_get_response_api_error(self) -> None:
        """Test handling of API errors."""
        import httpx

        service = LLMService(
            api_url="http://localhost:11434/v1",
            model="test-model",
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(RuntimeError, match="LLM API error"):
                await service.get_response(
                    message="test",
                    profile="miappe",
                    version="1.2",
                )

    def test_get_response_sync(self) -> None:
        """Test synchronous wrapper."""
        service = LLMService(
            api_url="http://localhost:11434/v1",
            model="test-model",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Sync response"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = service.get_response_sync(
                message="test",
                profile="miappe",
                version="1.2",
            )

            assert result == "Sync response"

    def test_get_response_sync_forwards_conversation_history(self) -> None:
        """Test sync wrapper forwards conversation_history to get_response."""
        service = LLMService(
            api_url="http://localhost:11434/v1",
            model="test-model",
        )

        history = [
            {"role": "user", "content": "What is Investigation?"},
            {"role": "assistant", "content": "Investigation is..."},
        ]

        with patch.object(
            service, "get_response", new=AsyncMock(return_value="ok")
        ) as mock_get_response:
            result = service.get_response_sync(
                message="Tell me more",
                profile="miappe",
                version="1.2",
                conversation_history=history,
            )

            assert result == "ok"
            mock_get_response.assert_awaited_once_with(
                "Tell me more",
                "miappe",
                "1.2",
                None,
                history,
            )
