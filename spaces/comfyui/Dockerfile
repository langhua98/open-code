# ComfyUI on a Hugging Face Docker Space (needs paid GPU hardware: T4 / L4 / A10G...).
# ZeroGPU does not work with Docker Spaces.
FROM python:3.12-slim

# Bump to upgrade ComfyUI: https://github.com/comfyanonymous/ComfyUI/tags
ARG COMFYUI_REF=v0.43.2
# CUDA 12.8 wheels run on every Spaces GPU (T4, L4, A10G, L40S, A100, H100).
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ffmpeg libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /home/user

RUN git clone --depth 1 --branch "$COMFYUI_REF" https://github.com/comfyanonymous/ComfyUI.git app
RUN pip install --user torch torchvision torchaudio --index-url "$TORCH_INDEX" \
 && pip install --user -r app/requirements.txt -r app/manager_requirements.txt huggingface_hub

COPY --chown=user models.txt start.sh fetch_models.py ./

EXPOSE 7860
CMD ["bash", "start.sh"]
