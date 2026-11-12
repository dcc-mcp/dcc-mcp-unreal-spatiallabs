"""Inspect retained software SBS files without starting a host or vendor runtime."""

from dcc_mcp_core.skill import skill_entry
from dcc_mcp_core.skills_helper import skill_error, skill_success
from spatiallabs_stereo import inspect_stereo_pair as _run


@skill_entry
def inspect_stereo_pair(pair_path):
    try:
        result = _run(pair_path)
    except (ValueError, OSError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        return skill_error("Stereo evidence check refused", str(exc))
    return skill_success("Stereo files inspected; visual and device acceptance remain separate", **result)


main = inspect_stereo_pair

if __name__ == "__main__":
    from dcc_mcp_core.skills_helper import run_main

    run_main(main)
