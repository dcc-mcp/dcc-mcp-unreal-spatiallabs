# Device playtest delivery

Use this workflow when someone should receive a runnable game and connect their
own SpatialLabs device. Record the exact model, Windows/GPU/driver, Acer runtime
version and the current official engine/plugin support record first.

## Choose and verify the delivery

| Output | What the recipient can test | What remains unverified |
|---|---|---|
| Software SBS PNG pair | Static stereoscopic content in a compatible player | Interactive game, vendor integration, tracking and comfort |
| Packaged ordinary game | Launch, controls and complete gameplay without an editor | SpatialLabs stereo and tracking |
| Packaged game with the supported vendor integration | Device launch, stereo and tracking under the matching runtime | Hardware acceptance until the recipient actually tests it |

A capture helper can have fixed project paths, Editor-only dependencies, an
expected Editor executable hash, offscreen flags and automatic exit. Inspect these
before packaging. Remove a task-specific capture helper from the authorized
delivery copy; retain its frozen source, images and receipts separately. An Editor
plugin DLL is not a Shipping/Game binary. Never copy it into a packaged game or
change BuildId to pretend compatibility.

## Build an isolated candidate

1. Preserve the original project, frozen evidence and previous failed runs.
   Create a separate delivery copy and review source/configuration changes.
2. Verify official engine/plugin/runtime/model compatibility and the applicable
   vendor installation and redistribution terms. Follow the operator license
   workflow before downloading or installing a vendor package. Do not bundle a
   driver/runtime installer merely because its download is public.
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
- UE 5.8's installed `ExecutorFactory` can initialize local UBA despite
  `-NoUBA`. Inspect the exact installed implementation. A task-scoped child
  `UBA_ROOT`, `-nocache` and `-UBADisableRemote` contained the reviewed build;
  these do not redirect the separate startup `Trace.uba` rotation.

These observations describe retained software evidence, not universal support
across every Engine patch. Recheck the selected installation before reuse.
