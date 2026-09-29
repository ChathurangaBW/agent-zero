import importlib
import inspect
import json
import errno
from typing import Any, TypedDict
import aiohttp
from helpers import crypto

from helpers import dotenv


# Remote Function Call library
# Call function via http request
# Secured by pre-shared key


class RFCUnavailableError(ConnectionError):
    """RFC connection establishment failed before a request was accepted.

    Callers may safely fall back to local execution only for this exception.
    Response errors, disconnects after connection, and timeouts remain
    ambiguous and deliberately propagate without a local retry.
    """


class RFCInput(TypedDict):
    module: str
    function_name: str
    args: list[Any]
    kwargs: dict[str, Any]


class RFCCall(TypedDict):
    rfc_input: str
    hash: str


async def call_rfc(
    url: str, password: str, module: str, function_name: str, args: list, kwargs: dict
):
    input = RFCInput(
        module=module,
        function_name=function_name,
        args=args,
        kwargs=kwargs,
    )
    call = RFCCall(
        rfc_input=json.dumps(input), hash=crypto.hash_data(json.dumps(input), password)
    )
    result = await _send_json_data(url, call)
    return result


async def handle_rfc(rfc_call: RFCCall, password: str):
    if not crypto.verify_data(rfc_call["rfc_input"], rfc_call["hash"], password):
        raise Exception("Invalid RFC hash")

    input: RFCInput = json.loads(rfc_call["rfc_input"])
    return await _call_function(
        input["module"], input["function_name"], *input["args"], **input["kwargs"]
    )


async def _call_function(module: str, function_name: str, *args, **kwargs):
    func = _get_function(module, function_name)
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)


def _get_function(module: str, function_name: str):
    # import module
    imp = importlib.import_module(module)
    # get function by the name
    func = getattr(imp, function_name)
    return func


async def _send_json_data(url: str, data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=data,
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    error = await response.text()
                    raise Exception(error)
    except aiohttp.ClientConnectorError as exc:
        # A connector error includes TLS, DNS and other post-resolution
        # failures. Only a refused TCP connection is known not to have
        # reached the RFC endpoint, so only that condition may trigger a
        # direct local fallback.
        os_error = getattr(exc, "os_error", None)
        if isinstance(os_error, ConnectionRefusedError) or getattr(os_error, "errno", None) == errno.ECONNREFUSED:
            raise RFCUnavailableError(f"RFC endpoint is unavailable: {exc}") from exc
        raise
