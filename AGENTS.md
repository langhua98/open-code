# AGENTS.md

这是一个在 GitHub Codespaces 里用 OpenCode 开发的 AI 工程。Codespaces 没有 GPU：需要 GPU 的推理和测试由 `tools/kgpu` 发到 Kaggle（默认 T4 ×2）运行，结果再拉回 `runs/`。

和用户交流使用简体中文。用户经常在手机上操作，回复要短，先说结论。

## 目录

- `src/`：工程代码。`src/gpu_check.py` 是 GPU 自检示例。
- `tools/kgpu`：Kaggle GPU 运行器（`tools/kgpu --help`）。
- `kgpu.toml`：Kaggle 运行配置，包括默认命令、加速器、超时，以及数据集和模型的挂载。
- `requirements-gpu.txt`：在 Kaggle 上额外需要 pip 安装的包。
- `runs/<run_id>/`：每次 GPU 运行拉回的结果，`runs/latest` 指向最新一次。这个目录不提交到 git。

## 开发闭环

1. 修改代码。
2. 能在本地 CPU 上验证的，先在本地验证（语法检查、单元测试、小数据跑通）。不要为这些占用 GPU。
3. 需要 GPU 时，运行 `tools/kgpu run --no-follow`；要换命令就用 `tools/kgpu run --no-follow -- <命令>`。bash 超时设为 1800000 ms。
   - 退出码 0 表示成功，其他值表示失败。失败时会直接打印日志的最后 40 行。
   - 退出码 75 表示 Kaggle 上还在跑：用 `tools/kgpu wait --no-follow` 继续等，不要重复提交。
4. 读取 `runs/latest/kgpu_result.json`、`runs/latest/kgpu.log` 和 `runs/latest/outputs/`。如果没有 result 文件，就读 `runs/latest/console.txt`（Kaggle 原始日志）。
5. 根据日志修改代码，然后回到第 2 步。

## Kaggle 上的运行环境

- 打包范围：git 已跟踪的文件加上新建但未被忽略的文件（遵守 `.gitignore`，包含未提交的改动）。单个文件超过 5 MB 会被跳过。
- 工作目录是仓库根目录的一份副本。写到 `outputs/`（也就是 `$KGPU_OUTPUT_DIR`）里的文件，会被拉回到 `runs/<run_id>/outputs/`。
- 数据集和模型权重不要放进仓库。把它们上传成 Kaggle Dataset 或 Model，在 `kgpu.toml` 的 `[sources]` 里声明，运行时会以只读方式挂载到 `/kaggle/input/` 下。
- 默认可以联网（`internet = true`），能 pip install，也能从 Hugging Face 下载模型。
- 每次运行默认最长 1 小时（`[kernel].timeout`），可以用 `--timeout` 覆盖。

## 规则

- GPU 配额有限（每周 30 小时，用 `tools/kgpu quota` 查看）。每次运行要尽量短：用小 batch、少步数，只跑需要验证的部分。同一时间只跑一个任务。
- 绝不打印、写入或提交任何密钥。`KAGGLE_API_TOKEN` 只来自环境变量，也就是 Codespaces Secrets。
- 不要把 `runs/` 和 `outputs/` 提交到 git。
