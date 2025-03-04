import pytest
from unittest.mock import patch
from datetime import datetime
from Clients.base import TokenUsage, BaseLLMClient, DummyLLMClient


class TestTokenUsage:
    def test_initialization(self):
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            prompt_cost=0.001,
            completion_cost=0.002,
            total_cost=0.003,
            model="test-model",
            cache_hit=False
        )

        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.prompt_cost == 0.001
        assert usage.completion_cost == 0.002
        assert usage.total_cost == 0.003
        assert usage.model == "test-model"
        assert usage.cache_hit is False
        assert isinstance(usage.timestamp, datetime)

    def test_initialization_with_timestamp(self):
        timestamp = datetime(2023, 1, 1, 12, 0, 0)
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="test-model",
            timestamp=timestamp
        )

        assert usage.timestamp == timestamp

    def test_to_dict(self):
        timestamp = datetime(2023, 1, 1, 12, 0, 0)
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            prompt_cost=0.001,
            completion_cost=0.002,
            total_cost=0.003,
            model="test-model",
            timestamp=timestamp,
            cache_hit=True
        )

        usage_dict = usage.to_dict()
        assert usage_dict["prompt_tokens"] == 100
        assert usage_dict["completion_tokens"] == 50
        assert usage_dict["total_tokens"] == 150
        assert usage_dict["prompt_cost"] == 0.001
        assert usage_dict["completion_cost"] == 0.002
        assert usage_dict["total_cost"] == 0.003
        assert usage_dict["model"] == "test-model"
        assert usage_dict["timestamp"] == "2023-01-01T12:00:00"
        assert usage_dict["cache_hit"] is True

    def test_str_representation(self):
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            prompt_cost=0.001,
            completion_cost=0.002,
            total_cost=0.003,
            model="test-model",
            cache_hit=False
        )

        usage_str = str(usage)
        assert "Model: test-model" in usage_str
        assert "Tokens: 100 in + 50 out = 150 total" in usage_str
        assert "Cost: $0.003000" in usage_str

    def test_str_representation_with_cache_hit(self):
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            prompt_cost=0.001,
            completion_cost=0.002,
            total_cost=0.003,
            model="test-model",
            cache_hit=True
        )

        usage_str = str(usage)
        assert "Model: test-model (cache hit)" in usage_str


class TestDummyLLMClient:
    @pytest.fixture
    def client(self):
        return DummyLLMClient()

    @pytest.mark.asyncio
    async def test_get_response(self, client):
        response = await client.get_response("Test prompt", "Test system")
        assert response == "Dummy response."

    @pytest.mark.asyncio
    async def test_generate_response(self, client):
        response = await client.generate_response([])
        assert response == "Agent session ended."

    @pytest.mark.asyncio
    async def test_check_for_user_input_request(self, client):
        needs_input, message = await client.check_for_user_input_request("Any response")
        assert needs_input is False
        assert message is None

    def test_get_model_pricing(self, client):
        pricing = client.get_model_pricing("any-model")
        assert pricing == {"input": 0.0, "output": 0.0}


class TestBaseLLMClient:
    @pytest.fixture
    def base_client(self):

        return DummyLLMClient()

    def test_initialization(self, base_client):
        assert base_client.total_prompt_tokens == 0
        assert base_client.total_completion_tokens == 0
        assert base_client.total_tokens == 0
        assert base_client.total_cost == 0.0
        assert base_client.usage_history == []
        assert base_client.max_model_tokens == 128000

    def test_add_usage(self, base_client):
        with patch("builtins.print") as mock_print:
            usage = TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                prompt_cost=0.001,
                completion_cost=0.002,
                total_cost=0.003,
                model="test-model"
            )

            base_client.add_usage(usage)

            assert base_client.total_prompt_tokens == 100
            assert base_client.total_completion_tokens == 50
            assert base_client.total_tokens == 150
            assert base_client.total_cost == 0.003
            assert len(base_client.usage_history) == 1
            assert base_client.usage_history[0] == usage
            assert mock_print.call_count == 2

    def test_add_multiple_usage(self, base_client):
        with patch("builtins.print"):
            usage1 = TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                prompt_cost=0.001,
                completion_cost=0.002,
                total_cost=0.003,
                model="test-model"
            )

            usage2 = TokenUsage(
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
                prompt_cost=0.002,
                completion_cost=0.004,
                total_cost=0.006,
                model="test-model"
            )

            base_client.add_usage(usage1)
            base_client.add_usage(usage2)

            assert base_client.total_prompt_tokens == 300
            assert base_client.total_completion_tokens == 150
            assert base_client.total_tokens == 450
            assert round(base_client.total_cost, 6) == 0.009
            assert len(base_client.usage_history) == 2

    def test_get_usage_summary(self, base_client):
        with patch("builtins.print"):
            usage1 = TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                prompt_cost=0.001,
                completion_cost=0.002,
                total_cost=0.003,
                model="test-model"
            )

            usage2 = TokenUsage(
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
                prompt_cost=0.002,
                completion_cost=0.004,
                total_cost=0.006,
                model="test-model"
            )

            base_client.add_usage(usage1)
            base_client.add_usage(usage2)

            summary = base_client.get_usage_summary()

            assert summary["total_prompt_tokens"] == 300
            assert summary["total_completion_tokens"] == 150
            assert summary["total_tokens"] == 450
            assert round(summary["total_cost"], 6) == 0.009
            assert summary["calls"] == 2
            assert len(summary["history"]) == 2

    def test_calculate_token_cost_standard(self, base_client):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50
        }

        model_pricing = {
            "input": 0.00001,
            "output": 0.00002
        }

        cost = base_client.calculate_token_cost(usage, model_pricing)

        assert cost["prompt_cost"] == 0.001
        assert cost["completion_cost"] == 0.001
        assert cost["total_cost"] == 0.002
        assert cost["cache_hit"] is False
        assert cost["cache_write"] is False

    def test_calculate_token_cost_cache_hit(self, base_client):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50
        }

        model_pricing = {
            "input": 0.00001,
            "output": 0.00002,
            "input_cache_read": 0.000005
        }

        cost = base_client.calculate_token_cost(usage, model_pricing, cache_hit=True)

        assert cost["prompt_cost"] == 0.0005
        assert cost["completion_cost"] == 0.001
        assert cost["total_cost"] == 0.0015
        assert cost["cache_hit"] is True
        assert cost["cache_write"] is False

    def test_calculate_token_cost_cache_write(self, base_client):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50
        }

        model_pricing = {
            "input": 0.00001,
            "output": 0.00002,
            "input_cache_write": 0.000015
        }

        cost = base_client.calculate_token_cost(usage, model_pricing, cache_write=True)

        assert cost["prompt_cost"] == 0.0015
        assert cost["completion_cost"] == 0.001
        assert cost["total_cost"] == 0.0025
        assert cost["cache_hit"] is False
        assert cost["cache_write"] is True

    def test_adjust_prompts(self, base_client):
        system_prompt = "System prompt"
        user_prompt = "User prompt"

        adjusted_system, adjusted_user = base_client.adjust_prompts(system_prompt, user_prompt)

        assert adjusted_system == system_prompt
        assert adjusted_user == user_prompt


if __name__ == "__main__":
    pytest.main(["-v"])
