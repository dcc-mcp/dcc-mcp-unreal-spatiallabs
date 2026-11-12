# DCC-MCP Unreal SpatialLabs

Optional Skills for preparing, inspecting and testing an editable Unreal project
for Acer SpatialLabs. This package contains eight read-only MCP tools plus
separate operator consoles for authorized installation and software execution.

The runtime Skill is `unreal-spatiallabs`. The distribution identity is
`dcc-mcp-unreal-spatiallabs`. This is an experimental Skill package, not an Unreal
adapter or a display driver. Use the existing
[Unreal adapter](https://github.com/dcc-mcp/dcc-mcp-unreal) to connect a host.

## What is included

- Project and official-support inspection, archive checks and installation plans.
- Retained runtime/log/PNG evidence checks and measured performance comparisons.
- Software SBS pair validation: image hashes, camera metadata, distinct eye pixels
  and exact rowwise `left|right` composition.
- Bounded software plans and separate operator-controlled execution and rollback.

Read the [Skill contract](skills/unreal-spatiallabs/SKILL.md),
[device playtest delivery workflow](skills/unreal-spatiallabs/references/DELIVERY.md)
and [official support ledger](skills/unreal-spatiallabs/references/SUPPORT.md).

An integrity check does not identify the visible scene, measure its disparity,
attest an original process, or certify a physical device. These remain separate
reviews. A successful screenshot run is not a playable packaged game.

## Local use

Configure the Unreal adapter's explicit `extra_skill_paths` with this checkout's
absolute `skills` directory. Installing the adapter does not enable this package.
Use `dcc-mcp-cli list`, then discover and describe the actual returned tools.
Do not construct instance tool names or take over another owner's running host.

For offline stereo evidence review, the entry point
`skills/unreal-spatiallabs/scripts/inspect_stereo_pair.py` accepts a JSON object
on stdin containing the absolute `pair_path`. It starts no Unreal, vendor code,
driver or network request. Pillow is required for this optional pixel inspection;
dependencies are never installed by a tool call.

## Development

```console
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python tools/validate_skills.py
```

CI checks Python 3.9 and 3.12 on Windows and Linux. Python 3.7 syntax checks for
legacy utilities do not establish Python 3.7 runtime support. This checkout is
validated against released Core 0.20.44; live host/device acceptance is separate.

No Acer/NVIDIA binaries, proprietary game assets, credentials or local task
receipts are included. Vendor terms and runtime prerequisites remain with the
device owner. The catalog is a non-installable draft; creating this repository
does not publish a marketplace package.

The initial implementation was extracted from `dcc-mcp-unreal` commit
`c7b92695dc6119d6fb46f1a85b7b03b3260e6ebb`, preserving its optional utilities and
regression tests. Subsequent reusable changes are maintained here.
