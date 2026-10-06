---
description: Run the GPU job on Kaggle (T4 x2), read the logs, fix and retest
---
Run this project's GPU job on Kaggle and act on the result.

Arguments: `$ARGUMENTS`
- Empty: run `[job].command` from kgpu.toml.
- Starting with `--`: pass them through, e.g. `/gpu -- python src/infer.py --limit 8` runs that command.
- Anything else: a description of what to test; pick the command yourself.

GPU quota right now:
!`tools/kgpu quota 2>&1 | tail -n 4`

Steps:
1. Before spending GPU time, run cheap local checks on what changed (for example `python -m py_compile <files>` or the CPU tests).
2. Start the run with `tools/kgpu run --no-follow` (plus `-- <command>` when needed). Give the bash call a timeout of 1800000 ms.
3. Exit code 75 means the job is still running on Kaggle: run `tools/kgpu wait --no-follow` with the same timeout until it finishes. Never start a second run while one is pending.
4. Read `runs/latest/kgpu_result.json`, `runs/latest/kgpu.log` and the relevant files in `runs/latest/outputs/`. If there is no result file, read `runs/latest/console.txt`.
5. Report in a few lines: success or failure, exit code, duration, GPUs, key metrics or the root-cause error.
6. If it failed and the cause is clear, fix the code, re-check locally and run again. Stop after 3 GPU runs for this request, or earlier when the fix is unclear, and explain what you found.
