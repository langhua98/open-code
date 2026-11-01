---
title: ComfyUI
emoji: 🎨
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
suggested_hardware: t4-small
suggested_storage: small
startup_duration_timeout: 1h
pinned: false
---

# ComfyUI（Hugging Face Docker Space）

把这个文件夹的内容上传到一个 **Docker** Space，就是一个带 ComfyUI-Manager 的完整 ComfyUI 网页界面。

## 部署步骤

1. 打开 <https://huggingface.co/new-space>：
   - SDK 选 **Docker**，模板选 **Blank**。
   - **Visibility 选 Private**。ComfyUI 自己没有登录密码，公开的话谁都能用你的 GPU，还能通过 Manager 装插件、跑代码。私有 Space 只有登录了你 HF 账号的浏览器能打开。
   - Hardware 选一个 GPU（见下面的费用）。**ZeroGPU 不支持 Docker Space**，免费的 CPU 跑不动出图。
2. Space 页面 → **Files** → **Add file → Upload files**，把本文件夹里的 5 个文件（`README.md`、`Dockerfile`、`start.sh`、`fetch_models.py`、`models.txt`）传上去。或者在电脑上用 `hf upload <用户名>/<space名> spaces/comfyui . --repo-type space`。
3. （建议）**Settings → Persistent storage** 开一档存储。开了以后模型、插件、工作流、出图都存在 `/data`，重启不丢；不开的话每次重启都要重新下模型。
4. （可选）**Settings → Variables and secrets**：
   - Secret `HF_TOKEN`：下载需要授权的模型（比如 FLUX.1-dev）时要用。
   - Variable `COMFYUI_ARGS`：额外的 ComfyUI 启动参数，比如 `--lowvram`。
5. 第一次构建大约 10–20 分钟（要装 PyTorch）。状态变成 Running 后，直接在 Space 页面里用 ComfyUI。

## 加模型

改 `models.txt`，一行一个：`<models 下的子文件夹> <HF 仓库> <仓库里的文件路径>`。Space 启动时会自动下载缺的，已经有的跳过。也可以在 ComfyUI-Manager 里直接装模型和自定义节点。

## 费用（按小时计，以 <https://huggingface.co/pricing> 为准）

| 硬件 | 显存 | 价格 | 适合 |
| --- | --- | --- | --- |
| T4 small | 16 GB | 约 $0.40/小时 | SD1.5、SDXL |
| L4 | 24 GB | 约 $0.80/小时 | SDXL、FLUX（fp8） |
| A10G small | 24 GB | 约 $1.00/小时 | 同上，更快 |

- 只在 Running 时计费。**Settings → Sleep time** 设短一点（比如 15 分钟），不用时自动休眠就不花钱；下次打开会冷启动几分钟。
- 持久存储另收月费（small 20 GB 约 $5/月，以设置页显示为准）。

## 注意

- 通过 Manager 装的自定义节点代码存在 `/data/comfyui/custom_nodes`，会保留；但它们额外 pip 装的依赖在镜像重建后会丢。常用插件的依赖最好写进 `Dockerfile`。
- 升级 ComfyUI：改 `Dockerfile` 里的 `COMFYUI_REF`，重新上传，Space 会自动重建。
