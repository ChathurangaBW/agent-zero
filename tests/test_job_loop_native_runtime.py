"""Development remote pause cannot disable the native framework scheduler."""
import asyncio

import pytest

from helpers import job_loop, rfc, runtime


@pytest.fixture(autouse=True)
def native_environment(monkeypatch):
    monkeypatch.setattr(runtime, "is_development", lambda: True)
    monkeypatch.setattr(runtime, "_get_rfc_url", lambda: "http://127.0.0.1:55080/api/rfc")
    monkeypatch.setattr(runtime.files, "deabsolute_path", lambda path: "helpers/job_loop.py")
    monkeypatch.setattr(job_loop, "keep_running", True)
    monkeypatch.setattr(job_loop, "pause_time", 0)
    monkeypatch.setattr(job_loop.PrintStyle, "error", lambda *args: None)


@pytest.mark.asyncio
@pytest.mark.parametrize("outage", ["unconfigured", "refused"])
async def test_native_scheduler_runs_when_remote_pause_transport_is_unavailable(monkeypatch, outage):
    calls = []
    if outage == "unconfigured":
        monkeypatch.setattr(runtime.dotenv, "get_dotenv_value", lambda *a, **kw: "")
    else:
        monkeypatch.setattr(runtime, "_get_rfc_password", lambda: "fixture")
        async def refused(**kwargs):
            raise rfc.RFCUnavailableError("connection refused")
        monkeypatch.setattr(runtime.rfc, "call_rfc", refused)
    async def tick():
        calls.append("local scheduler and extensions")
    monkeypatch.setattr(job_loop, "scheduler_tick", tick)
    await job_loop.run_iteration()
    await job_loop.run_iteration()
    assert calls == ["local scheduler and extensions"] * 2
    assert job_loop.keep_running is True
    assert job_loop.pause_time == 0


@pytest.mark.asyncio
async def test_successful_remote_pause_never_calls_local_pause(monkeypatch):
    remote, local = [], []
    monkeypatch.setattr(runtime, "_get_rfc_password", lambda: "fixture")
    async def accept(**kwargs):
        remote.append(kwargs)
    async def tick():
        local.append("tick")
    monkeypatch.setattr(runtime.rfc, "call_rfc", accept)
    monkeypatch.setattr(job_loop, "scheduler_tick", tick)
    await job_loop.run_iteration()
    assert len(remote) == 1 and remote[0]["function_name"] == "pause_loop"
    assert local == ["tick"] and job_loop.keep_running is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [asyncio.TimeoutError("ambiguous"), PermissionError("auth"), RuntimeError("remote")])
async def test_ambiguous_pause_keeps_local_scheduler_progressing(monkeypatch, failure):
    monkeypatch.setattr(runtime, "_get_rfc_password", lambda: "fixture")
    async def fail(**kwargs):
        raise failure
    calls = []
    async def local_tick():
        calls.append("tick")
    monkeypatch.setattr(runtime.rfc, "call_rfc", fail)
    monkeypatch.setattr(job_loop, "scheduler_tick", local_tick)
    await job_loop.run_iteration()
    assert calls == ["tick"]
    assert job_loop.keep_running is True


@pytest.mark.asyncio
async def test_remote_only_contract_raises_unavailable_without_executing_function(monkeypatch):
    monkeypatch.setattr(runtime.dotenv, "get_dotenv_value", lambda *a, **kw: "")
    async def mutation():
        pytest.fail("remote-only call executed locally")
    with pytest.raises(rfc.RFCUnavailableError):
        await runtime.call_remote_development_function(mutation)
