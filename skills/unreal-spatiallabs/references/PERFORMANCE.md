# Performance and conditional DLSS evaluation

Start with a measured baseline on the copied project. An FPS overlay, process
survival or a vendor demonstration is not a benchmark of this project.

## Comparable run identity

For each run retain project revision/content hashes, map, camera path and timing,
resolution for each eye and final output, screen percentage/dynamic resolution,
render settings and quality profile, RHI/renderer, exact engine/plugin/runtime,
hardware, driver/OS, display refresh/mode, tracking state and power conditions.
Record build configuration, warm-up, sample start/end/duration, repeat count,
background workload, VSync/frame cap and profiling/OBS capture overhead.

Before/after comparisons use matching conditions except the named optimization
under test. Document that one intentional difference. A changed camera,
resolution, scene revision or GPU invalidates a direct causal comparison;
`analyze_performance` must return an incompatibility or insufficient-evidence
result rather than inventing a percentage improvement. Repeat runs when needed
to distinguish noise, shader compilation or thermal behavior from a change.

## Capture and metrics

For the Acer path, the current [Acer performance guide](https://spatiallabs.acer.com/developer/docs/dec752e4-1211-11ec-b734-061c90c28e02/12a0ce02-99da-48df-b2ce-e5f22a7ae1d8)
identifies the separate `ProfileGPU` window as incompatible. Do not invoke it
for this path. The guide lists Unreal Stats, `STAT GPU` and RenderDoc; discover
the actual typed capture capabilities and verify their compatibility before
collecting data. Record capture overhead and preserve unavailable GPU timings.

Discover the target engine's typed profiling/console/log tools and describe
their schemas. Use supported Unreal Insights/CSV/stat capture facilities. Start
and stop every capture explicitly; Epic documents that `stat startfile` may
continue after PIE closes. Bound capture time/disk use and retain raw file paths
and hashes, exporter version and sampling notes.

Collect separate values for frame time, Game CPU, Draw CPU, RHI CPU and GPU time.
Preserve available frame-time samples and report count, median and tail
percentiles such as p95/p99 with units and aggregation method. CPU and GPU may
overlap; do not add them together to invent a total frame time. Record memory or
VRAM pressure and observable stalls when instrumentation provides them.

Keep these values distinct:

| Metric | Meaning and limits |
|---|---|
| Render FPS | Actual rendered application frames per second with the acquisition method; do not infer it from an FG display overlay. |
| Display/presented FPS | Presented output including generated frames when applicable; identify the external measurement/counter. |
| CPU/GPU frame time | Measured render-work timing; an increased presentation rate does not establish reduced work time. |
| Latency | Explicitly identify CPU, render, game-to-present or end-to-end input-to-photon measurement. One cannot substitute for another. |
| Recording FPS | OBS encoding/capture cadence; it is neither application render FPS nor proof of display refresh. |

Unavailable metrics are `null` with a reason and acquisition status. Do not use
zero, synthetic estimates or a reciprocal of display FPS as GPU render time.
Report the sample window and missing data. A counter that cannot distinguish
generated frames cannot prove a render-FPS improvement.

## Conditional optimization decisions

First identify the bottleneck from measured CPU/GPU work. Review expensive
screen-space and pixel-dependent effects on the stereo path, content cost,
scalability and resolution only within the authorized copied project. Keep
before/after configuration diff and rollback data. Do not silently modify global
NVIDIA settings, power policy, driver, runtime or engine installation.

Evaluate these NVIDIA capabilities separately, using the current official
plugin documentation and actual runtime capability queries:

| Capability | Required evidence before enabling |
|---|---|
| Super Resolution (SR) | Exact engine/plugin/GPU/driver/RHI support, correct per-eye inputs and stereo compatibility for the chosen Acer path; compare image detail, temporal stability and frame time. |
| DLAA | Its own support result and configuration; compare at a defined native resolution. Do not label DLAA as SR upscaling. |
| Ray Reconstruction (RR) | Supported ray-tracing/rendering path and plugin/engine combination, plus explicit stereo compatibility. Compare denoising artifacts, motion and both eyes. |
| Frame Generation / Multi Frame Generation | Exact GPU and driver capability, presentation path and Acer stereo compatibility; measure generated presentation rate, real rendered frame rate and latency separately. |
| Reflex or other latency controls | Supported integration, independent enablement state and an identified latency measurement; do not assume FPS gains imply latency gains. |

The [support ledger](SUPPORT.md) records Acer's currently published DLSS 3.7
recommendation and a separate NVIDIA general UE listing. These are not
sufficient evidence to enable modern FG/RR automatically. Missing Acer/stereo
evidence yields `unknown` and no activation. A runtime status saying "enabled"
does not demonstrate correct binocular output.

For each approved optimization, perform A/B runs with the same scene/camera and
conditions, repeat samples, and compare measured timing, quality and latency.
Inspect both eyes for ghosting, mismatched detail, disocclusion, motion, UI and
tracking artifacts. Capture fixed reference frames and moving segments. Preserve
the ability to revert that single change before testing the next one.

Without the supported physical SpatialLabs display, 2D timing can be reported as
2D timing only. Device stereo quality, tracking, comfort, latency and performance
remain `NOT_RUN`. No measured hardware run means no claim of a performance gain.

## Input record for `analyze_performance`

Each `baseline` and `candidate` is an object containing `identity`, `metrics`,
and optional `optimizations` and `dlss`. Required identity keys are:
`project`, `source_hash`, `scene`, `camera`, `resolution`, `quality`, `hardware`,
`driver`, `engine`, `plugin`, `runtime`, `stereo`, `sample_window_seconds`,
`warmup_seconds`, and `capture_mode`. Use `[width, height]` positive integers for
`resolution`, `mono` or `stereo` for the stereo mode and explicit nonempty
hardware/quality data. Extra identity keys also participate in comparison.
Keep the single intended optimization difference under `optimizations`; do not
remove actual changes to scene, camera or hardware from `identity` to obtain a
`comparable` result.

Metric keys are `cpu_ms`, `gpu_ms`, `frame_ms`, `render_fps`, `display_fps` and
`latency_ms`. Each available metric supplies positive finite `samples`, `source`
and optional matching `unit` (`ms` or `fps`). Missing metrics can be omitted or
explicitly explained:

```json
{
  "gpu_ms": {"samples": null, "reason": "GPU timing unavailable in this capture"},
  "latency_ms": {"samples": null, "reason": "No supported latency instrument was used"}
}
```

Feed exported real samples into measured records. The analyzer returns mean,
p50/p95/p99 using linear interpolation over sorted samples and independent metric
deltas when every declared condition matches. It does not capture measurements,
prove statistical significance or attest to supplied files.

Optional `dlss` records are keyed separately by `sr`, `dlaa`, `rr` and `fg`.
Each needs `status` and `reason`; a claimed supported/unsupported result also
needs an official `source_url`, timezone-aware `checked_at` (within seven days and
never future-dated) and `versions` whose `engine`, `plugin`, `runtime`, `hardware`
and `driver` match identity. A stereo support claim additionally
needs `stereo_compatible: true` and official `stereo_source_url`. Incomplete
records become `unknown`. These are caller-supplied evidence references, not
automatic official-content verification or permission to activate anything.
The standalone implementation is `scripts/spatiallabs_performance.py`; use the
public read-only MCP wrapper and its declared schema rather than calling private
helpers or treating caller-supplied records as automatic machine detection.
