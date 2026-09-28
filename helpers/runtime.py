import argparse
import inspect
import secrets
from pathlib import Path
from typing import TypeVar, Callable, Awaitable, Union, overload, cast
from helpers import dotenv, rfc, files
import asyncio
import threading
import queue
import sys
import nest_asyncio

nest_asyncio.apply()

T = TypeVar("T")
R = TypeVar("R")

parser = argparse.ArgumentParser()
args = {}
dockerman = None
runtime_id = None
_rfc_warning_lock = threading.Lock()
_warned_rfc_unavailable = set()


def initialize():
    global args
    if args:
        return
    parser.add_argument("--port", type=int, default=None, help="Web UI port")
    parser.add_argument("--host", type=str, default=None, help="Web UI host")
    parser.add_argument(
        "--cloudflare_tunnel",
        type=bool,
        default=False,
        help="Use Cloudflare Tunnel for public URL",
    )
    parser.add_argument(
        "--development", type=bool, default=False, help="Development mode"
    )

    known, unknown = parser.parse_known_args()
    args = vars(known)
    for arg in unknown:
        if "=" in arg:
            key, value = arg.split("=", 1)
            key = key.lstrip("-")
            args[key] = value


def get_arg(name: str):
    global args
    return args.get(name, None)


def has_arg(name: str):
    global args
    return name in args


def is_dockerized() -> bool:
    return bool(get_arg("dockerized"))


def is_development() -> bool:
    return not is_dockerized()


def get_local_url():
    if is_dockerized():
        return "host.docker.internal"
    return "127.0.0.1"


def get_runtime_id() -> str:
    global runtime_id
    if not runtime_id:
        runtime_id = secrets.token_hex(8)
    return runtime_id


def get_persistent_id() -> str:
    id = dotenv.get_dotenv_value("A0_PERSISTENT_RUNTIME_ID")
    if not id:
        id = secrets.token_hex(16)
        dotenv.save_dotenv_value("A0_PERSISTENT_RUNTIME_ID", id)
    return id


def _warn_rfc_fallback_once(message: str) -> None:
    """Keep an expected development outage visible without flooding logs."""
    with _rfc_warning_lock:
        if message in _warned_rfc_unavailable:
            return
        _warned_rfc_unavailable.add(message)
    from helpers.print_style import PrintStyle
    PrintStyle.warning(f"RFC fallback to direct: {message}")


@overload
async def call_development_function(
    func: Callable[..., Awaitable[T]], *args, **kwargs
) -> T: ...


@overload
async def call_development_function(func: Callable[..., T], *args, **kwargs) -> T: ...


async def call_development_function(
    func: Union[Callable[..., T], Callable[..., Awaitable[T]]], *args, **kwargs
) -> T:
    if is_development():
        try:
            return await call_remote_development_function(func, *args, **kwargs)
        except rfc.RFCUnavailableError as exc:
            # A connector failure means no RFC request was accepted, so a
            # local fallback cannot duplicate remote work. Ambiguous timeout,
            # response, authentication, and remote-function errors propagate.
            _warn_rfc_fallback_once(str(exc))
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
    else:
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)  # type: ignore


async def call_remote_development_function(
    func: Union[Callable[..., T], Callable[..., Awaitable[T]]], *args, **kwargs
) -> T:
    """RFC-only control operations must never act on this local process."""
    url = _get_rfc_url()
    password = _get_rfc_password()
    module_path = Path(files.deabsolute_path(func.__code__.co_filename)).with_suffix("")
    result = await rfc.call_rfc(url=url, password=password, module=".".join(module_path.parts),
                               function_name=func.__name__, args=list(args), kwargs=kwargs)
    return cast(T, result)


async def handle_rfc(rfc_call: rfc.RFCCall):
    return await rfc.handle_rfc(rfc_call=rfc_call, password=_get_rfc_password())


def _get_rfc_password() -> str:
    password = dotenv.get_dotenv_value(dotenv.KEY_RFC_PASSWORD)
    if not password:
        raise rfc.RFCUnavailableError("No RFC password is configured.")
    return password


def _get_rfc_url() -> str:
    # Delay import to avoid a circular import with helpers.settings.
    from helpers import settings
    set = settings.get_settings()
    url = set["rfc_url"]
    if not "://" in url:
        url = "http://" + url
    if url.endswith("/"):
        url = url[:-1]
    url = url + ":" + str(set["rfc_port_http"])
    url += "/api/rfc"
    return url


def call_development_function_sync(
    func: Union[Callable[..., T], Callable[..., Awaitable[T]]], *args, **kwargs
) -> T:
    # run async function in sync manner
    result_queue = queue.Queue()

    def run_in_thread():
        result = asyncio.run(call_development_function(func, *args, **kwargs))
        result_queue.put(result)

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join(timeout=30)  # wait for thread with timeout

    if thread.is_alive():
        raise TimeoutError("Function call timed out after 30 seconds")

    result = result_queue.get_nowait()
    return cast(T, result)


def get_web_ui_port():
    web_ui_port = (
        get_arg("port") or int(dotenv.get_dotenv_value("WEB_UI_PORT", 0)) or 5000
    )
    return web_ui_port


def get_tunnel_api_port():
    tunnel_api_port = (
        get_arg("tunnel_api_port")
        or int(dotenv.get_dotenv_value("TUNNEL_API_PORT", 0))
        or 55520
    )
    return tunnel_api_port


def get_platform():
    return sys.platform


def is_windows():
    return get_platform() == "win32"


def get_terminal_executable():
    if is_windows():
        return "powershell.exe"
    else:
        return "/bin/bash"
