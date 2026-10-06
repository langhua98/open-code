"""GPU smoke test: confirms every visible GPU is usable and measures fp16 matmul speed.

Run it on Kaggle with `tools/kgpu run`. Writes outputs/gpu_check.json.
"""

import json
import os
import platform
import time


def main() -> int:
    out_dir = os.environ.get("KGPU_OUTPUT_DIR", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    report = {"python": platform.python_version(), "devices": []}

    try:
        import torch
    except ImportError:
        print("torch is not installed")
        return write(out_dir, report, 1)

    report["torch"] = torch.__version__
    report["cuda"] = torch.version.cuda
    count = torch.cuda.device_count()
    print(f"torch {torch.__version__}, CUDA {torch.version.cuda}, {count} GPU(s) visible")
    if count == 0:
        print("No CUDA device visible. Is the accelerator enabled in kgpu.toml?")
        return write(out_dir, report, 1)

    size, repeats = 4096, 20
    for index in range(count):
        device = torch.device("cuda", index)
        props = torch.cuda.get_device_properties(device)
        a = torch.randn(size, size, device=device, dtype=torch.float16)
        b = torch.randn(size, size, device=device, dtype=torch.float16)
        a @ b  # warm-up so cuBLAS setup is not timed
        torch.cuda.synchronize(device)
        start = time.perf_counter()
        for _ in range(repeats):
            a @ b
        torch.cuda.synchronize(device)
        seconds = time.perf_counter() - start
        tflops = repeats * 2 * size**3 / seconds / 1e12
        memory_gb = props.total_memory / 1024**3
        report["devices"].append(
            {"index": index, "name": props.name, "memory_gb": round(memory_gb, 1), "fp16_tflops": round(tflops, 1)}
        )
        print(f"cuda:{index} {props.name}, {memory_gb:.1f} GiB, fp16 matmul {tflops:.1f} TFLOPS")

    return write(out_dir, report, 0)


def write(out_dir: str, report: dict, code: int) -> int:
    report["ok"] = code == 0
    with open(os.path.join(out_dir, "gpu_check.json"), "w") as f:
        json.dump(report, f, indent=2)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
