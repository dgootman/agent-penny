import asyncio
from dataclasses import dataclass
from datetime import datetime
from threading import Thread, current_thread
from typing import Any, Literal, override
from uuid import uuid4
from zoneinfo import ZoneInfo

import chainlit as cl
import logfire
import yaml
from apscheduler.jobstores.base import JobLookupError  # type: ignore[import-untyped]
from apscheduler.schedulers.asyncio import (  # type: ignore[import-untyped]
    AsyncIOScheduler,
)
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.date import DateTrigger  # type: ignore[import-untyped]
from chainlit.config import config
from chainlit.context import init_ws_context
from chainlit.session import WebsocketSession
from chainlit.socket import persist_user_session, process_message
from chainlit.types import MessagePayload
from loguru import logger
from pydantic import AwareDatetime, BaseModel
from pydantic_ai import (
    AgentToolset,
    FunctionToolset,
    ModelMessage,
    ModelResponse,
    ModelRetry,
)
from pydantic_ai.capabilities import AbstractCapability
from slugify import slugify

from agent_penny import user_data
from agent_penny.chainlit_utils import get_user

JobExecutionStatus = Literal["started", "finished", "failed"]


class JobExecution(BaseModel):
    start: AwareDatetime
    end: AwareDatetime | None = None
    status: JobExecutionStatus = "started"
    result: str | None = None

    @staticmethod
    def create(job: "ScheduledJob"):
        return JobExecution(start=datetime.now(ZoneInfo(job.timezone)))

    def finish(self, status: JobExecutionStatus, result: str | Exception):
        self.end = datetime.now(self.start.tzinfo)
        self.status = status
        self.result = str(result)


class ScheduledJob(BaseModel, use_attribute_docstrings=True):  # type: ignore[call-arg]
    name: str
    prompt: str
    """
    The task prompt to send the agent when the job runs.
    Phrase it as the work to perform, not as a request to schedule that work.
    """

    cron_expression: str | None = None
    date: AwareDatetime | None = None
    timezone: str
    last_execution: JobExecution | None = None


def _jobs_path():
    return user_data.path("jobs")


def _job_file_path(job_name: str):
    return _jobs_path() / f"{slugify(job_name)}.yaml"


def _load_job(job_name: str):
    return ScheduledJob.model_validate(
        yaml.safe_load(_job_file_path(job_name).read_text())
    )


def _save_job(job: ScheduledJob):
    return _job_file_path(job.name).write_text(
        yaml.safe_dump(job.model_dump(exclude_none=True), sort_keys=False)
    )


_scheduler = AsyncIOScheduler()
_threads: set[Thread] = set()


@logfire.instrument()
async def emit(event: str, data: Any) -> None:
    pass


@logfire.instrument()
async def emit_call(
    event: Literal["ask", "call_fn"], data: Any, timeout: int | None
) -> None:
    pass


@logfire.instrument(new_trace=True)
async def run(user_id: str, job_name: str):
    logger.debug("Running job", job_name=job_name)

    # HACK: Scheduling has an implicit dependency on user persistence in the data layer
    user = cl.PersistedUser.from_json(
        user_data._user_path(user_id, "user.json").read_text()
    )

    session = WebsocketSession(
        id=str(uuid4()),
        socket_id=str(uuid4()),
        emit=emit,  # type: ignore[ty:invalid-argument-type, arg-type]
        emit_call=emit_call,
        user_env={},
        client_type="webapp",
        user=user,
    )

    init_ws_context(session)

    job = _load_job(job_name)

    execution = JobExecution.create(job)

    try:
        if config.code.on_chat_start:
            await config.code.on_chat_start()

        payload: MessagePayload = {
            "message": {
                "id": str(uuid4()),
                "threadId": session.thread_id,
                "createdAt": datetime.now().isoformat(),
                "output": job.prompt,
                "name": user.identifier,
                "type": "user_message",
            },
            "fileReferences": None,
        }

        try:
            await process_message(session, payload)

            message_history: list[ModelMessage] = cl.user_session.get("message_history")

            if message_history:
                assert isinstance(message_history[-1], ModelResponse)
                execution.finish("finished", message_history[-1].text)
            else:
                execution.finish(
                    "failed", RuntimeError("Unknown error in job execution")
                )

            job.last_execution = execution
            _save_job(job)

            if config.code.on_chat_end:
                await config.code.on_chat_end()
        finally:
            # Wait for pending tasks to complete
            # One of those tasks will flush the final agent message to the session so it can be saved
            tasks = asyncio.all_tasks()
            tasks.discard(asyncio.current_task())  # type: ignore[arg-type]
            if tasks:
                await asyncio.gather(*tasks)

            await persist_user_session(session.thread_id, session.to_persistable())
    except Exception as e:
        # Mark the job as failed if it hadn't finished,
        # while ignoring errors that occur after job completion
        if execution.status == "started":
            execution.finish("failed", e)
            job.last_execution = execution
            _save_job(job)
        raise e


def _thread(user_id, job_name):
    _threads.add(current_thread())
    try:
        asyncio.new_event_loop().run_until_complete(run(user_id, job_name))
    finally:
        _threads.remove(current_thread())


async def _launch(user_id: str, job_name: str):
    Thread(target=_thread, name="Scheduler", args=[user_id, job_name]).start()


def _add_job(user_id: str, job: ScheduledJob):
    job_id = slugify(f"{user_id} {job.name}")
    _scheduler.add_job(
        _launch,
        CronTrigger.from_crontab(job.cron_expression, timezone=job.timezone)
        if job.cron_expression
        else DateTrigger(job.date, job.timezone),
        args=[user_id, job.name],
        name=job_id,
        id=job_id,
    )
    logger.debug(
        "Scheduled job", user_id=user_id, job=job.model_dump(exclude={"prompt"})
    )


def _remove_job(user_id: str, job_name: str):
    job_id = slugify(f"{user_id} {job_name}")
    _scheduler.remove_job(job_id)
    logger.debug("Removed job", user_id=user_id, job_name=job_name)


def startup():
    _scheduler.start()

    logger.info("Scheduler started")

    for user_dir in user_data.users_dir.iterdir():
        # HACK: Scheduling has an implicit dependency on user persistence in the data layer
        if not (user_dir / "user.json").exists():
            continue

        user_id = cl.PersistedUser.from_json(
            (user_dir / "user.json").read_text()
        ).identifier

        for job_file in user_dir.glob("jobs/*.yaml"):
            job = ScheduledJob.model_validate(yaml.safe_load(job_file.read_text()))
            _add_job(user_id, job)


toolset = FunctionToolset()


@toolset.tool_plain()
def list_jobs() -> list[ScheduledJob]:
    return [_load_job(p.stem) for p in _jobs_path().glob("*.yaml")]


@toolset.tool_plain()
def load_job(job_name: str) -> ScheduledJob:
    return _load_job(job_name)


@toolset.tool_plain()
def upsert_job(job: ScheduledJob):
    """
    Create or update an existing scheduled job.
    The job will run periodically if a cron expression is provided or just once if a specific date is specified.
    """
    if job.cron_expression and job.date:
        raise ModelRetry("Cron expression and date can't be specified at the same time")

    # If the job already exists, preserve the last execution status
    if _job_file_path(job.name).exists():
        job.last_execution = _load_job(job.name).last_execution

    _save_job(job)

    job_id = slugify(f"{get_user().identifier} {job.name}")

    try:
        _scheduler.remove_job(job_id)
    except JobLookupError:
        pass

    _add_job(get_user().identifier, job)


@toolset.tool_plain()
def delete_job(job_name: str):
    job_file = _job_file_path(job_name)

    if not job_file.exists():
        raise ModelRetry(f"Job was not found: {job_name}")

    job_file.unlink()

    try:
        _remove_job(get_user().identifier, job_name)
    except JobLookupError:
        pass


@dataclass
class SchedulingCapability(AbstractCapability[Any]):
    def __post_init__(self):
        jobs_path = _jobs_path()
        if not jobs_path.exists():
            jobs_path.mkdir()

    @override
    def get_toolset(self) -> AgentToolset[Any] | None:
        return toolset
