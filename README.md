# open-code：手机 + HuggingFace + OpenCode + Kaggle GPU

在手机上写 AI 工程：代码和 [OpenCode](https://github.com/anomalyco/opencode) 跑在 HuggingFace Spaces（Docker）里；需要 GPU 时，一条命令把代码发到 Kaggle 的免费 T4 ×2 上运行，再把日志和结果拉回来。OpenCode 读日志、改代码、再测试，形成闭环。

![架构图](docs/architecture.png)

```
📱 手机浏览器
      │
      ▼
HuggingFace Spaces（Docker）────────────────────────────┐
  工程代码 · OpenCode（Web 界面）· Git · 终端               │
      │                                                │
      │ tools/kgpu run（需要 GPU 时）                    │ 读日志 → 改代码 → 再测试
      ▼                                                │
Kaggle（T4 ×2）                                         │
  在私有 Notebook 里运行工程代码：推理 / 测试              │
      │                                                │
      ▼                                                │
runs/<编号>/：日志、结果、输出文件 ───────────────────────┘
```

## 一次性准备（全程可以在手机浏览器里完成）

### 1. Kaggle

1. 账号需要完成**手机号验证**，否则不能用 GPU，也不能联网（Settings → Phone verification）。
2. 打开 <https://www.kaggle.com/settings/api>，在 **API** 一栏点击 **Generate New Token**，复制生成的 token（以 `KGAT_` 开头）。

### 2. DeepSeek

OpenCode 默认用 DeepSeek 官方 API。打开 <https://platform.deepseek.com/api_keys> 创建一个 API key（以 `sk-` 开头），复制下来。账户里要有余额。

### 3. 创建 HuggingFace Space，同时填入 token

打开 <https://huggingface.co/new-space>，创建一个 **Docker Space**（SDK 选 Docker，模板选 Blank）：

1. 空间名（Space name）填 `open-code`（或你喜欢的名字，只能小写字母、数字和连字符）。
2. 把 OpenCode 的部署代码（`Dockerfile` 等）放到这个 Space 的仓库里，让它监听 **7860** 端口（HuggingFace 会把它映射到 Space 的网址）。
3. 打开 Space 页面的 **Settings → Secrets**，点 **Add secret**，把下面两个 token 加进去：
   - `KAGGLE_API_TOKEN`：粘贴第 1 步拿到的 Kaggle token（`KGAT_` 开头）
   - `DEEPSEEK_API_KEY`：粘贴第 2 步拿到的 DeepSeek key（`sk-` 开头）
   - 可选 `OPENCODE_SERVER_PASSWORD`：作为 Web 界面的密码

HuggingFace 会把 secret 存成 Space 的环境变量，代码里通过环境变量读取。Secret 只存在 Space 设置里，**不要写进仓库里的任何文件**。

第一次构建大约需要几分钟，构建完成后 OpenCode 会自动在 Space 里跑起来。以后每次打开这个 Space，都会自动启动。

## 日常使用

### 打开 OpenCode

- **手机用 Web 界面**：浏览器打开你的 Space 网址，形如 `https://<用户名>-open-code.hf.space`（用户名和空间名换成你自己的）。如果设置了 `OPENCODE_SERVER_PASSWORD`，用户名填 `opencode`。
  - **每个浏览器第一次打开时**：点「添加项目」（或输入框下方的「新建项目」），在搜索框输入 Space 里的代码路径（Docker Space 默认是 `/app`，以你 Dockerfile 里的 `WORKDIR` 为准），选中后回车。之后这个浏览器会记住这个项目。
  - **iPhone 上全屏用（推荐）**：在 Safari 里打开上面的网址，点「…」→「共享」→「添加到主屏幕」，开关保持打开，点「添加」。以后点主屏幕上的 OpenCode 图标，打开就是全屏的，没有浏览器的按钮。
    - 主屏幕上的 OpenCode 和 Safari 的存储是分开的，第一次进去要再添加一次项目。
- **免费 CPU Space 会休眠**：HuggingFace 免费 CPU Space 一段时间没有访问会自动休眠，下次打开要等几十秒唤醒；访问时会自动醒来。想让 Space 持续在线，可以升级到付费的 CPU 或 GPU Space。
- **模型**：默认用 DeepSeek 官方 API 的 **DeepSeek V4 Pro**；起标题、写摘要这类小任务用更便宜的 **DeepSeek V4.1 Flash**（`opencode.json` 里的 `model` 和 `small_model`）。key 从 Space 的 secret `DEEPSEEK_API_KEY` 读取。
  - 想省钱，可以点输入框下方的模型名，换成 DeepSeek V4.1 Flash。
  - 如果提示没有 key 或认证失败，检查 Space 的 Secrets 是否已添加、是否已重启；也可以在 OpenCode 里输入 `/connect`，选 DeepSeek，临时粘贴 key。
  - 余额用完时，可以换一个 OpenCode Zen 的免费模型（标着「免费」的），不需要 key。
  - **Mac 本地模型**：模型列表里的 **Mac 本地模型 → Qwen3.5 9B（Mac 本地）**（`mac/qwen3.5:9b`）是 William 的 Mac 上用 Ollama 跑的 qwen3.5:9b（16GB Mac 上写代码最合适的一档，支持工具调用），在 HF Space 里走本机地址 `http://127.0.0.1:7860/mac/v1`（OpenAI 兼容接口）：Mac 上的小程序主动连进 Space，请求从这条连接转给 Mac，不怕 HF 掐掉 Cloudflare、ngrok 这类中转。在别的地方（Codespaces）用，要把 `baseURL` 换成 `https://langhua1998-douyin-proxy.hf.space/mac/v1`。key 从环境变量 `LOCAL_LLM_API_KEY` 读取，值就是 Mac 上 `~/ollama-api/.env` 里的 `API_KEY`：Codespaces 里加成 Codespaces secret，HF Space 上加成 Space secret。默认关掉了思考（`reasoningEffort: none`），回得快。
    - OpenCode 每次光系统提示和工具说明就有一万多 token，Ollama 默认的 4096 上下文装不下，Ollama 官方也建议 OpenCode 用 64K。Mac 上要把 Ollama 的上下文调到 65536（Ollama 设置里的 Context length，或者 `OLLAMA_CONTEXT_LENGTH=65536`），和 `opencode.json` 里的 `limit.context` 对上。
    - Mac 睡眠、关机或断网时，这个模型会直接回一句「⚠️ Mac 本地模型现在连不上…」（`opencode.json` 里带了 `X-Offline-Notice: 1` 头才这样回；不带这个头的程序收到 503），换回 DeepSeek 就行。Mac 合盖用电池会睡眠，要一直能用就插电并打开「接通电源时防止自动睡眠」。
    - 8B 小模型能力有限，适合简单问答、改小段代码；步骤多的活还是用 DeepSeek。
  - GitHub Copilot 已经在 `opencode.json` 的 `disabled_providers` 里隐藏了，因为 Copilot 免费版不包含 Claude Sonnet 这类模型，选了只会报错。以后如果订阅了 Copilot Pro，把 `"github-copilot"` 从这个列表里删掉就能用。

### OpenCode 能用的工具

除了读写文件、运行命令，OpenCode 在这个 Space 里还能用下面这些工具。直接用中文告诉它要做什么就行，它会自己挑工具：

| 工具 | 能做什么 | 可以这样说 |
| --- | --- | --- |
| 浏览器（Playwright） | 打开网页、点按钮、填表、截图 | 「用浏览器打开 example.com，告诉我页面上写了什么」 |
| 网页搜索 | 查最新的资料和报错的解决办法 | 「搜一下这个报错怎么解决」 |
| GitHub 命令 `gh` | 查看和创建 Issue、PR，查看 Actions 运行结果 | 「用 gh 看一下这个仓库最近的 Issue」 |
| Docker | 运行容器 | Space 环境本身需要，见下面 |
| 文档处理库 | 读写 PDF、Word、Excel、PPT，画图表 | 「把这个 Excel 画成折线图」 |
| 技能 | 代码审查、安全检查、上网调研、处理文档 | 「审查一下我的改动」「做个安全检查」 |

- 浏览器工具默认不加载，这样每次请求能少发约 2 万字节的工具说明，更省 token。要用浏览器时照常说「用浏览器……」，OpenCode 会把这一步交给 `browser` 子代理。
- 浏览器截图保存在 `.playwright-mcp/`，生成的文档放在 `outputs/`，这两个目录都不会提交到 git。
- 推送代码、开 PR 之前，OpenCode 会先问你。
- 免费模型用这些工具的本事一般（DeepSeek 好一些）：简单的事情可以，步骤很多的网页操作容易出错。

**怎么更新 Space**：修改 Space 仓库里的代码后 `git push`，HuggingFace 会自动重建并重启；或者在 Space 页面点 **Settings → Factory rebuild** 手动重建。Space 重启会清掉没有放进持久存储的文件（比如聊天记录），建议把需要长期保留的数据放进 Space 的持久存储目录，或及时提交到 git。

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
| `Dockerfile` 等 | HuggingFace Space 的部署配置：在 Space 里跑 OpenCode Web 界面（监听 7860），连上浏览器、`gh`、文档处理库和 Kaggle CLI |
| `docs/` | 手机入口页（GitHub Pages）：<https://langhua98.github.io/open-code/> |
| `tools/web` | 在本地或 Codespaces 里启动 OpenCode 网页版（终端里输入 `web`）的备用脚本 |
| `tools/kgpu` | Kaggle GPU 运行器 |
| `kgpu.toml` | Kaggle 运行配置：默认命令、GPU 型号、联网、超时、数据集和模型挂载 |
| `requirements-gpu.txt` | Kaggle 上额外安装的 pip 包 |
| `src/infer.py` | 示例 AI 工程（默认任务）：每张 T4 各加载一份 Qwen2.5-0.5B-Instruct，分摊推理并检查答案，结果写到 `outputs/infer.json` |
| `src/gpu_check.py` | 硬件自检：检查两张 T4 是否都可用，并测 fp16 矩阵乘法速度 |
| `AGENTS.md` | 给 OpenCode 的项目规则：开发闭环、节省 GPU 配额、不泄露密钥 |
| `.opencode/commands/gpu.md` | OpenCode 的 `/gpu` 命令 |
| `.opencode/skills/` | OpenCode 的技能：代码审查、安全检查、上网调研、处理文档 |
| `opencode.json` | OpenCode 项目配置：默认 DeepSeek 模型、可选的 Mac 本地模型（`mac/qwen3.5:9b`）、隐藏 Copilot、接上浏览器工具（默认不加载，交给 `browser` 代理用）、装上 [Superpowers](https://github.com/obra/superpowers) 技能插件（v6.4.2） |
| `tests/` | `kgpu` 的单元测试：`python3 -m unittest discover -s tests` |

## 额度与注意事项

- **Kaggle GPU**：每周 30 小时，每周刷新，用 `kgpu quota` 查看剩余。把能在 CPU 上验证的都放在本地跑，GPU 只用来跑真正需要它的部分。
- **HuggingFace Space**：免费 CPU Space 一段时间没有访问会休眠；需要持续在线或更多资源时再考虑付费（CPU 或 GPU 按时计费）。持久存储、Secrets 等按需在 Space 设置里配置。
- Kaggle 上的任务不依赖 Space：提交之后关掉 Space 也没关系，回来后运行 `kgpu wait` 就能取回结果。
- 如果 token 泄露（比如发到了聊天里），到对应平台（Kaggle / DeepSeek）的设置页重新生成，并更新 Space 的 Secrets。
