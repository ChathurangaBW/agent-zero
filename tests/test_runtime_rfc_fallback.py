import asyncio

import pytest

from helpers import rfc, runtime


@pytest.fixture(autouse=True)
def development_runtime(monkeypatch):
    monkeypatch.setattr(runtime, "is_development", lambda: True)
    monkeypatch.setattr(
        runtime, "_get_rfc_url", lambda: "http://127.0.0.1:55080/api/rfc"
    )
    monkeypatch.setattr(
        runtime.files, "deabsolute_path", lambda value: "helpers/example.py"
    )


@pytest.mark.asyncio
async def test_missing_password_falls_back_to_async_function_once(monkeypatch):
    calls = []
    monkeypatch.setattr(
        runtime.dotenv, "get_dotenv_value", lambda *args, **kwargs: ""
    )

    async def operation(value):
        calls.append(value)
        return value + 1

    assert await runtime.call_development_function(operation, 4) == 5
    assert calls == [4]


@pytest.mark.asyncio
async def test_connector_failure_falls_back_to_sync_function_once(monkeypatch):
    monkeypatch.setattr(runtime, "_get_rfc_password", lambda: "configured")
    remote_calls = []
    local_calls = []

    async def unavailable(**kwargs):
        remote_calls.append(kwargs)
        raise rfc.RFCUnavailableError("connection refused")

    def operation(value):
        local_calls.append(value)
        return value * 2

    monkeypatch.setattr(runtime.rfc, "call_rfc", unavailable)
    assert await runtime.call_development_function(operation, 6) == 12
    assert len(remote_calls) == 1
    assert local_calls == [6]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        asyncio.TimeoutError("ambiguous timeout"),
        RuntimeError("remote function failed"),
        PermissionError("remote authentication failed"),
    ],
)
async def test_ambiguous_or_remote_failure_never_executes_locally(
    monkeypatch, failure
):
    monkeypatch.setattr(runtime, "_get_rfc_password", lambda: "configured")
    local_calls = []

    async def fail(**kwargs):
        raise failure

    async def operation():
        local_calls.append(True)
        return "local"

    monkeypatch.setattr(runtime.rfc, "call_rfc", fail)
    with pytest.raises(type(failure), match=str(failure)):
        await runtime.call_development_function(operation)
    assert local_calls == []


@pytest.mark.asyncio
async def test_successful_remote_result_does_not_execute_locally(monkeypatch):
    monkeypatch.setattr(runtime, "_get_rfc_password", lambda: "configured")
    local_calls = []

    async def succeed(**kwargs):
        return {"source": "remote"}

    def operation():
        local_calls.append(True)
        return {"source": "local"}

    monkeypatch.setattr(runtime.rfc, "call_rfc", succeed)
    assert await runtime.call_development_function(operation) == {"source": "remote"}
    assert local_calls == []


@pytest.mark.asyncio
async def test_rfc_http_error_is_not_reclassified_as_unavailable(monkeypatch):
    class Response:
        status = 500

        async def text(self):
            return "remote error"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(rfc.aiohttp, "ClientSession", Session)
    with pytest.raises(Exception, match="remote error") as exc:
        await rfc._send_json_data("http://127.0.0.1", {})
    assert not isinstance(exc.value, rfc.RFCUnavailableError)
