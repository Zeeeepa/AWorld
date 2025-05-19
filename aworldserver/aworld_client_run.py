# Initialize AworldTaskClient with server endpoints
import asyncio
import uuid

from aworld_client import AworldTask, AworldTaskClient

AWORLD_TASK_CLIENT = AworldTaskClient(
    know_hosts=["localhost:9299", "localhost:9399", "localhost:9499"]
)


async def _run_gaia_task(gaia_question_id: str) -> None:
    """Run a single Gaia task with the given question ID.

    Args:
        gaia_question_id: The ID of the question to process
    """
    global AWORLD_TASK_CLIENT
    task_id = str(uuid.uuid4())

    # Submit task to Aworld server
    await AWORLD_TASK_CLIENT.submit_task(
        AworldTask(
            task_id=task_id,
            agent_id="gaia_agent",
            agent_input=gaia_question_id,
            session_id="session_id",
            user_id="SYSTEM"
        )
    )

    # Get and print task result
    task_result = await AWORLD_TASK_CLIENT.get_task_state(task_id=task_id)
    print(task_result)


async def _batch_run_gaia_task(start_i: int, end_i: int) -> None:
    """Run multiple Gaia tasks in parallel.

    Args:
        start_i: Starting question ID
        end_i: Ending question ID
    """
    tasks = [
        _run_gaia_task(str(i))
        for i in range(start_i, end_i + 1)
    ]
    await asyncio.gather(*tasks)


if __name__ == '__main__':
    # Run batch processing for questions 1-5
    asyncio.run(_batch_run_gaia_task(1, 5))