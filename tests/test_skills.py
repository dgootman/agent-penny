from pathlib import Path
from textwrap import dedent

import pytest
from loguru import logger
from pydantic_ai import (
    Agent,
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agent_penny.exceptions import SecurityError


async def call_tool(skills_path: str, tool_name: str, skill_name: str):
    from agent_penny.capabilities.skills import SkillContent, SkillsCapability

    async def model_function(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        logger.debug(messages)

        message = messages[-1]
        [part] = message.parts
        if isinstance(part, UserPromptPart):
            return ModelResponse(
                parts=[ToolCallPart(tool_name, {"name": part.content})]
            )
        elif isinstance(part, ToolReturnPart):
            return ModelResponse(parts=[TextPart(part.model_response_str())])
        else:
            raise ValueError(f"Unexpected part: {part}")

    agent = Agent(
        model=FunctionModel(model_function),
        capabilities=[SkillsCapability(skills_path)],
    )

    result = await agent.run(skill_name, output_type=SkillContent)
    assert result

    return result.output


@pytest.mark.parametrize(
    "skills_path,skill_name,description,content_starts_with",
    [
        (
            ".agents/skills",
            "code-reviewer",
            'Expertise in reviewing code for style, security, and performance. Use when the user asks for "feedback," a "review," or to "check" their changes.',
            dedent("""\
                # Code Reviewer

                You are an expert code reviewer. When reviewing code, follow this workflow:
                """),
        ),
        (
            ".agents/skills",
            "update-readme",
            "Generates or updates a README.md file based on the application's functionality. Use when the user wants to generate or update the README.md file to reflect the current state of the application.",
            dedent("""\
                # Update README

                You are an expert at analyzing a codebase and generating or updating a comprehensive `README.md` file that describes the application's functionality.

                When asked to update the README, follow this workflow:
                """),
        ),
    ],
)
@pytest.mark.asyncio
async def test_activate_skill(
    skills_path: str, skill_name: str, description: str, content_starts_with: str
):
    skill = await call_tool(skills_path, "activate_skill", skill_name)
    assert skill.name == skill_name
    assert skill.description == description
    assert skill.content.startswith(content_starts_with)


@pytest.mark.parametrize(
    "skill_name",
    [
        ("../../etc/passwd"),
        ("../skill-creator"),
        ("skill-creator/../../etc/passwd"),
        ("skill-creator/../../../tmp/evil"),
        ("nested/../another/../../etc/shadow"),
        ("./../skill-creator"),
        ("/etc/passwd"),
        ("/tmp/../etc/passwd"),
    ],
)
def test_path_traversal(skill_name: str, tmpdir: Path):
    from agent_penny.capabilities.skills import SkillContent, SkillsCapability

    capability = SkillsCapability(tmpdir)

    with pytest.raises(SecurityError):
        capability.activate_skill(skill_name)

    with pytest.raises(SecurityError):
        capability.create_skill(
            SkillContent(name=skill_name, content="Hack the world!")
        )

    with pytest.raises(SecurityError):
        capability.update_skill(
            SkillContent(name=skill_name, content="Hack the world!")
        )


def test_skill_lifecycle(tmpdir: Path):
    from agent_penny.capabilities.skills import SkillContent, SkillsCapability

    capabilities = SkillsCapability(tmpdir)

    catalog = capabilities.list_skills()
    assert len(catalog.available_skills) == 0

    test_skill_content = dedent("""\
        # Test Skill

        This is a simple test skill.

        When activated:
        - Confirm the skill loaded successfully.
        - Reply with a short acknowledgement.
        - Do not perform any external actions.
        """).strip()

    capabilities.create_skill(
        SkillContent(
            name="test-skill",
            description="Testing skill lifecycle",
            content=test_skill_content,
        )
    )

    assert (tmpdir / "test-skill" / "SKILL.md").exists()

    skill_txt = (tmpdir / "test-skill" / "SKILL.md").read_text("utf-8")
    assert skill_txt == (
        dedent("""\
            ---
            name: test-skill
            description: Testing skill lifecycle
            ---
            """)
        + test_skill_content
    )

    catalog = capabilities.list_skills()
    assert len(catalog.available_skills) == 1
    [skill_definition] = catalog.available_skills
    assert skill_definition.name == "test-skill"
    assert skill_definition.description == "Testing skill lifecycle"

    skill = capabilities.activate_skill("test-skill")
    assert skill.name == "test-skill"
    assert skill.description == "Testing skill lifecycle"
    assert skill.content == test_skill_content

    capabilities.update_skill(
        SkillContent(
            name="test-skill",
            description="Lifecycle testing skill",
            license="Apache-2.0",
            metadata={"author": "dgootman", "version": "1.0"},
            content="Yes, we're still testing",
        )
    )

    skill_txt = (tmpdir / "test-skill" / "SKILL.md").read_text("utf-8")
    assert skill_txt == (
        dedent("""\
            ---
            name: test-skill
            description: Lifecycle testing skill
            license: Apache-2.0
            metadata:
              author: dgootman
              version: '1.0'
            ---
            Yes, we're still testing
            """).strip()
    )

    skill = capabilities.activate_skill("test-skill")
    assert skill.name == "test-skill"
    assert skill.description == "Lifecycle testing skill"
    assert skill.content == "Yes, we're still testing"

    capabilities.delete_skill("test-skill")

    assert not (tmpdir / "test-skill" / "SKILL.md").exists()

    catalog = capabilities.list_skills()
    assert len(catalog.available_skills) == 0
