from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class AgentConfiguration:
    """Holds the static configuration for an agent."""
    agent_id: str
    role: str
    model_provider: str
    model_name: str
    system_prompt: str # For now, the full prompt string
    allowed_tools: List[str] = field(default_factory=list) # List of tool names
    # Later: knowledge_base_ref, initial_memory, etc.

    def __post_init__(self):
        # Basic validation
        if not self.agent_id or not self.role or not self.model_provider or not self.model_name:
            raise ValueError("AgentConfiguration missing required fields (id, role, provider, model)")
        # Ensure allowed_tools is a list, even if empty
        if self.allowed_tools is None:
             self.allowed_tools = []
