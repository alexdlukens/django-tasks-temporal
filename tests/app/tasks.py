from django.tasks import task


@task()
def add(a: int, b: int) -> int:
    return a + b


@task()
def boom(message: str) -> None:
    raise ValueError(message)


@task(takes_context=True)
def result_id(context) -> str:
    return context.task_result.id


@task(backend="scheduled")
def scheduled_tick() -> str:
    return "tick"
