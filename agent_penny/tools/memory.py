from pydantic_ai import FunctionToolset

import agent_penny.user_data as user_data


class MemoryProvider:
    def __init__(self) -> None:
        memory_file = user_data.path("memories.txt")
        if not memory_file.exists():
            memory_file.write_text("")

        self.memory_file = memory_file
        self.toolset = FunctionToolset(
            [
                self.load_memory,
                self.save_memory,
            ]
        )

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
