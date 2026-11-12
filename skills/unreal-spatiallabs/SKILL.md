---
name: unreal-spatiallabs
description: >-
  Experimental Acer SpatialLabs glasses-free stereoscopic 3D workflow for an
  editable Unreal project: inspect compatibility, review project-only installation,
  validate archives, prepare bounded software debugging/test runs, compare
  runtime/log/capture evidence, measured performance and layered acceptance.
  Use for SpatialLabs adaptation and conditional DLSS analysis, not headset VR
  or conversion of arbitrary closed-source games.
license: MIT
compatibility: "Python 3.7+ standalone utilities; Unreal adapter Python 3.9+. Windows SpatialLabs workflow; exact Acer engine/plugin/runtime/device combination requires current official verification."
metadata:
  dcc-mcp:
    dcc: unreal
    version: "0.1.0"
    layer: domain
    stage: project
    tags: [unreal, spatiallabs, stereoscopic, experimental, performance]
    search-hint: "Acer SpatialLabs glasses-free naked-eye 3D editable buildable Unreal game source automation debugging interaction regression stereo depth UI DLSS CPU GPU frame time OBS"
    tools: tools.yaml
---

# Unreal SpatialLabs (experimental)

This optional package is maintained in
[`dcc-mcp/dcc-mcp-unreal-spatiallabs`](https://github.com/dcc-mcp/dcc-mcp-unreal-spatiallabs)
under `skills/unreal-spatiallabs`. It originated in the Unreal adapter's optional
skills directory and is not part of the adapter's bundled skills.

The marketplace package identity is `dcc-mcp-unreal-spatiallabs`; the runtime
skill is `unreal-spatiallabs`. The catalog draft remains non-installable until
an immutable release and package integrity have been reviewed.

For local use, configure the owning adapter's explicit `extra_skill_paths` with
this checkout's absolute `skills` directory. See
[local loading](references/WORKFLOW.md#local-loading-of-this-optional-skill).
Do not restart another owner's adapter or change global environment variables.
All eight MCP tools are read-only. Operator installation and execution remain
separate from tool discovery and analysis.

Use only an editable project the user may modify. First inspect and report; a
positive filesystem preflight is not proof of official support, a successful
build or a working SpatialLabs display. Unsupported or unknown combinations
block installation. Read [official support evidence](references/SUPPORT.md)
before selecting versions and [the workflow](references/WORKFLOW.md) before
any project, build or recording action.

For a user-owned game with source, the first software automation target is an
officially supported, editable and buildable Unreal project. After the user has
authorized the exact isolated project, reviewed typed steps, bounded repair scope
and reserved instances, the software runner can carry out those software steps
without a person attending each step. Source access does not waive vendor terms.
It does not imply support for other engines or automatically generate a fix for
any game. See [software debugging and testing](references/WORKFLOW.md#software-debugging-and-testing).

## Boundaries

- Installing this skill accepts no Acer, NVIDIA or other vendor license.
  No vendor binary is included. Before any real download, the human must review
  the exact current license, plugin version, official URL and absolute project
  scope in a visible local terminal. The agent must not enter the acceptance
  phrase, pipe acceptance through stdin, simulate input or pass an approval flag.
- The declared MCP tools are read-only. The separate operator installer is the
  only installation route. The operator must have explicitly authorized that
  project and accepted the displayed terms; an MCP argument such as
  `approved: true`, a saved plan or prior skill installation cannot replace this.
- Work in an isolated project copy and source worktree. Preserve source hashes,
  uncommitted changes and backups. Do not take over an existing UE/OBS instance,
  clear another owner's lease, stop their job or alter the original project.
- Never change engine-wide plugins, the system OpenXR runtime, drivers,
  permissions, global settings or security protections through this workflow.
  Acer OpenXR may be a SpatialLabs dependency; its name does not extend this skill
  to headset VR. Missing prerequisites are an operator handoff.
- No arbitrary game injection or promise of one-click closed-source conversion.
  No push, public PR, merge, publishing or distribution follows from this skill.
- The separate software runner executes only the hash-bound, reviewed typed
  steps for the authorized target. Repairs require explicit scope and finite
  retry limits. An uncertain mutation is inspected before retry; failures outside
  the reviewed repair scope stop for review. No arbitrary generated code or shell
  command is implied by the goal of unattended software testing.
- If hardware is absent, device stereo, tracking, comfort and device performance
  remain `NOT_RUN`. Synthetic tests, 2D output and OBS footage cannot pass them.

## Read-only tool sequence

Discover the installed tools, read their current schemas and use their returned
names exactly. Do not construct instance slugs. These local names describe this
package's contract:

| Tool | Purpose |
|---|---|
| `inspect_stereo_pair(pair_path)` | Verify retained software eye images, hashes, camera metadata and exact SBS pixel composition; scene/disparity/device acceptance remain separate. |
| `inspect_project(project_path, environment={})` | Inspect an editable project or locate a candidate in a delivery folder; report the resolved `.uproject`, bounded search scope, plugin/config state and supplied environment evidence. |
| `inspect_software_evidence(project_path, engine_root, run_log_path, capture_path=None, cache_state="unknown")` | Read specified existing files: compare installed/runtime identity, audit declared GameFeatureData dependencies and assess one cold/warm native capture. No host calls, scene auto-pass or installation authority. |
| `plan_install(project_path, plugin_version, engine_version, source_url, support_evidence=None, license_evidence=None)` | Produce a reviewable plan scoped to one project; this does not download, accept terms, configure or install anything. |
| `validate_archive(archive_path, plugin_version, engine_version)` | Inspect a local archive and metadata before installation; rejection leaves the project untouched. |
| `analyze_performance(baseline, candidate)` | Compare measured runs only when their conditions match; preserve missing metrics and distinguish rendered from generated frames. |
| `acceptance_report(evidence)` | Summarize evidence per layer; missing evidence cannot become a pass. |
| `prepare_software_plan(project_path, instance_id, steps, max_attempts=1, instance_short=None)` | Prepare a bounded hash-bound software plan from reviewed discovered tool schemas; does not call tools, mutate the project or authorize execution. |

1. Resolve source ownership and identify the actual engine and editable source.
   A folder labelled "source" may contain only a packaged game. For delivery
   folders, follow [input intake](references/WORKFLOW.md#delivery-folder-intake);
   do not run bundled executables or mistake cooked archives for editable assets.
   Resolve the exact source project directory or `.uproject`. Inspect without
   mutating. Record the project identity and actual engine, plugin, runtime,
   GPU/driver and device evidence. The tool performs filesystem inspection;
   automatic runtime/device/GPU probing is not implemented. Supplied environment
   data is reported, unverified evidence, not hardware attestation. Recheck the
   current official combination; `unknown` is a blocker.
   A supplied support record must identify a supported exact engine/plugin/
   runtime/device combination, an official Acer source URL and its check date.
   It is review evidence, not an automatic discovery result or installation
   authorization; the operator must verify it again before accepting the plan.
2. Create an authorized isolated project copy with a manifest of source paths,
   hashes and revision. Review intended camera/depth/UI changes and keep them in
   that copy. Do not copy credentials or unrelated data.
3. Produce and review the installation plan. Stop for the human operator's
   license acceptance and exact project authorization. The plan must bind
   `license_evidence` to the fixed official Acer license URL, a SHA-256 of the
   precise terms content the operator read and a current timezone-aware check
   time. This record is evidence only. Without it, planning remains read-only
   and installation/console download is refused. Before accepting, the operator
   must confirm that the current official content still has that hash; changed
   content requires a new plan and review. Follow
   [installation and rollback](references/WORKFLOW.md#operator-installation)
   without driving their terminal input.
4. After the operator completes `operator_install.py install plan.json`, re-inspect and verify the receipt,
   archive digest, installed files, config diff and rollback data. A local digest
   without a separately trusted vendor digest is provenance, not vendor
   authenticity verification. On failure preserve diagnostics and use the
   receipt-based operator rollback; never overwrite changed user files. A rollback
   preserves the managed plugin under the transaction's `plugin.rolled-back`
   directory. Never delete that quarantine or automatically retry an uncertain
   install.
5. With separately authorized, unoccupied UE/build/OBS resources, validate
   editor, standalone build and 2D behavior. Then perform device checks only on
   the verified SpatialLabs combination. Use the DCC-MCP discovery, schema,
   call, status and artifact verification sequence in the workflow reference.
   Inspect retained run files with `inspect_software_evidence`; follow
   [software evidence checks](references/SOFTWARE_EVIDENCE.md). Keep installed
   metadata distinct from the actual log identity, preserve required runtime
   dependencies when disabling control plugins, and retain cold failures after
   a warm capture succeeds. A valid PNG and native screenshot log still require
   visual review of the real scene and separate run/project ownership evidence.
6. Establish a measured baseline, evaluate compatible optimizations individually
   and compare equivalent runs using [performance rules](references/PERFORMANCE.md).
   DLSS SR, DLAA, RR and FG are separate capabilities. Generated display FPS
   does not establish improved CPU/GPU render time or reduced latency.
7. Deliver the plan, manifest, diffs, install/rollback receipts, raw metric
   references, build logs, recording metadata and layered
   [acceptance report](references/ACCEPTANCE.md). Mark every unexecuted layer
   `NOT_RUN`, including actual vendor installation, build and recording if only
   synthetic regression tests ran.

For a version to hand to another person, follow [device playtest delivery](references/DELIVERY.md). A screenshot capture plugin and a playable device build have different launch, runtime and acceptance requirements.

## Scripts

Eight entry-point scripts expose the read-only tools listed above. Shared helpers
include `spatiallabs_project.py`, `spatiallabs_performance.py`,
`spatiallabs_software.py`, and the software evidence/runtime helpers.
`operator_install.py` and `software_runner.py` are
separate operator consoles; listing or loading this skill does not authorize
their mutations or provide their human confirmation.

## Software runner

`scripts/spatiallabs_software.py` supplies preparation and execution helpers.
`prepare_software_plan` is one of the eight read-only MCP tools; `run_software_plan` is
available only through the separate operator-authorized path. The repository
CLI is `scripts/software_runner.py`: `prepare SPEC.json` prints a read-only plan
and `run PLAN.json` requires a visible human TTY. The human enters the exact
`RUN SOFTWARE CHECKS <plan-hash>` phrase once; the agent must not enter it, pipe
input or use an approval boolean. After that authorization, the reviewed software
steps can run unattended. Inspect help and the saved plan before execution.
Full schema validation requires `jsonschema>=4.17` as declared in this optional
skill's `requirements.txt`; missing dependencies fail closed and are never
automatically installed. The optional stereo pixel checker also requires Pillow, which is not automatically installed. Python 3.7 runtime execution remains unverified; Pillow inspection is tested on Python 3.9+.

The reviewed sequence is preflight and official support/terms review -> isolated
source/configuration plan -> authorized installation/configuration -> compile
and start -> bounded interaction regression -> logs and CPU/GPU capture ->
conditional DLSS A/B runs -> OBS output -> software and hardware-separated report.
Use exact discovered tool slugs, schemas and instance identities. Installation
keeps its human license gate; automated test authorization cannot accept terms.

The run records each step, its result and recovery state. A step without result
assertions can show call completion only; its business outcome remains `NOT_RUN`.
`max_attempts` is an upper bound of 1 or 2, not a promise of automatic retry.
A fixed, explicitly reviewed repair may execute once; the failed action is not
replayed and unknown repairs are not generated. Missing prerequisites, changed identities,
unknown mutation outcomes or exhausted retries require review. Hardware stereo,
tracking, comfort and device performance cannot pass from software-run results.
The CLI displays, resolves and hash-binds the real `dcc-mcp-cli` executable from
an absolute PATH location outside the project; it does not run a project-cwd
shadow executable. It checks fresh ready-instance/schema discovery and probes
the project before mutation, with automatic CLI updates disabled. The initial
UE preflight must be the normally discovered `unreal_pie__pie_get_status`
backend with empty arguments and `project_result_path` equal to
`["context", "perf", "project_name"]`; never construct its instance slug.
This host capability reads Unreal's current project path, not a filesystem echo.

OBS start requires an included read-only idle preflight whose selected recording
value is exactly `false`, and an actual output schema guaranteeing a string
recording ID. Without that schema, recording is `NOT_RUN` and is not started.
Stopping requires this run's successful returned ID, an exact ID parameter
selector and a response confirming the same ID. Non-start/stop OBS roles must
be actually read-only. Never take over recording or clear leases. A restarted
run only observes its prior journal; a disk-recorded ID does not regain ownership.
Source drift can be read for historical recovery but cannot authorize mutations.
Live execution requires a confirmed target, available task-owned instances and
the normal authorized control path. If access is refused or a technical HOLD
remains, live discovery and execution stay `NOT_RUN`; finding a source path or
passing offline regressions does not release that gate.

Stop on authorization refusal, changed project identity, unsafe paths, unknown
support, malformed/incomplete downloads or archive validation failure. Diagnose
the rejected operation; do not try another identity, global install path,
transport or control surface to bypass it.
