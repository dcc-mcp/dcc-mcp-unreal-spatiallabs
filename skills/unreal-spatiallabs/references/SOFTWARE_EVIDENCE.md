# Existing-run software evidence

`inspect_software_evidence` is a read-only file analyzer. It launches no process,
loads no vendor code, changes no plugin/configuration, and grants no installation,
support or execution approval. It is usable without a physical SpatialLabs display
or live adapter. Access refusals and the existing host/resource gates still apply.

Supply the exact editable `.uproject` file, its existing Engine directory, a finalized
native log, an optional native PNG, and this run's reported `cache_state` (`cold`,
`warm`, or `unknown`). Discover/describe the actual MCP tool before live calls;
standalone review may run the entry-point script with its JSON input on stdin.
No acceptance phrase is part of this read-only tool. Its successful result envelope
means analysis completed, not that the game or scene passed.

```json
{
  "project_path": "C:/review/Game/Game.uproject",
  "engine_root": "F:/UE/UE_5.8/Engine",
  "run_log_path": "C:/review/run-02/Game.log",
  "capture_path": "C:/review/run-02/Game.png",
  "cache_state": "warm"
}
```

## Installed identity and observed runtime

Keep `Build/Build.version` metadata separate from the log's actual `Engine Version`
and changelist. A patch/changelist conflict is a mismatch, not a supported exact
version. Missing or conflicting runtime identities remain unknown. The tool does
not attest that an arbitrary supplied log came from the specified Engine executable;
retain the original launch plan, executable hash and task-owned process receipt.
Never repair or replace a shared Engine to make these records agree.

## Runtime dependencies after control isolation

The dependency audit targets configured `GameFeatureData` references. It reads
bounded Engine plugin descriptors and reports declared enabling paths, including
runtime functionality supplied indirectly by toolsets. Disabling `AllToolsets`
can remove `AllToolsets -> GameFeaturesToolset -> GameFeatures` while project
configuration still requires `/Script/GameFeatures.GameFeatureData`.

Review a minimal isolated dependency correction only when the actual configuration
and descriptors support it. The analyzer does not enable GameFeatures in every
project, reinstall toolsets, restore Python, or recursively modify plugins.
Declared/default/target-dependent edges are static evidence; they are not a native
plugin-resolution or asset-load proof. In particular, a descriptor's `Enabled:false`
does not prove no module mounted. Preserve actual module/interpreter/control-service
logs separately; `-DisablePython` can leave stock Python modules mounted while the
interpreter remains disabled.

## One cold or warm capture

The analyzer records bounded log/capture fingerprints and native observations.
PNG integrity, matching native save path/dimensions, World/RHI messages and frame
number make a capture eligible for visual review. They do not identify room contents
or prove loading finished. A complete sky-only, black, loading, default-material or
unrelated scene must not pass merely because the process exited0 or the file decoded.
Screenshot convergence delay, `DEFER` count, elapsed seconds and a high frame number
are not room-ready assertions.

Cold streaming/load timeout is retained as a failure for that run. Analyze a warm
run independently and retain both records; warming DDC changes conditions and does
not demonstrate a fix for cold-loading reliability. Do not pool cold/warm timing
or claim performance improvement from fewer initialization seconds.

Visual review remains required even for well-formed native output. Record the
reviewer's observed scene, image SHA-256 and scope separately. The analyzer cannot
independently bind an editable project to an arbitrary log or prove process cleanup.
Retain task-owned launch/Job records and the source/configuration manifest. The
current tool never automatically passes the scene, full game, interaction, package,
performance, OBS, SBS, Acer output or physical-device layers.

## Native build startup writes

Before building a capture plugin, inspect the selected installed UBT's startup
logging and cache lifecycle as well as its project/action outputs. A project-local
`-Log` and `-NoEngineChanges` do not establish that all writes stay in the task.
The latter also does not reject every new Engine output; review the action graph
and generated-header destinations before compiling.

Some installed UBT versions rotate a user-level `Trace.uba` through
`Log.BackupLogFile` before parsing normal build arguments. That rotation can
delete old shared backups before the requested project log is configured.
For this startup path, `-Log` and `-NoUBA` do not redirect or disable the rotation.
Record the exact installed source/binary fingerprints, startup paths and retention
effects before reserving a build attempt. Project build authorization alone does
not establish ownership of existing shared diagnostics.

If rotation is refused, preserve the exception and owned-process terminal receipt.
Do not delete/move old traces, change ACLs, impersonate a recursive `-Session`, set
BuildMachine/profile aliases, replace UBT or switch entry points to bypass it.
Resume only after the actual shared-data blocker is resolved within its authorized
scope, with a newly reviewed attempt budget and current resource handoff.
Distinguish planning (which can already run UHT), compilation, module loading and
actual eye capture; failure before the action graph proves none of the later stages.

## Bounded continuation

Preserve the first failed log/image and known exit state before changing a reviewed
isolated variant. A new plan must bind its new descriptor fingerprint and remaining
attempt budget. An old plan cannot be replayed after a dependency change. An
uncertain process is inspected, not restarted. New UE/SBS execution also needs its
then-current resource window; a previous release is not a future reservation.

For simulated SBS, require actual distinct camera transforms/projections and raw
left/right captures with matching run/frame metadata. Copying a 2D PNG into both
halves does not establish binocular disparity. The new analyzer checks ordinary
run evidence only and does not implement stereo rendering or pair acceptance.
