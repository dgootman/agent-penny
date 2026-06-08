from dataclasses import dataclass
from pathlib import Path
from typing import Any, override

from pydantic_ai import AgentToolset, FunctionToolset, RunContext, Tool
from pydantic_ai.capabilities import AbstractCapability

import agent_penny.user_data as user_data


@dataclass()
class MemoryCapability(AbstractCapability[Any]):
    memory_file: Path

    def __init__(self):
        self.memory_file = user_data.path("memories.txt")

        if not self.memory_file.exists():
            self.memory_file.write_text("")

    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return FunctionToolset(
            [
                Tool(self.load_memory),
                Tool(self.save_memory),
            ]
        )

    @override
    def get_instructions(self):
        async def _get_instructions(ctx: RunContext[Any]) -> str | None:
            memory = self.load_memory()

            if not memory:
                return None

            return f"You remember the following from previous conversations: {memory}"

        return _get_instructions

    def load_memory(self):
        """Load the agent's persistent memory of key details from past conversations."""

        return self.memory_file.read_text()

    def save_memory(self, memory: str):
        """
        Persist long-term agent memory that may affect future conversations.

        Workflow:
        - Always call `load_memory` first.
        - Merge existing memory with new information.
        - Resolve conflicts and remove outdated details.
        - Call `save_memory` with the full merged memory.

        Guidelines:
        - Retain all relevant information.
        - This overwrites prior memory; never save partial updates.
        - Keep memory accurate, consistent, and concise.
        """

        self.memory_file.write_text(memory)
