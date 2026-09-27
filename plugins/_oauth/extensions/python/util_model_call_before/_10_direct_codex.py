from helpers.extension import Extension
from plugins._oauth.helpers.direct_codex import configure_direct_codex_model


async def _consume_stream(_chunk: str) -> None:
    return None


class DirectCodexUtility(Extension):
    def execute(self, call_data: dict, **kwargs):
        if not configure_direct_codex_model(call_data.get("model"), self.agent):
            return
        if not call_data.get("callback"):
            # Utility calls are usually collected, but Codex requires SSE.
            call_data["callback"] = _consume_stream
