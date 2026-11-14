# Device playtest delivery

Use this workflow when someone should receive a runnable game and connect their
own SpatialLabs device. When the request is broad compatibility, prepare the
ordinary game independently while keeping a separate device/runtime matrix.
An unknown recipient model does not block the ordinary package. Record the exact
model, Windows/GPU/driver, Acer runtime and current official support before
activating or accepting the vendor integration on that target.

## Windows 10/11 and multiple devices

One Windows x64 package can target Windows 10 and Windows 11; test its actual
launch and controls on each OS before declaring both verified. Python CI on a
Windows runner is not a packaged Unreal game or Windows 10 acceptance result.
Check the Engine's minimum OS/build and graphics requirements separately from
the selected display runtime's requirements.

For the official UE 5.8 integration, the current Acer 2.1.9 release notes limit
support to SpatialLabs Pro devices and require Acer OpenXR Runtime 1.01.2059 or
later. Do not interpret the runtime minimum as proof that every newer release
supports both Windows versions or every Pro model.

| Target | Ordinary game | Current Acer UE 5.8 stereo integration |
|---|---|---|
| Windows 10 x64 | Target and test independently | Verify the exact Pro model/runtime/Windows build first |
| Windows 11 x64 | Target and test independently | Verify the exact Pro model/runtime/Windows build first |
| Officially supported SpatialLabs Pro models | Ordinary display mode remains separate | Candidate after vendor prerequisites and authorized installation; device result pending |
| Consumer View/Predator models or another vendor's display | Ordinary display mode remains separate | Outside this Acer plugin's declared Pro-only support; investigate that model's official route separately |

Deliver normal 2D launch and supported device launch as explicit choices. A
missing runtime should produce a useful prerequisite message or allow ordinary
mode; it must not silently change the system OpenXR runtime, install a driver,
or relabel 2D output as device stereo. Broad compatibility intent does not
authorize sideloading Pro software on consumer hardware. If another model needs
a distinct integration, package and validate it separately.

Sources rechecked 2026-11-12:
[Acer prerequisites](https://spatiallabs.acer.com/developer/docs/dec752e4-1211-11ec-b734-061c90c28e02/d1cfd53e-727e-4dd4-8a1a-90a353e36da3),
[Acer UE 5.8 release listing](https://spatiallabs.acer.com/developer/download/4af46a9c-1c10-11ec-b734-061c90c28e02),
[Epic Windows requirements](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine).

## Choose and verify the delivery

| Output | What the recipient can test | What remains unverified |
|---|---|---|
| Software SBS PNG pair | Static stereoscopic content in a compatible player | Interactive game, vendor integration, tracking and comfort |
| Packaged game emitting live software SBS | Both-eye rendering and separately tested gameplay | Official model/runtime compatibility, display, tracking and comfort |
| Packaged ordinary game | Launch, controls and complete gameplay without an editor | SpatialLabs stereo and tracking |
| Packaged game with the supported vendor integration | Device launch, stereo and tracking under the matching runtime | Hardware acceptance until the recipient actually tests it |

A capture helper can have fixed project paths, Editor-only dependencies, an
expected Editor executable hash, offscreen flags and automatic exit. Inspect these
before packaging. Remove a task-specific capture helper from the authorized
delivery copy; retain its frozen source, images and receipts separately. An Editor
plugin DLL is not a Shipping/Game binary. Never copy it into a packaged game or
change BuildId to pretend compatibility.

For an existing Shipping game's stereo-emulation route, use the
[playable stereo checks](PLAYABLE_STEREO.md). Treat each-eye menu composition,
input, projection and normal shutdown as explicit checks before packaging;
an ordinary game's working controls alone do not pass those checks.

## Build an isolated candidate

1. Preserve the original project, frozen evidence and previous failed runs.
   Create a separate delivery copy and review source/configuration changes.
2. For a vendor-enabled build, verify official engine/plugin/runtime/model
   compatibility and the applicable installation and redistribution terms.
   Follow the operator license workflow before downloading or installing a vendor
   package. These vendor prerequisites do not block an authorized ordinary build.
   Do not bundle a driver/runtime installer merely because its download is public.
3. Configure the correct startup map, required streaming maps, runtime modules,
   device resolution/fullscreen mode and a normal input/exit path. Use current
   vendor instructions. Screenshot settings such as `-RenderOffscreen`, a fixed
   `-seconds` budget or disabled input do not belong in the recipient launcher.
4. Plan the actual Game/Shipping target and cook/stage/archive operations. Read
   every action/UHT/output/delete path before executing. Scope writable temp,
   logs, DDC and UBA state to the delivery task; preserve separately reviewed
   shared startup diagnostics. Supervise the new process tree through real root
   exit and owned Job emptiness. A budget expiry is not cleanup evidence.
5. Check the package from a path unrelated to the developer source directory.
   It must include cooked assets and required licensed prerequisites and start
   without an installed Unreal Editor or the developer's absolute paths.
   Bind the Game/Shipping executable and target receipt, enabled runtime modules,
   startup configuration and cooked archive hashes to the same reviewed candidate.
   Verify that the Game receipt includes the changed runtime module; an older
   game executable and a newly compiled Editor plugin are not that candidate.
6. Provide the executable/archive, hashes, short device connection/launch steps,
   controls, supported combination and a way to return the app's own logs.
   Ask the recipient to test scene progression, input, stereo, eye tracking,
   UI/depth, stability and comfort. Keep untested results `NOT_RUN`.

## Native implementation lessons

- Include complete `UPackage` and `APawn` definitions when using their members
  or converting their pointers; do not rely on transitive Editor headers.
- Some Windows Engine binaries route `FPlatformMisc::GetSHA256Signature` to an
  unimplemented generic assertion. A Win64-only helper can use Windows CNG
  `BCryptHash` with `bcrypt.lib` and an `abc` known-vector startup self-check.
  Preserve the failing log; do not modify the shared Engine. Independently
  compare emitted file hashes with the receiving system's SHA-256 utility.
- In the inspected UE 5.8 `ExecutorFactory`, `-NoUBA` disables detouring while
  the local UBA scheduler still executes ordinary `[NoUba]` actions. Inspect
  the selected implementation before interpreting the executor's name or flags.
  A task-scoped child
  `UBA_ROOT`, `-nocache` and `-UBADisableRemote` contained the reviewed build;
  these do not redirect the separate startup `Trace.uba` rotation.
- Export actions through a direct UBT invocation with `-WriteOutdatedActions`
  and `-NoEngineChanges` as top-level build-mode arguments. In the inspected
  UE 5.8 UAT route, nesting them inside `-ubtargs` did not apply those global
  options and compilation ran instead. Require the actual exported graph before
  calling a stage action-only. UAT can also schedule an Editor target for a
  nominally Blueprint project; use `-nocompileeditor` when reusing its existing
  editor. After an accepted Game build, `-skipbuild` avoids recompiling it during
  cook/stage/archive.
- An exported action graph does not prove that an import restores its dependencies.
  In the inspected UE 5.8 toolchain, `LinkedAction.ExportJson` writes
  `PrerequisiteActions` IDs, but `Action.ImportJson` reads `PrerequisiteItems`;
  `ActionGraph.ImportJson` and `ExecuteMode` do not restore the ID edges.
  Direct `-Mode=Execute -Actions=...` therefore ran links and dependent compiles
  before their precompiled header (PCH), producing `LNK1181` and `C1083` errors.
  Preserve this failure and use the standard UBT Build entry with the reviewed
  target, source and flags so its in-memory dependencies remain intact. Do not
  patch the shared Engine, hand-edit the graph or invent an executor. Check the
  selected exporter/importer before reuse; this is not a ban on every Engine
  patch's import path. A locked PCH during its own compile is not evidence of
  a shared Engine permission problem.
- Review and hash the actual on-disk response files as well as the exported
  commands and outputs. In that toolchain, `ResponseFileContents` contained a
  prefix; the real compiler response file also contained language, optimization
  and warning flags. Preserve those bytes before the next stage; do not truncate
  the file to the exported prefix. A normal UBT Build may regenerate its own
  project-local response files, which must remain distinct from the retained
  export evidence.
- UE 5.8's C# `ConfigFile` parser splits command-line INI overrides on commas,
  including commas inside tuples. A tuple accepted by the native engine can
  therefore fail in UAT before cooking. For the existing filesystem `Local`
  store, `-ddc=(Local)` plus
  `-AdditionalCookerOptions=-LocalDataCachePath=<task-cache>` avoids a tuple
  override. Confirm the effective cache path, shader-worker count and cooker
  count in the actual cook log.
- Keep native lifetime independent of progress-file durability. After a process
  resumes, a journal write error must not discard its Job/process handles or
  trigger another launch. Windows readers of atomically replaced progress files
  should permit [delete sharing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew#parameters).
  Preserve I/O failures and await real exits. If the named Job is unavailable,
  report its lifetime as unknown; a last PID list, a passing replacement test or
  a generated EXE does not establish that the original Job is empty.
- The same lifetime rule applies to every post-resume exception and an uncertain
  `ResumeThread` outcome, not just progress-file I/O. Keep observing the same
  original root/thread/Job handles; an exception handler must not release them
  in `finally` while the tree is still live or unknown. After actual root exit
  and Job emptiness, retain the first error and report failure even if the root
  returned zero. Completed cleanup does not turn that failure into a build pass.
  Check this with non-native fault tests for repeated query/save failures,
  interrupts and uncertain resume. Separately preserve safe cleanup of only the
  newly created, provably unresumed suspended root; do not relaunch or adopt a Job.
- Do not use an Engine tick limit as a supervisor deadline. A retained Shipping
  probe with `-SECONDS=90` remained active beyond five minutes; argument parsing
  and the effective tick limit were not established for that build. Keep the
  original supervisor and handles alive until actual exit and owned Job emptiness.
  If normal automatic exit is unavailable and DCC-CUA observation fails, request
  a manual normal close; do not send blind input, force termination or relaunch.

These observations describe retained software evidence, not universal support
across every Engine patch. Recheck the selected installation before reuse.
