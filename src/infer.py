"""Example AI workload: batched LLM inference spread over every visible GPU.

Loads one copy of a small instruct model per GPU, splits the prompts between them,
checks one answer, and writes answers plus throughput to outputs/infer.json.
Swap in your own model, prompts and checks.

    tools/kgpu run                                    # default [job].command
    tools/kgpu run -- python src/infer.py --model Qwen/Qwen2.5-1.5B-Instruct --max-new-tokens 128
"""

import argparse
import json
import os
import threading
import time

PROMPTS = [
    "用一句话解释什么是 Transformer。",
    "Write a Python function is_prime(n) and nothing else.",
    "列出三种降低大模型推理显存占用的方法。",
    "What is the capital of Australia? Answer with the city name only.",
    "把这句话翻译成英文：今天的实验在两张 T4 显卡上完成。",
    "Explain in one sentence what tensor parallelism is.",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    args = parser.parse_args()

    import torch
    import transformers

    out_dir = os.environ.get("KGPU_OUTPUT_DIR", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    devices = [torch.device("cuda", i) for i in range(torch.cuda.device_count())] or [torch.device("cpu")]
    print(f"torch {torch.__version__}, transformers {transformers.__version__}, devices: {[str(d) for d in devices]}")

    start = time.perf_counter()
    tokenizer = transformers.AutoTokenizer.from_pretrained(args.model, padding_side="left")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    # T4 has no fast bfloat16, so run in float16 on GPU.
    dtype = torch.float16 if devices[0].type == "cuda" else torch.float32
    models = [
        transformers.AutoModelForCausalLM.from_pretrained(args.model).to(device=device, dtype=dtype).eval()
        for device in devices
    ]
    load_s = time.perf_counter() - start
    print(f"loaded {args.model} on {len(devices)} device(s) in {load_s:.1f}s")

    shards = [PROMPTS[i :: len(devices)] for i in range(len(devices))]
    results: list = [None] * len(devices)

    def work(index: int) -> None:
        results[index] = generate(models[index], tokenizer, shards[index], devices[index], args.max_new_tokens)

    start = time.perf_counter()
    threads = [threading.Thread(target=work, args=(i,)) for i in range(len(devices))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    gen_s = time.perf_counter() - start

    answers = [item for shard in results for item in shard["answers"]]
    tokens = sum(shard["tokens"] for shard in results)
    for item in answers:
        print(f"\n[{item['device']}] Q: {item['prompt']}\nA: {item['answer']}")

    capital = next(item["answer"] for item in answers if "Australia" in item["prompt"])
    checks = {"capital_is_canberra": "canberra" in capital.lower()}
    report = {
        "model": args.model,
        "devices": [str(d) for d in devices],
        "load_seconds": round(load_s, 1),
        "generate_seconds": round(gen_s, 1),
        "generated_tokens": tokens,
        "tokens_per_second": round(tokens / gen_s, 1),
        "checks": checks,
        "answers": answers,
    }
    with open(os.path.join(out_dir, "infer.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{tokens} tokens in {gen_s:.1f}s = {tokens / gen_s:.1f} tokens/s across {len(devices)} device(s)")
    print(f"checks: {checks}")
    return 0 if all(checks.values()) else 1


def generate(model, tokenizer, prompts: list[str], device, max_new_tokens: int) -> dict:
    import torch

    texts = [
        tokenizer.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True)
        for p in prompts
    ]
    batch = tokenizer(texts, return_tensors="pt", padding=True).to(device)
    with torch.inference_mode():
        output = model.generate(**batch, max_new_tokens=max_new_tokens, do_sample=False)
    new_tokens = output[:, batch["input_ids"].shape[1] :]
    texts = tokenizer.batch_decode(new_tokens, skip_special_tokens=True)
    return {
        "answers": [{"device": str(device), "prompt": p, "answer": t.strip()} for p, t in zip(prompts, texts)],
        "tokens": int((new_tokens != tokenizer.pad_token_id).sum()),
    }


if __name__ == "__main__":
    raise SystemExit(main())
