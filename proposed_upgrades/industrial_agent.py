from backend.tasks.industrial_agent import *  # noqa: F401,F403
from backend.tasks.industrial_agent import bootstrap_demo


if __name__ == "__main__":
    import asyncio

    asyncio.run(bootstrap_demo())
