import asyncio
import pytest
from Core.agent import AutonomousAgent

class DummyLLM:
    async def generate_response(self, conversation_history):

        response = {
            "thinking": "I am thinking about the task.",
            "analysis": "Analyzing the conversation.",
            "tool_calls": [],
            "answer": "This is the final answer."
        }
        return response

    def adjust_prompts(self, system_prompt, user_prompt):
        return system_prompt, user_prompt

@pytest.mark.asyncio
class TestAutonomousAgent:
    async def test_run_agent_simple(self):

        agent = AutonomousAgent(api_key="dummy", model="dummy-model", provider="openai", test_mode=True)
        agent.llm = DummyLLM()

        async def fake_input():
            return "exit"
        agent._get_user_input = fake_input

        await agent.run(initial_prompt="Test prompt", system_prompt="System instructions")

        answers = [msg["content"] for msg in agent.local_conversation_history if msg["role"] == "assistant"]
        assert any("This is the final answer." in answer for answer in answers)
