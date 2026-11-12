# Agent contract

- Scope changes to this optional Skill package. Host integration belongs to
  `dcc-mcp-unreal`; public Skill metadata is not MCP server registration.
- Run `python -m pytest -q`, `python -m ruff check .` and
  `python tools/validate_skills.py` before delivery.
- Keep MCP tools read-only with explicit schemas. Import sibling helpers
  directly, without changing global import paths in runtime scripts.
- Preserve existing installation/authorization boundaries. User authorization
  in the current session governs ordinary work; it does not accept third-party
  license terms or grant access to another owner's resources.
- Application UI uses only project-owned `dcc-cua` / DCC-MCP `ui-control`.
  Report `provider=dcc-cua runtime=<version> pid=<pid> hwnd=<hwnd>` before UI
  observation/input. Repair or report an unavailable route.
- Keep vendor binaries, proprietary game files, local receipts and credentials
  out of this repository. Treat support/device evidence as current observations,
  not a permanent compatibility guarantee.
- Preserve exact source/tool bindings, failed runs and owned-process cleanup.
  An uncertain operation is inspected before replay. Do not modify a shared
  Engine or BuildId to force a build or compatibility result.
- Use English Conventional Commits, authored and committed as
  `loonghao <hal.long@outlook.com>`. Feature branches use `agent/`.
