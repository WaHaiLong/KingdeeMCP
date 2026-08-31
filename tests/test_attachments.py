"""V6.0 attachment contract tests. All HTTP requests use an in-memory transport."""

import asyncio
import base64
import json
import os
import sys
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from kingdee_mcp import server


def upload_input(**changes):
    values = dict(form_id="PUR_PurchaseOrder", bill_id="100723", bill_no="CGDD000198",
                  file_name="合同.txt", send_byte="77u/MTIzNA==")
    values.update(changes)
    return server.AttachmentUploadInput(**values)


def success(**fields):
    return {"Result": {"ResponseStatus": {"IsSuccess": True, "Errors": [],
                                          "SuccessEntitys": []}, **fields}}


def uploaded():
    result = success(FileId="file-123", Message="")
    result["Result"]["ResponseStatus"]["SuccessEntitys"] = [{"Id": 470257, "Number": None}]
    return result


def downloaded(**changes):
    fields = dict(FileName="合同.txt", FileSize=7, FilePart="77u/MTIzNA==",
                  StartIndex=4194304, IsLast=True, Message="")
    fields.update(changes)
    return success(**fields)


@pytest.fixture
def api(monkeypatch):
    """Exercise real httpx serialization without opening a socket."""
    calls, responses = [], []

    async def handle(request):
        calls.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)

    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(server.httpx, "AsyncHTTPTransport", lambda **kwargs: transport)
    monkeypatch.setattr(server, "SERVER_URL", "https://kingdee.invalid/k3cloud/")
    monkeypatch.setattr(server, "_session_id", "test-session")
    monkeypatch.setattr(server, "_session_lock", None)
    log = Mock()
    monkeypatch.setattr(server, "log_tool_usage", log)

    async def login():
        server._session_id = "renewed-session"
        return server._session_id

    login_mock = AsyncMock(side_effect=login)
    monkeypatch.setattr(server, "_login", login_mock)
    return calls, responses, login_mock, log


@pytest.mark.parametrize("changes", [
    {"form_id": " "}, {"bill_id": ""}, {"bill_no": " "}, {"file_name": ""},
    {"file_id": " "}, {"send_byte": "not base64!"}, {"send_byte": "data:text/plain;base64,YQ=="},
    {"send_byte": "合同"}, {"is_last": "false"}, {"unknown": 1},
    {"entry_id": "100"}, {"entry_key": "FPOOrderEntry"},
    {"entry_key": "FPOOrderEntry", "entry_id": "-1"},
    {"send_byte": base64.b64encode(b"a" * (4 * 1024 * 1024 + 1)).decode()},
])
def test_upload_validation(changes):
    with pytest.raises(ValidationError):
        upload_input(**changes)


@pytest.mark.parametrize("changes", [
    {"file_id": " "}, {"start_index": -1}, {"start_index": True},
    {"start_index": 0.5}, {"unexpected": 1},
])
def test_download_validation(changes):
    with pytest.raises(ValidationError):
        server.AttachmentDownloadInput(**{"file_id": "file-123", **changes})


def test_empty_file_and_max_chunk_are_valid():
    assert upload_input(send_byte="", entry_id="-1").send_byte == ""
    data = base64.b64encode(b"a" * (4 * 1024 * 1024)).decode()
    assert upload_input(send_byte=data).send_byte == data


@pytest.mark.asyncio
async def test_header_upload_wire_contract_and_ids(api):
    calls, responses, login, log = api
    responses.append(uploaded())
    out = json.loads(await server.kingdee_upload_attachment(upload_input()))
    assert len(calls) == 1
    assert calls[0].url.path.endswith("DynamicFormService.AttachmentUpLoad.common.kdsvc")
    assert calls[0].headers["cookie"] == "kdservice-sessionid=test-session"
    assert calls[0].headers["content-type"] == "application/json"
    outer = json.loads(calls[0].content)
    assert isinstance(outer, dict) and set(outer) == {"data"} and isinstance(outer["data"], str)
    assert json.loads(outer["data"]) == {
        "FileName": "合同.txt", "FormId": "PUR_PurchaseOrder", "InterId": "100723",
        "BillNO": "CGDD000198", "IsLast": True, "SendByte": "77u/MTIzNA==",
    }
    assert out["success"] and out["next_action"] is None
    assert out["file_id"] == "file-123" and out["attachment_ids"] == [470257]
    login.assert_not_awaited()
    # Logging must never contain file bytes, names or identifiers.
    logged = repr(log.call_args)
    for value in ("77u/MTIzNA==", "合同.txt", "file-123", "test-session"):
        assert value not in logged


@pytest.mark.asyncio
async def test_entry_chunk_upload_carries_file_id_and_completion(api):
    calls, responses, _, _ = api
    responses.extend([success(FileId="file-123"), uploaded()])
    first = json.loads(await server.kingdee_upload_attachment(upload_input(
        is_last=False, entry_key="FPOOrderEntry", entry_id="101300", alias_file_name="合同",
    )))
    assert first["success"] and first["next_action"] == "upload_attachment"
    assert first["attachment_ids"] == []
    final = json.loads(await server.kingdee_upload_attachment(upload_input(
        file_id=first["file_id"], entry_key="FPOOrderEntry", entry_id="101300", send_byte="YQ==",
    )))
    payload = json.loads(json.loads(calls[1].content)["data"])
    assert payload["FileId"] == "file-123" and payload["IsLast"] is True
    assert payload["Entrykey"] == "FPOOrderEntry" and payload["EntryinterId"] == "101300"
    assert json.loads(json.loads(calls[0].content)["data"])["AliasFileName"] == "合同"
    assert final["next_action"] is None and final["is_last"] is True


@pytest.mark.asyncio
async def test_download_chunks_preserve_server_cursor(api):
    calls, responses, _, _ = api
    responses.extend([downloaded(IsLast=False, FilePart="YQ=="),
                      downloaded(StartIndex=8388608, FilePart="Yg==")])
    first = json.loads(await server.kingdee_download_attachment(
        server.AttachmentDownloadInput(file_id="file-123")))
    assert first["next_action"] == "download_attachment" and not first["is_last"]
    last = json.loads(await server.kingdee_download_attachment(
        server.AttachmentDownloadInput(file_id="file-123", start_index=first["start_index"])))
    assert json.loads(json.loads(calls[1].content)["data"]) == {"FileId": "file-123", "StartIndex": 4194304}
    assert calls[0].url.path.endswith("DynamicFormService.AttachmentDownLoad.common.kdsvc")
    assert last["next_action"] is None and last["file_name"] == "合同.txt"
    # The manual's cursor can exceed FileSize; do not calculate it from decoded length.
    assert last["start_index"] == 8388608 and last["file_size"] == 7
    assert base64.b64decode(first["file_part"]) + base64.b64decode(last["file_part"]) == b"ab"


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [
    {"IsLast": "false"}, {"IsLast": False, "StartIndex": 0}, {"StartIndex": -1},
    {"StartIndex": True}, {"FilePart": "invalid!"}, {"FilePart": None},
    {"FileSize": -1}, {"FileName": None},
])
async def test_malformed_download_never_reports_completion(api, fields):
    api[1].append(downloaded(**fields))
    out = json.loads(await server.kingdee_download_attachment(server.AttachmentDownloadInput(file_id="x")))
    assert out["success"] is False and out["errors"]
    assert "next_action" not in out and len(api[0]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    {"Result": None}, {}, success(), success(FileId=""),
    {"Result": {"ResponseStatus": {"IsSuccess": "true"}}},
    httpx.Response(200, text="response_error: upstream error"),
])
async def test_malformed_upload_is_unknown_and_not_retried(api, response):
    api[1].append(response)
    out = json.loads(await server.kingdee_upload_attachment(upload_input()))
    assert out["success"] is False and out["outcome_unknown"] is True
    assert "next_action" not in out and len(api[0]) == 1


@pytest.mark.asyncio
async def test_business_error_and_file_id_are_preserved_without_retry(api):
    calls, responses, login, log = api
    responses.append({"Result": {"ResponseStatus": {"IsSuccess": False, "Errors": [
        {"Message": "附件权限不足", "FieldName": "FormId"}]}, "FileId": "partial-id"}})
    out = json.loads(await server.kingdee_upload_attachment(upload_input()))
    assert not out["success"] and out["errors"][0]["message"] == "附件权限不足"
    assert out["file_id"] == "partial-id" and "next_action" not in out
    assert len(calls) == 1 and log.call_args.args[3] is False
    login.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_business_error_uses_top_level_message(api):
    api[1].append({"ResponseStatus": {"IsSuccess": False, "Errors": []}, "Message": "文件不存在"})
    out = json.loads(await server.kingdee_download_attachment(server.AttachmentDownloadInput(file_id="missing")))
    assert not out["success"] and out["errors"] == [{"message": "文件不存在"}]
    assert "file_part" not in out and len(api[0]) == 1


@pytest.mark.asyncio
async def test_empty_download_is_supported(api):
    api[1].append(downloaded(FilePart="", FileSize=0))
    out = json.loads(await server.kingdee_download_attachment(server.AttachmentDownloadInput(file_id="empty")))
    assert out["success"] and out["file_part"] == "" and out["next_action"] is None


@pytest.mark.asyncio
async def test_log_failure_does_not_hide_successful_upload(api):
    api[1].append(uploaded())
    api[3].side_effect = OSError("log directory is read-only")
    out = json.loads(await server.kingdee_upload_attachment(upload_input()))
    assert out["success"] and out["file_id"] == "file-123"
    assert len(api[0]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [httpx.ReadTimeout("hidden payload"),
                                       httpx.ConnectError("hidden payload"),
                                       httpx.Response(503, text="hidden payload")])
async def test_upload_network_failures_are_not_replayed_or_logged(api, exception):
    calls, responses, _, log = api
    responses.append(exception)
    result = await server.kingdee_upload_attachment(upload_input())
    out = json.loads(result)
    assert not out["success"] and out["outcome_unknown"]
    assert "勿自动重传" in out["recovery_hint"] and len(calls) == 1
    assert "hidden payload" not in result + repr(log.call_args)


@pytest.mark.asyncio
async def test_explicit_401_reauthenticates_and_retries_once(api):
    calls, responses, login, _ = api
    responses.extend([httpx.Response(401), uploaded()])
    out = json.loads(await server.kingdee_upload_attachment(upload_input()))
    assert out["success"] and len(calls) == 2
    assert calls[0].content == calls[1].content
    assert calls[1].headers["cookie"] == "kdservice-sessionid=renewed-session"
    login.assert_awaited_once()


@pytest.mark.asyncio
async def test_second_401_stops(api):
    calls, responses, login, _ = api
    responses.extend([httpx.Response(401), httpx.Response(401)])
    out = json.loads(await server.kingdee_upload_attachment(upload_input()))
    assert not out["success"] and len(calls) == 2
    login.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_words_in_successful_filename_do_not_replay(api):
    api[1].append(downloaded(FileName="session expired 会话.txt"))
    out = json.loads(await server.kingdee_download_attachment(server.AttachmentDownloadInput(file_id="x")))
    assert out["success"] and len(api[0]) == 1
    api[2].assert_not_awaited()


@pytest.mark.asyncio
async def test_cold_session_login_is_shared(api, monkeypatch):
    monkeypatch.setattr(server, "_session_id", None)
    api[1].extend([downloaded(), downloaded()])
    await asyncio.gather(*[server.kingdee_download_attachment(server.AttachmentDownloadInput(file_id="x"))
                           for _ in range(2)])
    api[2].assert_awaited_once()
    assert len(api[0]) == 2


@pytest.mark.asyncio
async def test_mcp_discovery_exposes_safe_annotations_and_validates_input(api):
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}
    assert tools["kingdee_upload_attachment"].annotations.readOnlyHint is False
    assert tools["kingdee_upload_attachment"].annotations.idempotentHint is False
    assert tools["kingdee_download_attachment"].annotations.readOnlyHint is True
    assert tools["kingdee_download_attachment"].annotations.idempotentHint is True
    api[1].append(uploaded())
    result = await server.mcp.call_tool("kingdee_upload_attachment", {"params": upload_input().model_dump()})
    # Test actual FastMCP dispatch as well as direct Python calls.
    assert result and len(api[0]) == 1
