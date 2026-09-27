# File Browser Development RFC Fallback

## Problem

In a native WSL development run, `GET /api/get_work_dir_files` delegated to
the development RFC endpoint even when no RFC password or listener was
configured. The resulting connection failure propagated as HTTP 500.

The RFC transport is still required for split-runtime development. A fallback
must therefore distinguish a connection that was never established from an
ambiguous failure after a remote operation may have started.

## Behavior

`helpers.runtime.call_development_function` now executes the function locally
only when:

- no RFC password is configured; or
- connection establishment raises `RFCUnavailableError`.

Timeouts, HTTP errors, authentication failures, post-connect disconnects and
remote function errors propagate without a local retry. This prevents a
state-changing remote call from being repeated locally.

`api/get_work_dir_files.py` relies on this shared contract and does not add a
second catch-all fallback. Authentication, CSRF and response shapes are
unchanged.

## Native WSL layout

The default development file-browser path is `/a0`. A native WSL installation
should map that path to its checkout during explicit environment setup, for
example:

```bash
sudo ln -s /mnt/c/path/to/agent-zero /a0
```

The application does not create this host-level link automatically.

## Verification

Run in the framework test environment:

```bash
python -m pytest tests/test_runtime_rfc_fallback.py -q
python -m pytest tests/test_file_browser_navigation.py -q
python -m pytest tests/test_http_auth_csrf.py -q
```

For a live WSL WebUI, obtain the CSRF cookie from `/`, send its value as
`X-CSRF-Token`, and verify that both `/a0` and `/` listings return HTTP 200.
The runtime log may contain an `RFC fallback to direct` warning when RFC is
unconfigured, but must contain no unhandled traceback.
