from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from textwrap import dedent, shorten
from typing import Any, override

import chainlit as cl
import yaml
from chainlit.context import ChainlitContextException
from loguru import logger
from pydantic import BaseModel, ConfigDict
from pydantic_ai import ModelRetry, RunContext, Tool
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset
from pydantic_ai_skills.directory import parse_skill_md

from agent_penny import user_data
from agent_penny.exceptions import SecurityError


class SkillDefinition(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str
    """
    The name of the skill.
    Max 64 characters. Lowercase letters, numbers, and hyphens only. Must not start or end with a hyphen.
    """

    description: str | None = None
    """Max 1024 characters. Non-empty. Describes what the skill does and when to use it."""

    license: str | None = None
    """License name or reference to a bundled license file."""

    compatibility: str | None = None
    """Max 500 characters. Indicates environment requirements (intended product, system packages, network access, etc.)."""

    metadata: dict[str, Any] | None = None
    """Arbitrary key-value mapping for additional metadata."""


class SkillCatalog(BaseModel):
    available_skills: list[SkillDefinition]


class SkillContent(SkillDefinition):
    model_config = ConfigDict(use_attribute_docstrings=True)

    content: str


@dataclass(init=False)
class SkillsCapability(AbstractCapability[Any]):
    def __init__(self, skills_path: str | Path | None = None):
        super().__init__()
        self.skills_path = (
            Path(skills_path) if skills_path else user_data.path("skills")
        )
        self.update_chainlit_commands()

    def update_chainlit_commands(self):
        # TODO: Try to decouple the capability from Chainlit to make it reusable
        try:
            loop = cl.context.loop
        except ChainlitContextException as e:
            logger.debug("Chainlit isn't running", e)
            return None

        skill_catalog = self.list_skills()

        if loop:
            loop.create_task(
                cl.context.emitter.set_commands(
                    [
                        {
                            "id": skill.name,
                            "icon": "scroll",
                            "description": shorten(
                                skill.description or skill.name, 125, placeholder="..."
                            ),
                            "button": False,
                            "persistent": True,
                        }
                        for skill in skill_catalog.available_skills
                    ]
                )
            )

    @override
    def get_instructions(self):
        async def _get_instructions(ctx: RunContext[Any]) -> str | None:
            # TODO: Consider caching the instructions since this is invoked at every agent turn
            if (
                ctx.metadata
                and (skill_name := ctx.metadata.get("skill_name"))
                and self.resolve_skill_path(skill_name).exists()
            ):
                skill = self.activate_skill(skill_name)

                return dedent("""\
                    The following skill is loaded and ready to guide you.

                    """) + skill.model_dump_json(indent=2, exclude_none=True)
            else:
                skill_catalog = self.list_skills()

                if not skill_catalog.available_skills:
                    return None

                return dedent("""\
                    The following skills provide specialized instructions for specific tasks.
                    When a task matches a skill's description, call the activate_skill tool
                    with the skill's name to load its full instructions.

                    """) + skill_catalog.model_dump_json(indent=2, exclude_none=True)

        return _get_instructions

    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return FunctionToolset(
            [
                Tool(self.list_skills),
                Tool(self.activate_skill),
                Tool(self.create_skill),
                Tool(self.update_skill),
                Tool(self.delete_skill),
            ]
        )

    def list_skills(self) -> SkillCatalog:
        """See [Step 3: Disclose available skills to the model](https://agentskills.io/client-implementation/adding-skills-support#step-3-disclose-available-skills-to-the-model)"""

        if not self.skills_path.exists():
            return SkillCatalog(available_skills=[])

        available_skills = [
            SkillDefinition(
                name=frontmatter_dict.get("name") or p.name,
                description=frontmatter_dict.get("description"),
            )
            for p in self.skills_path.iterdir()
            if p.is_dir() and (p / "SKILL.md").exists()
            for frontmatter_dict, instructions_markdown in [
                parse_skill_md((p / "SKILL.md").read_text())
            ]
        ]

        return SkillCatalog(available_skills=available_skills)

    def resolve_skill_path(self, name: str):
        if not name or "/" in name:
            raise SecurityError(f"Path traversal attempted for skill: {name}")

        skill_path = self.skills_path / name / "SKILL.md"

        if self.skills_path.resolve() not in skill_path.resolve().parents:
            raise SecurityError(f"Path traversal attempted for skill: {name}")

        return skill_path.resolve()

    def resolve_skill(self, name: str, should_exist: bool) -> Path:
        skill_path = self.resolve_skill_path(name)

        if should_exist and not skill_path.exists():
            raise ModelRetry(f"Skill does not exist: {name}")

        if not should_exist and skill_path.exists():
            raise ModelRetry(f"Skill already exists: {name}")

        return skill_path

    def activate_skill(self, name: str) -> SkillContent:
        skill_path = self.resolve_skill(name, True)

        skill_text = skill_path.read_text()

        frontmatter_dict, instructions_markdown = parse_skill_md(skill_text)

        return SkillContent.model_validate(
            {
                "name": frontmatter_dict.get("name") or name,
                "description": frontmatter_dict.get("description"),
                **frontmatter_dict,
                "content": instructions_markdown,
            }
        )

    def skill_content_to_txt(self, skill: SkillContent) -> str:
        skill_txt = StringIO()
        skill_txt.write("---\n")
        yaml.safe_dump(
            {
                k: v
                for k, v in skill.model_dump(exclude_none=True).items()
                if k != "content"
            },
            skill_txt,
            sort_keys=False,
        )
        skill_txt.write("---\n")
        skill_txt.write(skill.content)
        return skill_txt.getvalue()

    def create_skill(self, skill: SkillContent) -> None:
        """
        Args:
            skill: Skill information to update
        """
        skill_path = self.resolve_skill(skill.name, False)

        if not skill_path.parent.exists():
            skill_path.parent.mkdir(parents=True)

        skill_path.write_text(self.skill_content_to_txt(skill))

        self.update_chainlit_commands()

    def update_skill(self, skill: SkillContent) -> None:
        skill_path = self.resolve_skill(skill.name, True)

        skill_path.write_text(self.skill_content_to_txt(skill))

    def delete_skill(self, name: str) -> None:
        skill_path = self.resolve_skill(name, True)

        skill_path.unlink()

        self.update_chainlit_commands()
