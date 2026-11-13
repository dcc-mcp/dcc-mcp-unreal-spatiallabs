# Layered acceptance and handoff

Use `PASS`, `FAIL` and `NOT_RUN` per layer, with evidence paths, versions,
timestamps and acquisition method. Unknown prerequisites and missing evidence
cannot become `PASS`. A blocked layer does not invalidate independently measured
lower-layer results, but it prevents a claim that the overall hardware workflow
passed. Keep any schema-specific result names from `acceptance_report` and explain
their meaning; never manually change a returned rejection into success.

| Layer | Evidence required |
|---|---|
| Source and safety regression | Actual test command/output, code revision/diff, test environment; unauthorized zero-download/zero-write behavior, version mismatch, malformed archive/path/link rejection, failure preservation, idempotence and rollback conflicts. Mock network/package tests are labeled synthetic. |
| Bounded software suite | Hash-bound software plan, exact authorized source/copy and instance identities, reviewed typed steps, durable per-step call/job/evidence results, finite retry counts and any explicitly authorized repair diff/rollback. Synthetic dispatch tests do not pass a real-game suite. |
| Optional skill packaging | Lint and creator validation against `optional-skills/unreal-spatiallabs`, resolved scripts and explicit tool schemas, actual discovery/load/router evidence if executed. Bundled-skill lint alone does not validate this optional directory. |
| Real vendor installation | Human-operated license/scope acceptance, verified current support matrix, official source/redirect and integrity record, install receipt, project-local diff, backup and rollback readback. Synthetic installation cannot pass this layer. |
| UE editor load | Exact copied project/engine/runtime/descriptor identity, correct plugin load logs, schema/control call result and error review. Copying a plugin directory is insufficient. |
| Ordinary 2D regression | Current project map/camera/UI checks, actual launch/call path, output/logs and result; prior sample footage is not this skill's result. |
| Standalone build | Exact DCC-MCP instance/job, build command/arguments, terminal result/log, artifact path/hash and actual executable launch/behavior. |
| OBS demonstration | Selected OBS instance/source, pre/start/running/stop/finalization evidence, clip metadata and file hash. A 2D recording cannot pass device perception. |
| Physical stereo | Exact supported SpatialLabs model/runtime/plugin combination, physical observer, near/screen/far depth, binocular consistency, occlusion and UI evidence. |
| Tracking | Physical device tracking acquisition, viewing movement, tracking loss/recovery and observed behavior. A display name or process is insufficient. |
| Comfort | Actual observer feedback, conditions and duration on the device; no inferred medical or safety claim. |
| Device performance and optimization | Raw comparable hardware runs, CPU/GPU distributions, render/display FPS distinction, latency method, quality checks and approved optimization diff/rollback. |

If no matching physical display is available, force the last four rows to
`NOT_RUN`; do not accept a caller's `PASS` label without device evidence.
Hardware claims remain unverified even if schema validation and every synthetic
regression test pass. When no real installation, build or recording was attempted,
those rows also remain `NOT_RUN`.

## Software suite results

The software runner's goal is unattended execution of a reviewed suite for an
officially supported, editable/buildable Unreal source project after its exact
scope is authorized. Preserve the plan ID, target identities, dispatch schemas,
per-step state, return/job/recording IDs, actual assertion results, evidence paths,
attempt bound and any fixed reviewed repair performed once. Include source/config
diffs and rollback data for actual repairs. A completed call with no assertions
cannot pass the business outcome; report that outcome `NOT_RUN`.
An available source tree does not waive Acer/NVIDIA terms or authorize arbitrary
generated code changes. A failure outside the approved repair scope stops for
review and is not reported as a fixed game.

Do not mark an uncertain mutation as failed and automatically repeat it. Retain
the uncertainty and inspect the original job/state before any recovery. A suite
that needs review remains incomplete/failed according to its actual result;
partial software success cannot pass missing build, input, capture or hardware
checks. Test-runner unit tests prove only their tested synthetic behavior.

Retain the actual read-only `project_result_path` observation proving the approved
`.uproject` from the discovered `unreal_pie__pie_get_status` backend with empty
arguments and selector `["context", "perf", "project_name"]`; a filesystem
echo is insufficient. Retain fresh ready-instance/schema checks and the absolute
reviewed CLI path/hash outside the project. For OBS retain the included actual
read-only idle guard and its boolean `false`, the output-schema guarantee of
a string recording ID, this run's successful start/ID and the exact stop
parameter selector plus same-ID response/finalization. Missing ID/schema means
the recording remains `NOT_RUN`; uncertain outcomes are not retried. An OBS
logs/preflight role must not hide a mutating tool.

A reopened journal supports read-only status/history recovery, not reacquisition
of recording ownership from disk. Source drift can be observed during recovery;
new mutations still require strict identity. Preserve a failed step for a new
reviewed continuation; a fixed reviewed repair executes once, without generated
code or failed-action replay. `max_attempts` in 1..2 is an upper bound, not evidence
that an action was safely replayed or fixed. Missing `jsonschema>=4.17` fails
closed without automatic dependency installation.

If source, authorized live resources or normal control access are unavailable,
keep the affected live discovery, compilation, launch, interaction, CPU/GPU
capture, DLSS A/B and OBS layers `NOT_RUN`. An access refusal blocks that action;
retained-file analysis does not release it. The physical-device layers remain
separate even after software steps pass.

The read-only `inspect_software_evidence` tool analyzes existing logs, metadata,
declared runtime dependencies and optional native PNG integrity. Its successful
envelope means analysis completed. It never automatically passes scene readiness:
a valid, natively logged sky-only screenshot still needs visual rejection. Keep
cold and warm records separate, retain timeout/errors, and review the exact image
hash and actual scene alongside the original project/process ownership evidence.
See [software evidence checks](SOFTWARE_EVIDENCE.md). File analysis does not attest
a live executable, bind an arbitrary log to a project, authorize a repair or prove
task-owned children exited.

## Input record for `acceptance_report`

The current tool normalizes these exact `layers` keys: `code`, `editor`, `2d`,
`package`, `stereo`, `tracking`, `comfort`, `device_performance`. Its summary is
restricted to those eight layers. Keep optional packaging, real installation,
rollback, software-suite and OBS recording results in the supplemental evidence ledger above;
the tool does not aggregate those extra rows and must not imply that it did.

Each supplied layer contains `status`, `reason` and an `evidence` path/reference
for `PASS` or `FAIL`. Missing layers default to `NOT_RUN`. A supplied `NOT_RUN`
needs a nonempty reason. `editor`, `2d` and `package` passes also require
`capture_kind: actual_run`, so mocks and earlier unrelated sample evidence are
not sufficient.

For real-device evidence, supply a top-level `device` object with
`present: true`, `kind: physical`, `family: acer_spatiallabs`, `device_id`,
`model` and `evidence`. A normal display or headset is not a substitute. Each
hardware layer's `PASS` must identify that same `device_id`, have
`capture_kind: physical_device` and include its own evidence. The analyzer only
checks the supplied records; a human must still review the physical capture and
official support. An example for a run with no hardware is:

```json
{
  "device": {"present": false, "family": "acer_spatiallabs"},
  "layers": {
    "editor": {"status": "NOT_RUN", "reason": "No new-skill editor run executed"},
    "2d": {"status": "NOT_RUN", "reason": "No new-skill 2D run executed"},
    "package": {"status": "NOT_RUN", "reason": "No build executed"}
  }
}
```

This returns an incomplete result and forces hardware layers to `NOT_RUN`.
Paths and status labels alone are not independent proof that an action ran.

Record manual playtest feedback with the exact run, action sequence and observed
result. For example, dismissing a tutorial and clicking the scene before movement
works confirms that combined sequence, not that focus alone caused the earlier
failure. A movement check does not pass interaction, scene progression, both-eye
UI or device acceptance. Retain these subchecks separately under the existing
layers; no new `acceptance_report` layer keys are introduced. Follow the
[playable stereo checks](PLAYABLE_STEREO.md) for live software SBS.

## Minimum deliverable

- Source branch/base/head or reviewed local diff and applicable instructions.
- Source-to-copy project lineage and hash manifest; no credentials.
- Official support ledger with date, exact values and unresolved `unknown`s.
- Reviewed plan, authorized scope, actual installation/rollback receipts if run,
  hashes, diffs, phase journal and any failure/conflict report. Identify the
  retained `.spatiallabs-transactions/PLAN_ID/plugin.rolled-back` directory after
  rollback; do not delete it or hide an uncertain install outcome behind a retry.
- Exact regression/lint commands, real outputs and the Python versions actually
  executed. AST compatibility is reported as syntax validation only.
- Current editor/2D/build/recording evidence only for executed actions.
- Software plan ID and step journal, exact typed calls/jobs, finite retry/repair
  outcomes and evidence that uncertain side effects were not blindly repeated.
- Baseline/candidate identities, raw metric references and result limits.
- Per-layer status and the precise next step for each `FAIL` or `NOT_RUN`.

Do not publish the catalog draft, mark it installable, merge or push as part of
acceptance. Those operations require separate authorization and a reviewed
immutable release package. The current draft records source ownership only.
