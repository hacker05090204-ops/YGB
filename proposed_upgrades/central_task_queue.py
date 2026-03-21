from backend.tasks.central_task_queue import *  # noqa: F401,F403
from backend.tasks.central_task_queue import main


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
