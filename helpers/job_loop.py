import asyncio
from datetime import datetime
import time
from helpers.task_scheduler import TaskScheduler
from helpers.print_style import PrintStyle
from helpers import errors
from helpers import runtime, rfc


SLEEP_TIME = 60

keep_running = True
pause_time = 0


async def run_loop():
    while True:
        await run_iteration()
        await asyncio.sleep(SLEEP_TIME)


async def run_iteration():
    global pause_time, keep_running
    if runtime.is_development():
        # Pause a reachable container scheduler, never this native process.
        try:
            await runtime.call_remote_development_function(pause_loop)
        except rfc.RFCUnavailableError:
            # Native/local deployment: there is no container scheduler to
            # pause. Local fallback here would disable our own job loop.
            pass
        except Exception as e:
            PrintStyle().error("Failed to pause job loop by development instance: " + errors.error_text(e))
            # An ambiguous/remote error may leave that scheduler running;
            # do not execute duplicate local scheduled work this iteration.
            return
    if not keep_running and (time.time() - pause_time) > (SLEEP_TIME * 2):
        resume_loop()
    if keep_running:
        try:
            await scheduler_tick()
        except Exception as e:
            PrintStyle().error(errors.format_error(e))


async def scheduler_tick():
    # Get the task scheduler instance and print detailed debug info
    scheduler = TaskScheduler.get()
    # Run the scheduler tick
    await scheduler.tick()

    # Run job_loop extensions (e.g. email polling)
    from helpers.extension import call_extensions_async
    await call_extensions_async("job_loop")


def pause_loop():
    global keep_running, pause_time
    keep_running = False
    pause_time = time.time()


def resume_loop():
    global keep_running, pause_time
    keep_running = True
    pause_time = 0
