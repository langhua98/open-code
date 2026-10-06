# open-code：手机 + Codespaces + OpenCode + Kaggle GPU

在手机上写 AI 工程：代码和 [OpenCode](https://github.com/anomalyco/opencode) 跑在 GitHub Codespaces 里；需要 GPU 时，一条命令把代码发到 Kaggle 的免费 T4 ×2 上运行，再把日志和结果拉回来。OpenCode 读日志、改代码、再测试，形成闭环。

```
📱 手机浏览器
      │
      ▼
GitHub Codespaces ─────────────────────────────────┐
  工程代码 · OpenCode（Web 界面：4096 端口）· Git · 终端  │
      │                                             │
      │ tools/kgpu run（需要 GPU 时）                 │ 读日志 → 改代码 → 再测试
      ▼                                             │
Kaggle（T4 ×2）                                      │
  在私有 Notebook 里运行工程代码：推理 / 测试          │
      │                                             │
      ▼                                             │
runs/<编号>/：日志、结果、输出文件 ───────────────────┘
```

## 一次性准备（全程可以在手机浏览器里完成）

### 1. Kaggle

1. 账号需要完成**手机号验证**，否则不能用 GPU，也不能联网（Settings → Phone verification）。
2. 打开 <https://www.kaggle.com/settings/api>，在 **API** 一栏点击 **Generate New Token**，复制生成的 token（以 `KGAT_` 开头）。

### 2. 创建 Codespace，同时填入 token

打开 <https://codespaces.new/langhua98/open-code>。页面上有一栏 **KAGGLE_API_TOKEN**，把 token 粘贴进去，然后点击 **Create codespace**。GitHub 会把它保存成你的 Codespaces secret，以后新建的 Codespace 都会自动带上。

另一种方式是先在 <https://github.com/settings/codespaces> 里点 **New secret** 手动添加：Name 填 `KAGGLE_API_TOKEN`，Repository access 选 `langhua98/open-code`。可选的 `OPENCODE_SERVER_PASSWORD` 也可以用同样方式添加，作为 Web 界面的密码。

Token 只存在 Codespaces secrets 里，**不要写进仓库里的任何文件**。

第一次创建大约需要 3–5 分钟，会自动完成：

- 安装 OpenCode 和 Kaggle CLI；
- 用你的 token 登录 Kaggle，并打印本周 GPU 配额；
- 在 4096 端口启动 OpenCode 的 Web 界面。

## 日常使用

### 打开 OpenCode

- **手机推荐用 Web 界面**：在 Codespace 底部的 **端口（Ports）** 面板找到 `4096 (OpenCode Web)`，点地球图标在浏览器中打开。地址形如 `https://<codespace名>-4096.app.github.dev`。端口默认是私有的，只有登录了 GitHub 的你自己能访问。如果设置了 `OPENCODE_SERVER_PASSWORD`，用户名填 `opencode`。
  - **每个浏览器第一次打开时**：点「添加项目」（或输入框下方的「新建项目」），在搜索框输入 `/workspaces/open-code`，选中第一项。之后这个浏览器会记住这个项目。
- **或者在终端里运行** `opencode`，进入终端界面（TUI）。
- **模型**：不做任何配置，也能直接用 OpenCode Zen 的免费模型（默认是 Big Pickle）。免费模型偶尔会提示 `Rate limit exceeded`：点输入框下方的模型名，换一个免费模型（例如 Nemotron 3 Ultra Free）就行。想要稳定，可以在 OpenCode 里输入 `/connect` 接入 DeepSeek、Kimi、智谱、GitHub Copilot 等；也可以把对应的 API Key（例如 `DEEPSEEK_API_KEY`）加到 Codespaces secrets 里。

### 在 GPU 上测试：`/gpu`

在 OpenCode 里输入：

```
/gpu                                     # 运行 kgpu.toml 里的默认命令（示例：src/infer.py 模型推理）
/gpu -- python src/gpu_check.py          # 指定这一次要运行的命令
/gpu 测一下 1.5B 模型的推理速度            # 用自然语言描述，让它自己选命令
```

OpenCode 会先在本地做语法检查，然后把代码发到 Kaggle T4 ×2 运行，读取日志和结果。如果失败，它会修改代码再测，单次 `/gpu` 最多跑 3 轮 GPU。

### 也可以直接在终端里用 `kgpu`

```bash
kgpu run                          # 打包当前代码 → Kaggle 运行 → 实时显示日志 → 拉回结果
kgpu run -- python train.py --epochs 1
kgpu run --accelerator none       # 只用 CPU 跑，不消耗 GPU 配额
kgpu push                         # 只提交，不等结果（之后用 kgpu wait 取结果）
kgpu wait                         # 继续等待最近一次运行并拉回结果
kgpu status                       # 最近一次运行的状态
kgpu logs -f                      # 实时查看 Kaggle 控制台日志
kgpu quota                        # 本周 GPU 配额
```

每次运行的结果保存在 `runs/<编号>/`，`runs/latest` 永远指向最新一次：

| 文件 | 内容 |
| --- | --- |
| `kgpu.log` | 运行时打印的所有内容 |
| `kgpu_result.json` | 退出码、耗时、GPU 型号、每一步的退出码 |
| `outputs/` | 代码写到 `outputs/` 目录（或 `$KGPU_OUTPUT_DIR`）的文件 |
| `console.txt` | Kaggle 的原始控制台日志 |

### 代码是怎么到 Kaggle 上的

`kgpu` 把 git 能看到的文件（包括**还没提交的改动**，遵守 `.gitignore`）打包，嵌进一个私有 Kaggle Notebook（`<你的用户名>/open-code-gpu`）里运行，每次运行生成一个新版本。不需要先 commit 或 push；仓库是私有的也没关系。

- 单个文件超过 5 MB 会被跳过。数据集和模型权重请上传成 Kaggle Dataset 或 Model，在 `kgpu.toml` 的 `[sources]` 里声明，运行时会挂载到 `/kaggle/input/`。
- 需要额外安装的包写进 `requirements-gpu.txt`。Kaggle 镜像已经自带 torch、transformers 等常用库。
- 单次运行默认最长 1 小时（`kgpu.toml` 里的 `timeout`）。

## 文件说明

| 路径 | 作用 |
| --- | --- |
| `.devcontainer/` | Codespaces 配置：Python 3.12 + Node，自动安装 OpenCode、Kaggle CLI，启动 Web 界面 |
| `tools/kgpu` | Kaggle GPU 运行器 |
| `kgpu.toml` | Kaggle 运行配置：默认命令、GPU 型号、联网、超时、数据集和模型挂载 |
| `requirements-gpu.txt` | Kaggle 上额外安装的 pip 包 |
| `src/infer.py` | 示例 AI 工程（默认任务）：每张 T4 各加载一份 Qwen2.5-0.5B-Instruct，分摊推理并检查答案，结果写到 `outputs/infer.json` |
| `src/gpu_check.py` | 硬件自检：检查两张 T4 是否都可用，并测 fp16 矩阵乘法速度 |
| `AGENTS.md` | 给 OpenCode 的项目规则：开发闭环、节省 GPU 配额、不泄露密钥 |
| `.opencode/commands/gpu.md` | OpenCode 的 `/gpu` 命令 |
| `opencode.json` | OpenCode 项目配置 |
| `tests/` | `kgpu` 的单元测试：`python3 -m unittest discover -s tests` |

## 额度与注意事项

- **Kaggle GPU**：每周 30 小时，每周刷新，用 `kgpu quota` 查看剩余。把能在 CPU 上验证的都放在本地跑，GPU 只用来跑真正需要它的部分。
- **Codespaces**：GitHub 免费账号每月有 120 核·小时（2 核机器约 60 小时）和 15 GB 存储。闲置 30 分钟会自动停止。不用时到 <https://github.com/codespaces> 停止或删除。
- Kaggle 上的任务不依赖 Codespace：提交之后关掉 Codespace 也没关系，回来后运行 `kgpu wait` 就能取回结果。
- 如果 token 泄露（比如发到了聊天里），到 Kaggle 设置页重新生成，并更新 Codespaces secret。
