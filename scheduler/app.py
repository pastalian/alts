import logging
import time
import traceback
import typing
import uuid
from datetime import datetime, timedelta

from celery.result import AsyncResult
from celery.states import READY_STATES
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator, ValidationError

from alts.tasks import run_docker
from scheduler.db import database, Session, Task
from shared import RUNNER_MAPPING


class Repository(BaseModel):
    name: typing.Optional[str] = None
    baseurl = str


class TaskRequestPayload(BaseModel):
    runner_type: str
    dist_name: str
    dist_version: typing.Union[str, int]
    dist_arch: str
    repositories: typing.List[Repository] = []
    package_name: str
    package_version: typing.Optional[str] = None

    @validator('runner_type')
    def validate_runner_type(cls, value: str) -> str:
        # TODO: Add config or constant to have all possible runner types
        if value not in ('any', 'docker'):
            raise ValidationError(f'Unknown runner type: {value}')
        return value


class TaskRequestResponse(BaseModel):
    success: bool
    error_description: typing.Optional[str] = None
    task_id: typing.Optional[str] = None


# TODO: Fix the issue with DisabledBackend for Celery
def check_celery_task_result(task_id: str, timeout=100):
    task_status = 'NEW'
    later = datetime.now() + timedelta(seconds=timeout)
    session = Session()
    while task_status not in READY_STATES and datetime.now() <= later:
        try:
            task_result = AsyncResult(task_id)
            task_status = task_result.state
        except Exception as e:
            logging.error(f'Cannot fetch task result for task ID {task_id}:'
                          f' {e}')
        try:
            task_record = (session.query(Task).filter(Task.task_id == task_id)
                           .first())
            if task_record != task_status:
                task_record.status = task_status
                session.add(task_record)
                session.commit()
        except Exception as e:
            logging.error(f'Cannot update task DB record: {e}')
        time.sleep(30)


app = FastAPI()

# TODO: Fix the issue with DisabledBackend for Celery
# @app.on_event('startup')
# async def startup():
#     await database.connect()
#
#     session = Session()
#     inspect_instance = celery_app.control.inspect()
#     for _, tasks in inspect_instance.active(safe=True).items():
#         # TODO: Add query to database and update tasks
#         pass
#     try:
#         for task in (session.query(Task.task_id, Task.status)
#                      .filter(Task.status == 'STARTED')):
#             task_result = AsyncResult(task.task_id)
#             task.status = task_result.state
#             session.add(task)
#         session.commit()
#     except Exception as e:
#         logging.error(f'Cannot save task info: {e}')
#         session.rollback()

# TODO: Fix the issue with DisabledBackend for Celery
# @app.on_event("shutdown")
# async def shutdown():
#     await database.disconnect()


@app.post('/schedule-task', response_model=TaskRequestResponse,
          responses={
              201: {'model': TaskRequestResponse},
              400: {'model': TaskRequestResponse},
          })
async def schedule_task(task_data: TaskRequestPayload) -> JSONResponse:
    runner_type = task_data.runner_type
    if runner_type == 'any':
        runner_type = 'docker'
    print(f'Runner type: {runner_type}')
    runner_class = RUNNER_MAPPING[runner_type]

    if task_data.dist_arch not in runner_class.SUPPORTED_ARCHITECTURES:
        raise ValidationError(f'Unknown architecture: {task_data.dist_arch}')
    if task_data.dist_name not in runner_class.SUPPORTED_DISTRIBUTIONS:
        raise ValidationError(f'Unknown distribution: {task_data.dist_name}')

    # TODO: Make decision on what queue to use for particular task based on
    #  queues load
    queue_arch = None
    for arch, supported_arches in runner_class.ARCHITECTURES_MAPPING.items():
        if task_data.dist_arch in supported_arches:
            queue_arch = arch

    if not queue_arch:
        raise ValidationError('Cannot map requested architecture to any '
                              'host architecture, possible coding error')

    queue_name = f'{runner_type}-{queue_arch}-{runner_class.COST}'
    task_id = str(uuid.uuid4())
    try:
        run_docker.apply_async(
            (task_id, runner_type, task_data.dist_name, task_data.dist_version,
             task_data.repositories, task_data.package_name,
             task_data.package_version), task_id=task_id, queue=queue_name)
        # background.add_task(check_celery_task_result, task_id)
    except Exception as e:
        logging.error(f'Cannot launch the task: {e}')
        logging.error(traceback.format_exc())
        return JSONResponse(
            content={'success': False, 'error_description': str(e)},
            status_code=400
        )
    return JSONResponse(content={'success': True, 'task_id': task_id},
                        status_code=201)
    # else:
    #     session = Session()
    #     try:
    #         task_record = Task(task_id=task_id, queue_name=queue_name,
    #                            status='NEW')
    #         session.add(task_record)
    #         session.commit()
    #         return {'task_id': task_id}
    #     except Exception as e:
    #         logging.error(f'Cannot save task data into DB: {e}')
    #         session.rollback()

