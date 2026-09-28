import asyncio
import re

from helpers.extension import Extension
from helpers.print_style import PrintStyle
from helpers import errors

from helpers.errors import HandledException


def provider_usage_limit_message(exception: BaseException) -> str | None:
    """Render a bounded actionable message for a terminal Codex allowance error."""
    text = str(exception)
    if "usage_limit_reached" not in text.lower():
        return None
    plan = re.search(r'["\']plan_type["\']\s*:\s*["\']([^"\']+)', text, re.I)
    remaining = re.search(r'["\']resets_in_seconds["\']\s*:\s*(\d+)', text, re.I)
    detail = ""
    if remaining:
        seconds = int(remaining.group(1))
        hours, remainder = divmod(seconds, 3600)
        minutes = (remainder + 59) // 60
        detail = f" The provider reports a reset in about {hours}h {minutes}m."
    plan_text = f" for the {plan.group(1)} plan" if plan else ""
    return (f"OpenAI Codex usage limit reached{plan_text}.{detail} "
            "Agent Zero did not retry because the allowance cannot recover before its provider reset. "
            "Use an available credit/reset or wait until the displayed reset time, then retry the message.")


class HandleCriticalException(Extension):
    async def execute(self, data: dict = {}, **kwargs):
        if not self.agent:
            return

        if not (exception:= data.get("exception")):
            return

        # when exception is HandledException, keep it active, no logging here
        if isinstance(exception, HandledException):
            return 

        # asyncio cancel - chat is being terminated, print out and re-raise as handledException
        if isinstance(exception, asyncio.CancelledError):
            PrintStyle(font_color="white", background_color="red", padding=True).print(
                f"Context {self.agent.context.id} terminated during message loop"
            )
            data["exception"] = HandledException(exception)
            return

        # other exceptions should be logged and re-raised as HandledException
        limit_message = provider_usage_limit_message(exception)
        error_text = limit_message or errors.error_text(exception)
        error_message = limit_message or errors.format_error(exception)

        PrintStyle(font_color="red", padding=True).print(error_message)
        self.agent.context.log.log(
            type="error",
            content=error_message,
        )
        PrintStyle(font_color="red", padding=True).print(
            f"{self.agent.agent_name}: {error_text}"
        )

        data["exception"] = HandledException(exception)
