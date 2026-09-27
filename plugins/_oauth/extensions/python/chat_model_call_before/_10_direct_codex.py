from helpers.extension import Extension
from plugins._oauth.helpers.direct_codex import configure_direct_codex_model


async def _consume_stream(_chunk: str, _total: str) -> None:
    return None


class DirectCodex(Extension):
    def execute(self, call_data: dict, **kwargs):
        if not configure_direct_codex_model(call_data.get("model"), self.agent):
            return
        if not any(
            call_data.get(name)
            for name in ("response_callback", "reasoning_callback", "tokens_callback")
        ):
            # The ChatGPT Codex backend requires SSE even when the caller wants
            # a collected result. The normal transport will collect the stream.
            call_data["response_callback"] = _consume_stream
