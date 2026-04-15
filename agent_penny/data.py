import functools
import json
import os
from datetime import UTC, datetime
from typing import Dict, List, Optional

from chainlit.data.base import BaseDataLayer
from chainlit.element import Element, ElementDict
from chainlit.step import StepDict
from chainlit.types import (
    Feedback,
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.user import PersistedUser, User
from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent
from typing_extensions import override

from . import user_data


def entry_point(func):
    return override(logger.catch(reraise=True)(func))


class GeneratedTitle(BaseModel):
    title: str


async def generate_title(prompt: str):
    if "TITLE_MODEL" not in os.environ:
        return prompt

    @functools.cache
    def title_generator():
        logger.debug("Creating title generator")
        return Agent(
            model=os.environ["TITLE_MODEL"],
            system_prompt="You are a title generator. Your sole task is to produce a concise title (under 10 words) that summarizes the user's text.",
            output_type=GeneratedTitle,
        )

    result = await title_generator().run(prompt)
    return result.output.title


class LocalDataLayer(BaseDataLayer):
    def __init__(self):
        threads_dir = user_data.data_dir / "threads"
        threads_dir.mkdir(exist_ok=True)

        self.threads_dir = threads_dir

    @entry_point
    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        # Do not load persisted user to avoid persisting metadata
        # Chainlit will fall back to `create_user` and provide the authenticated user's metadata
        return None

    @entry_point
    async def create_user(self, user: User) -> Optional[PersistedUser]:
        user_file = user_data._user_path(user.identifier, "user.json")

        if user_file.exists():
            persisted_user = PersistedUser.from_json(user_file.read_text())
        else:
            # Persist user attributes, but NOT metadata which contains sensitive credentials
            persisted_user = PersistedUser(
                id=user.identifier,
                createdAt=datetime.now().isoformat(),
                identifier=user.identifier,
                display_name=user.display_name,
            )

            user_file.write_text(persisted_user.to_json())

        # Override the user's metadata with the metadata from the authenticated user
        persisted_user.metadata = user.metadata
        return persisted_user

    @entry_point
    async def delete_feedback(self, feedback_id: str) -> bool:
        raise NotImplementedError("delete_feedback")

    @entry_point
    async def upsert_feedback(self, feedback: Feedback) -> str:
        raise NotImplementedError("upsert_feedback")

    @entry_point
    async def create_element(self, element: Element):
        raise NotImplementedError("create_element")

    @entry_point
    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional[ElementDict]:
        raise NotImplementedError("get_element")

    @entry_point
    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        raise NotImplementedError("delete_element")

    def load_thread(self, thread_id: str) -> ThreadDict:
        data_file = self.threads_dir / f"{thread_id}.json"
        if data_file.exists():
            with open(data_file) as f:
                return json.load(f)
        else:
            return {
                "id": thread_id,
                "steps": [],
                "createdAt": datetime.now(UTC).isoformat(),
            }  # type: ignore[typeddict-item,ty:missing-typed-dict-key,ty:invalid-return-type]

    def save_thread(self, thread: ThreadDict):
        data_file = self.threads_dir / f"{thread['id']}.json"
        with open(data_file, "w") as f:
            json.dump(thread, f)

    @entry_point
    async def create_step(self, step_dict: StepDict):
        logger.debug(
            "Create step",
            step_dict={"id": step_dict["id"], "threadId": step_dict["threadId"]},
        )

        thread = self.load_thread(step_dict["threadId"])

        thread["steps"].append(step_dict)

        self.save_thread(thread)

    @entry_point
    async def update_step(self, step_dict: StepDict):
        logger.debug(
            "Update step",
            step_dict={"id": step_dict["id"], "threadId": step_dict["threadId"]},
        )

        thread = self.load_thread(step_dict["threadId"])

        for i, step in enumerate(thread["steps"]):
            if step["id"] == step_dict["id"]:
                thread["steps"][i] = step_dict
                break

        self.save_thread(thread)

    @entry_point
    async def delete_step(self, step_id: str):
        logger.debug("Delete step", step_id=step_id)
        for f in self.threads_dir.glob("*.json"):
            thread: ThreadDict = json.loads(f.read_text())
            if steps := thread.get("steps"):
                if any(s["id"] == step_id for s in steps):
                    thread["steps"] = [s for s in steps if s["id"] != step_id]
                    self.save_thread(thread)

    @entry_point
    async def get_thread_author(self, thread_id: str) -> str:
        logger.debug("Get thread author", thread_id=thread_id)
        user_id = self.load_thread(thread_id)["userId"]
        assert user_id
        return user_id

    @entry_point
    async def delete_thread(self, thread_id: str):
        logger.debug("Delete thread", thread_id=thread_id)
        (self.threads_dir / f"{thread_id}.json").unlink()

    @entry_point
    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        logger.debug("List threads", filters=filters)

        assert filters.userId
        user_id = filters.userId

        threads: list[ThreadDict] = [
            json.loads(f.read_text()) for f in self.threads_dir.glob("*.json")
        ]
        threads = [t for t in threads if t.get("name") is not None]
        threads = [t for t in threads if t.get("userId") == user_id]
        if filters.search:
            threads = [
                t
                for t in threads
                if filters.search.lower() in t["name"].lower()  # type: ignore[union-attr,ty:unresolved-attribute]
            ]

        return PaginatedResponse(
            pageInfo=PageInfo(
                hasNextPage=False,
                startCursor=None,
                endCursor=None,
            ),
            data=threads,
        )

    @entry_point
    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        return self.load_thread(thread_id)

    @entry_point
    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        args = {
            k: v
            for k, v in {
                "name": name,
                "userId": user_id,
                "metadata": metadata,
                "tags": tags,
            }.items()
            if v is not None
        }

        logger.debug("Update thread", thread_id=thread_id, **args)

        if name:
            name = await generate_title(name)

        thread = self.load_thread(thread_id)

        if name:
            thread["name"] = name

        if user_id:
            thread["userId"] = user_id

            # userIdentifier is needed for making chats resumable
            thread["userIdentifier"] = user_id

        if metadata:
            thread["metadata"] = metadata

        if tags:
            thread["tags"] = tags

        self.save_thread(thread)

    @entry_point
    async def build_debug_url(self) -> str:
        raise NotImplementedError("build_debug_url")

    @entry_point
    async def close(self) -> None:
        logger.debug("Close")
        # TODO: Clean up empty or old threads

    @entry_point
    async def get_favorite_steps(self, user_id: str) -> List[StepDict]:
        raise NotImplementedError("get_favorite_steps")
