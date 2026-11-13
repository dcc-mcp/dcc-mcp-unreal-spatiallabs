# Playable software stereo checks

Use this reference for an authorized editable game's live side-by-side (SBS)
output. Keep vendor installation, software rendering, interaction and physical
display acceptance separate. This reference adds no tools or execution authority.

## Select the actual route

Epic documents `emulatestereo` as stereo emulation. Verify that the exact Shipping
build actually produces two eye views; a recognized argument or binary symbol is
insufficient. Acer documents SpatialLabs GO consuming fullscreen SBS content.
Check the recipient's current official model/software requirements before using
that route. Native SBS input is distinct from AI conversion of ordinary 2D.
Neither route establishes support for every SpatialLabs model or replaces the
Pro-only plugin compatibility checks in [delivery](DELIVERY.md).

Sources: [Epic command-line reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-command-line-arguments-reference?application_version=5.8)
and [Acer's published SBS description](https://news.acer.com/acer-unveils-spatiallabs-on-conceptd-empowering-creators-with-stereoscopic-3d).
The Acer article is historical capability evidence, not a current device matrix.

## Diagnose controls before changing mappings

Observe the same owned game's current menu, tutorial, pause state and viewport
focus through project DCC-CUA. Before observation/input, report its actual
provider, runtime, PID and HWND. A window being unfocused now does not prove it
was unfocused when the user encountered a problem. Do not steal focus or send
blind keys to test that hypothesis.

Read the game's own control instructions and trace menu/tutorial entry and exit,
input mode, movement/look locks, Controller/Pawn possession and actual Enhanced
Input mapping initialization. Asset references or exported graph names alone do
not prove the runtime state. A tutorial may intentionally retain movement locks
until its close handler restores Game input. Confirm the actual dismiss-and-move
sequence before changing input code. Keep game-specific keys and graph names in
the project's controls and evidence, rather than imposing them on other games.

Record which manual or authorized automated actions restored control. Separately
test look, interaction/pickup, menus and scene progression. Keep untested actions
`NOT_RUN`; movement alone is not a complete gameplay pass.

## Verify each eye and the UI

Retain original, time-separated native frames with exact run and capture metadata.
Review actual scene contents, eye order, per-eye aspect and stereo correspondences.
Decorations or capture scaling are not the render viewport; preserve originals and
label any analysis crop. Different frame bytes alone do not prove input response.

Check menus, logos, reticles, text and pointer targets in each eye. A single UMG
overlay spanning the combined pair is a delivery defect even when the scene has
two views. Verify hit testing after any UI correction. Camera tuning does not fix
UI composition, and changing the UI does not establish projection calibration.

Inspect the active camera, view target, eye offset, FOV, projection asymmetry and
WorldToMeters before calibration. For the inspected UE 5.8 implementation,
`GeneralProjectSettings` exposes `EyeOffsetForFakeStereoRenderingDevice`,
`FOVForFakeStereoRenderingDevice`, `TopFOVRatioForFakeStereoRenderingDevice`
and `DifferenceBetweenEyesForFakeStereoRenderingDevice`. Verify their effective
values and implementation in the selected Engine; do not prescribe universal
values, patch a shared Engine or reuse one screenshot's disparity as a comfort
threshold. Hardware stereo, tracking, comfort and performance remain `NOT_RUN`
without the corresponding physical tests.

## Keep game exit and task cleanup distinct

Retain original process/Job ownership until actual root exit and the entire owned
Job is empty. Observation budgets and Engine tick limits do not grant termination
authority. Preserve the original exit result and return that specific resource
slot to its coordinator; do not backfill a different run's unknown lifetime.

Keep separate receipts for capture preparation/restoration, each DCC-CUA task,
Host connection completion and the Game process tree. Exact OS process-exit
evidence can establish that a helper exited, but cannot recreate its missing
cleanup acknowledgement, exit code or restoration result. MissingWindow after
Game exit also does not manufacture an owned-session cleanup acknowledgement.
Retain these gaps explicitly for the responsible owner's resource disposition.

A semantic Window node does not authorize physical shortcuts. Discover the
current Host contract and obtain the actual action scope before input; physical
keyboard classification may require a raw-input scope even with semantic
observations. An action-confirmation tier is not an authorization category, and
renaming intent cannot lower it. After a real refusal, stop that action and retain
the result. Do not add scope, switch task/mode/provider or replay a refused key.
A future independently authorized run needs its own valid grant and binding.
