import dataclasses
import inspect
import json
import logging
import os
import sys
from datetime import date, datetime

from loguru import logger
from loguru._better_exceptions import ExceptionFormatter


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame:
            filename = frame.f_code.co_filename
            is_logging = filename == logging.__file__
            is_frozen = "importlib" in filename and "_bootstrap" in filename
            if depth > 0 and not (is_logging or is_frozen):
                break
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _default_json(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {"__type": type(obj).__name__} | dataclasses.asdict(obj)

    # Write warning directly to stderr if the object could not be serialized
    # Don't use `logger` to avoid recursion since `json_log_sink` uses this function
    if os.environ.get("LOGURU_LEVEL") == "TRACE":
        warning = json.dumps(
            {
                "time": datetime.now().isoformat(),
                "level": "WARNING",
                "message": f"Cannot serialize object of type: {type(obj)}",
            }
        )
        sys.stderr.write(f"{warning}\n")

    return str(obj)


def _to_json(obj):
    return json.dumps(obj, default=_default_json, ensure_ascii=False)


_exception_formatter = ExceptionFormatter()


def json_log_sink(message):
    record = message.record
    text = _to_json(
        {
            "time": record["time"],
            "thread": f"{record['thread'].name}({record['thread'].id})",
            "level": record["level"].name,
            "name": record["name"],
            "function": record["function"],
            "message": record["message"],
        }
        | ({"context": record["extra"]} if record["extra"] else {})
        | (
            {
                "exception": {
                    "type": record["exception"].type.__name__,
                    "value": str(record["exception"].value),
                    "traceback": "\n".join(
                        _exception_formatter.format_exception(
                            record["exception"].type,
                            record["exception"].value,
                            record["exception"].traceback,
                        )
                    ),
                }
            }
            if record["exception"]
            else {}
        ),
    )
    sys.stderr.write(f"{text}\n")
