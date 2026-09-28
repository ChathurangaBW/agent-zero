from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_deserialize_log_preserves_item_id() -> None:
    from helpers.log import Log
    from helpers.persist_chat import _deserialize_log, _serialize_log

    log = Log()
    log.log(type="user", heading="User message", content="hello", id="msg-123")
    log.log(type="assistant", heading="Assistant", content="hi")

    serialized = _serialize_log(log)
    restored = _deserialize_log(serialized)

    assert restored.logs[0].type == "user"
    assert restored.logs[0].id == "msg-123"
    assert restored.logs[1].type == "assistant"
    assert restored.logs[1].id is None


def test_load_tmp_chats_skips_directories_without_chat_json(monkeypatch, capsys) -> None:
    from helpers import persist_chat

    monkeypatch.setattr(persist_chat, "_convert_v080_chats", lambda: None)
    monkeypatch.setattr(
        persist_chat.files,
        "get_abs_path",
        lambda *parts: "/" + "/".join(str(part).strip("/") for part in parts if part),
    )
    monkeypatch.setattr(
        persist_chat.files,
        "list_files",
        lambda folder, pattern="*": ["orphan", "valid"],
    )
    monkeypatch.setattr(
        persist_chat.files,
        "exists",
        lambda path: str(path).endswith("/valid/chat.json"),
    )
    monkeypatch.setattr(
        persist_chat.files,
        "read_file",
        lambda path: json.dumps({"id": "valid"}),
    )
    monkeypatch.setattr(
        persist_chat,
        "_deserialize_context",
        lambda data: SimpleNamespace(id=data["id"], data={}),
    )

    assert persist_chat.load_tmp_chats() == ["valid"]
    assert "Error loading chat" not in capsys.readouterr().out


def test_load_tmp_chats_clears_and_persists_interrupted_stream(monkeypatch) -> None:
    from helpers import persist_chat

    context = SimpleNamespace(id="interrupted", data={})
    saved = []
    monkeypatch.setattr(persist_chat, "_convert_v080_chats", lambda: None)
    monkeypatch.setattr(
        persist_chat.files,
        "get_abs_path",
        lambda *parts: "/" + "/".join(str(part).strip("/") for part in parts if part),
    )
    monkeypatch.setattr(
        persist_chat.files, "list_files", lambda folder, pattern="*": ["interrupted"]
    )
    monkeypatch.setattr(persist_chat.files, "exists", lambda _path: True)
    monkeypatch.setattr(
        persist_chat.files,
        "read_file",
        lambda _path: json.dumps({"id": "interrupted", "streaming_agent": 1}),
    )
    monkeypatch.setattr(persist_chat, "_deserialize_context", lambda _data: context)
    monkeypatch.setattr(persist_chat, "save_tmp_chat", saved.append)

    assert persist_chat.load_tmp_chats() == ["interrupted"]
    assert saved == [context]


def test_deserialize_context_does_not_restore_process_local_streamer() -> None:
    from agent import AgentContext
    from helpers import persist_chat
    from initialize import initialize_agent

    context_id = f"interrupted-stream-{uuid.uuid4().hex[:8]}"
    context = AgentContext(config=initialize_agent(), id=context_id, set_current=False)
    try:
        serialized = persist_chat._serialize_context(context)
        # Subordinate chat snapshots may begin at agent number 1, which used to
        # make the stale marker resolve to a real Agent object after restart.
        serialized["agents"][0]["number"] = 1
        serialized["streaming_agent"] = 1
        AgentContext.remove(context_id)
        restored_interrupted = persist_chat._deserialize_context(serialized)
        assert restored_interrupted.streaming_agent is None
    finally:
        AgentContext.remove(context_id)


def test_save_tmp_chat_preserves_existing_file_until_atomic_replace(
    monkeypatch, tmp_path
) -> None:
    from agent import AgentContextType
    from helpers import persist_chat

    path = tmp_path / "chat.json"
    path.write_text("previous", encoding="utf-8")
    context = SimpleNamespace(id="chat", type=AgentContextType.USER, data={})

    monkeypatch.setattr(persist_chat, "_get_chat_file_path", lambda _ctxid: str(path))
    monkeypatch.setattr(persist_chat, "_serialize_context", lambda _context: {"new": True})
    real_replace = persist_chat.os.replace

    def interrupted_replace(_source: str, destination: str) -> None:
        assert Path(destination).read_text(encoding="utf-8") == "previous"
        raise OSError("simulated interruption")

    monkeypatch.setattr(persist_chat.os, "replace", interrupted_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        persist_chat.save_tmp_chat(context)

    assert path.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob("*.tmp")) == []

    monkeypatch.setattr(persist_chat.os, "replace", real_replace)
    persist_chat.save_tmp_chat(context)

    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
    assert context.data[persist_chat.SAVED_CHAT_CONTEXT_DATA_KEY] is True


def test_parallel_recovery_metadata_survives_chat_round_trip() -> None:
    from agent import AgentContext
    from helpers import parallel_tools, persist_chat
    from initialize import initialize_agent

    context_id = f"parallel-recovery-{uuid.uuid4().hex[:8]}"
    context = AgentContext(config=initialize_agent(), id=context_id, set_current=False)
    try:
        context.set_data(
            parallel_tools.PARALLEL_JOBS_RECOVERY_KEY,
            {
                "version": 1,
                "jobs": [
                    {
                        "job_id": "persisted-job",
                        "index": 0,
                        "tool_name": "call_subordinate",
                        "kind": "subordinate",
                        "state": "running",
                        "created_at": 100.0,
                        "started_at": 101.0,
                        "log_id": "persisted-log",
                    }
                ],
            },
        )
        serialized = persist_chat._serialize_context(context)
        assert "_parallel_jobs" not in serialized["data"]
        assert serialized["data"][parallel_tools.PARALLEL_JOBS_RECOVERY_KEY]["jobs"]

        restored = persist_chat._deserialize_context(serialized)
        assert parallel_tools.restore_parallel_jobs(restored) == 1
        recovered_job = restored.get_data(parallel_tools.PARALLEL_JOBS_KEY)["persisted-job"]
        assert recovered_job.state == "interrupted"
        assert recovered_job.deferred_task is None
    finally:
        AgentContext.remove(context_id)
