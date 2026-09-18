import logging
import sched
import time

from fastapi import APIRouter, BackgroundTasks

from infrastructure.entrypoint.api.router.logging.model.request_model import (
    LogRequest,
)
from infrastructure.entrypoint.api.router.logging.model.response_model import (
    LogGroupResponse,
    LogNameResponse,
    LogResponse,
)

log = logging.getLogger(__name__)

loggers_router = APIRouter(
    prefix="/loggers",
    tags=["loggers"],
    responses={404: {"description": "Not found"}},
)


@loggers_router.get(
    "/",
    tags=["loggers"],
    status_code=200,
    responses={200: {"answer": "answer response"}},
)
def get_loggers():
    loggers = {}
    loggers_groups = {}
    for name, logger in logging.root.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            loggers[name] = LogNameResponse(
                configuredLevel=logging.getLevelName(logger.level),
                effectiveLevel=logging.getLevelName(logger.getEffectiveLevel()),
            )

            if loggers_groups.get(logger.parent.name) is None:
                loggers_groups[logger.parent.name] = LogGroupResponse(
                    configuredLevel=logging.getLevelName(logger.level),
                    members=[
                        handler.name
                        for handler in logger.handlers
                        if handler.name is not None
                    ],
                )
            else:
                loggers_group = loggers_groups.get(logger.parent.name)
                loggers_group.members.append(logger.name)

    log_response = LogResponse(
        levels=logging.getLevelNamesMapping().keys(),
        loggers=loggers,
        groups=loggers_groups,
    )
    return log_response


@loggers_router.get("/names/{logger_name}")
def get_loggers_by_names(logger_name: str):
    logger = logging.root.manager.loggerDict.get(logger_name)

    log_response = LogNameResponse(
        configuredLevel=logging.getLevelName(logger.level),
        effectiveLevel=logging.getLevelName(logger.getEffectiveLevel()),
    )
    return log_response


@loggers_router.post("/names/{logger_name}", tags=["loggers"], status_code=200)
def post_loggers_by_names(
    logger_name: str,
    log_request: LogRequest,
    background_tasks: BackgroundTasks,
):
    logger_modified: list[dict] = []
    logger = logging.root.manager.loggerDict.get(logger_name)
    if logger is not None:
        logger_modified.append({"logger_name": logger.name, "log_level": logger.level})
        logger.setLevel(log_request.configuredLevel.value)
        log.info(f"logger found and modified time: {log_request.duration}")
        background_tasks.add_task(
            run_task,
            logger_modified=logger_modified,
            duration=log_request.duration,
        )


@loggers_router.get("/groups/{logger_group}", tags=["loggers"], status_code=200)
def get_loggers_by_groups(logger_group: str):
    loggers_group = None
    print(logging.root.manager.loggerDict.items())
    for name, logger in logging.root.manager.loggerDict.items():
        if isinstance(logger, logging.Logger) and logger_group == logger.parent.name:
            if loggers_group is None:
                loggers_group = LogGroupResponse(
                    configuredLevel=logging.getLevelName(logger.level),
                    members=[
                        handler.name
                        for handler in logger.handlers
                        if handler.name is not None
                    ],
                )
            else:
                loggers_group.members.append(logger.name)

    return loggers_group


@loggers_router.post("/groups/{logger_group}", tags=["loggers"], status_code=200)
def post_loggers_by_groups(
    logger_group: str,
    log_request: LogRequest,
    background_tasks: BackgroundTasks,
):
    logger_modified: list[dict] = []
    for name, logger in logging.root.manager.loggerDict.items():
        if isinstance(logger, logging.Logger) and logger_group == logger.parent.name:
            logger_modified.append(
                {"logger_name": logger.name, "log_level": logger.level}
            )
            logger.setLevel(log_request.configuredLevel.value)
    if logger_modified:
        background_tasks.add_task(
            run_task,
            logger_modified=logger_modified,
            duration=log_request.duration,
        )
        log.info(f"logger found and modified time: {log_request.duration}")


def run_task(logger_modified: list[dict], duration: int):
    log.info(f"Background task started for {duration} seconds")
    s = sched.scheduler(time.time, time.sleep)
    s.enter(duration, 1, task_return_logger_level, argument=(logger_modified,))
    s.run()


def task_return_logger_level(logger_modified: list[dict]):
    log.info(f"Return loggers: {logger_modified} to original level")
    for logger in logger_modified:
        logging.root.manager.loggerDict.get(logger.get("logger_name")).setLevel(
            logger.get("log_level")
        )
