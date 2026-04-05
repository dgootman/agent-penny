import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, override

import chainlit as cl
from pydantic_ai import ModelRetry
from pydantic_ai._run_context import AgentDepsT, RunContext
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.wrapper import WrapperToolset


@dataclass
class ApprovalRequiredToolset(WrapperToolset[AgentDepsT]):
    """A toolset that requires (some) calls to tools it contains to be approved.

    Adapted the Pydantic AI [ApprovalRequiredToolset](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/toolsets/approval_required.py)
    to use Chainlit's [AskActionMessage](https://docs.chainlit.io/api-reference/ask/ask-for-action) prompts.
    """

    approval_required_func: Callable[
        [RunContext[AgentDepsT], ToolDefinition, dict[str, Any]], bool
    ] = lambda ctx, tool_def, tool_args: True

    @override
    async def get_tools(
        self, ctx: RunContext[AgentDepsT]
    ) -> dict[str, ToolsetTool[AgentDepsT]]:
        # Return the list of wrapped tools, but require sequential execution
        # TODO: Debug and fix Chainlit issue with concurrent approvals, then remove the sequential requirement
        return {
            name: replace(tool, tool_def=replace(tool.tool_def, sequential=True))
            for name, tool in (await super().get_tools(ctx)).items()
        }

    @override
    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[AgentDepsT],
        tool: ToolsetTool[AgentDepsT],
    ) -> Any:
        if self.approval_required_func(ctx, tool.tool_def, tool_args):
            try:
                res = await cl.AskActionMessage(
                    content=(
                        f"Allow Agent Penny to run `{name}`?\n\n"
                        f"```json\n{json.dumps(tool_args, default=str, indent=2)}\n```"
                    ),
                    actions=[
                        cl.Action(name="allow", payload={}, label="✅ Allow"),
                        cl.Action(name="cancel", payload={}, label="❌ Cancel"),
                    ],
                    raise_on_timeout=True,
                ).send()

                if not res or res["name"] != "allow":
                    raise ModelRetry("User cancelled")
            except TimeoutError as e:
                raise ModelRetry("Timed out") from e

        return await super().call_tool(name, tool_args, ctx, tool)
