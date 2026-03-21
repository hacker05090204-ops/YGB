from backend.voice.streaming_pipeline import *  # noqa: F401,F403
from backend.voice.streaming_pipeline import main


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
