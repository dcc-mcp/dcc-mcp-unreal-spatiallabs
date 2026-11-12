# Official support evidence

Checked 2026-11-11 UTC against current public official text and download
metadata. This is a source ledger, not a permanent compatibility matrix.
Re-open the selected sources before operator installation and retain their
content fingerprints, exact package metadata and actual device/runtime evidence.
The UE5 guide still identifies some instructions/screenshots as UE5.3 while its
maintenance list includes 5.8; inspect the selected package and runtime behavior.
The Epic stat/Insights references retain their 2026-11-05 check; Acer and NVIDIA
entries were refreshed for this ledger update.

| Source | Evidence available at this check | Limits |
|---|---|---|
| [Acer UE5 download listing](https://spatiallabs.acer.com/developer/download/4af46a9c-1c10-11ec-b734-061c90c28e02) | Current record identifies UE 5.8, plugin 2.1.9, Pro devices and Acer OpenXR Runtime 1.01.2059 or later; release notes dated 2026/09/09, metadata updated 2026-09-11 without a timezone. | An upstream declaration does not verify the installed runtime, exact Pro model or native loading on a particular engine patch. |
| [Acer UE5 prerequisites](https://spatiallabs.acer.com/developer/docs/dec752e4-1211-11ec-b734-061c90c28e02/d1cfd53e-727e-4dd4-8a1a-90a353e36da3) | Development on ordinary hardware is allowed; preview/testing/running uses SpatialLabs, with the documented Pro restriction. | Hardware-free software build checks can be planned separately; no successful build or device result follows from this statement. |
| [Acer UE5 installation](https://spatiallabs.acer.com/developer/docs/dec752e4-1211-11ec-b734-061c90c28e02/e9267c33-e777-4b5e-9788-0d11ae72786c) | Installation guide and selected release notes describe the project `Plugins` workflow. | Prerequisites also contain an engine-folder instruction. Follow the authorized project-only scope; these inconsistent instructions do not grant shared Engine changes. |
| [Acer scene viewing](https://spatiallabs.acer.com/developer/docs/dec752e4-1211-11ec-b734-061c90c28e02/4975b448-68b9-46fa-9c68-ea14606a4f90) | The `VR Preview` menu opens a separate game window; `Launch game` supports an unpackaged project. The guide specifies 3840x2160 windowed fullscreen and the corresponding Start in VR setup. | The menu label does not change this skill's glasses-free scope. In-viewport PIE is not established as an equivalent stereo output path. |
| [Acer UE5 performance](https://spatiallabs.acer.com/developer/docs/dec752e4-1211-11ec-b734-061c90c28e02/12a0ce02-99da-48df-b2ce-e5f22a7ae1d8) | Names DLSS 3.7; lists Unreal Stats, STAT GPU and RenderDoc. The separate ProfileGPU window is incompatible. | No certification of DLSS 4.5, individual RR/FG/MFG features or every stereo/GPU/RHI combination. Verify capture compatibility and preserve missing timings. |
| [Acer legal entry supplied for this workflow](https://spatiallabs.acer.com/developer/docs/3e97ce90-22b4-11ed-91b8-067bb43818a8/c2b1e1dc-806b-4361-b903-8697f0ea8686) | Main EULA body is readable; installation/activation is expressed as acceptance. The checked content fingerprint is recorded below. | Reading or fingerprinting is not acceptance, operator authority or redistribution permission. Additional applicable terms still require review. |
| [NVIDIA DLSS official page](https://developer.nvidia.com/rtx/dlss) | October 2026 page lists DLSS 4.5 UE plugins for 5.8, 5.7, 5.6 and 5.5; package identifiers SL 2.14.16 / NGX 310.9.16. | General UE availability does not establish SpatialLabs stereo compatibility. Treat the Acer-specific combination as `unknown` until verified. |
| [Epic stat commands](https://dev.epicgames.com/documentation/unreal-engine/stat-commands-in-unreal-engine) | `stat unit` exposes Frame, Game, Draw, GPU, RHIT and DynRes; stat capture has explicit start and stop. | Missing GPU timing is missing evidence. Closing PIE does not guarantee an active stat capture stopped. |
| [Epic profiling introduction](https://dev.epicgames.com/documentation/unreal-engine/introduction-to-performance-profiling-and-configuration-in-unreal-engine) | Unreal Insights provides CPU/GPU and other profiling views. | Choose capture and export facilities supported by the actual target engine. |
| [NVIDIA staff explanation of UE frame counters](https://forums.developer.nvidia.com/t/frame-generation-not-work-on-ue-5-4/298908) | A July 2024 staff reply explains FG runs outside UE's measured render cycle. | Historical behavior is useful measurement context, not a current SpatialLabs compatibility certificate. |

The portal's published binary URL uses the exact host
`d20hwfev93w9j9.cloudfront.net`, direct `/upload/file/startvr/` directory and
`Acer SpatialLabs Unreal <engine> Plugin_<version>.zip` filename. The source
validator admits that reviewed namespace over HTTPS; it does not admit arbitrary
CloudFront hosts, nested paths or query parameters. Redirects use the same
validation, followed by bounded download and archive/version checks. This source
recognition grants no installation, license or hardware compatibility authority.

The EULA `UTF-8(data.content)` HTML fingerprint at this check is
`8f186dcfc7226857e2f9b8c74540e7d2aa3d4ff81bd181fe042dfd48fca472fd`.
This is not the surrounding API response or JavaScript page shell fingerprint.
The EULA does not identify a version number; metadata says
`2022-08-23T07:22:57` without a timezone. Recheck the actual content before each
operator plan. Actual device/runtime/driver capability remains `unknown` until
independently supplied and verified; this ledger is not a positive install matrix.

## Required per-project matrix

Record these fields with an evidence path or URL, observed value and check date:

- Editable project identity, source revision/hash and engine association, plus
  the engine's actual build/version; a `.uproject` association may be a GUID.
- Exact Acer plugin version and engine target from its descriptor/release notes.
- Acer runtime name/version and official minimum; do not switch system runtime.
- Exact display/device model, connection, firmware and tracking dependencies
  required by that model. A monitor name alone does not prove tracking works.
- Windows build, GPU model/architecture, driver, RHI, stereo mode and renderer.
- Each proposed NVIDIA capability, plugin version, GPU/driver requirements,
  official Acer/stereo compatibility evidence and runtime support result.
- License URL, displayed version or content fingerprint, review date and
  separately recorded human acceptance for the precise plan.

Use `supported` only when current official evidence covers that exact combination
and its required runtime capability checks succeed. Use `unsupported` for an
explicit mismatch, and `unknown` for unavailable or ambiguous evidence. Both
`unsupported` and `unknown` stop real installation/activation in this experiment.
Never turn a successful synthetic test into a supported hardware matrix entry.

## Distribution and version policy

The MIT metadata applies to this skill's authored code and documentation only.
Acer and NVIDIA packages keep their own licenses. Do not bundle, mirror or
redistribute their binaries with this skill or catalog draft. Do not interpret
an upstream download link as permission to accept terms for another person.

The standalone optional utilities retain Python 3.7 syntax. The owning adapter
requires Python 3.9+ in `AGENTS.md` and `pyproject.toml`; keep those CI gates.
An `ast` check using `feature_version=7` is syntax validation only. Python 3.7
runtime execution remains `NOT_RUN` unless actually tested on that interpreter,
and cannot be inferred from a successful run on a newer interpreter.
