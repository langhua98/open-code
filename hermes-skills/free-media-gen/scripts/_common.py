"""Shared bits for gen_image.py / img2video.py: token lookup, gradio_client, output paths."""
import os
import subprocess
import sys
import time

OUT_DIR = "/home/user"
TOKEN_FILE = os.path.expanduser("~/.hermes/hf_token")
POLLI_KEY_FILE = os.path.expanduser("~/.hermes/pollinations_key")


def read_secret(env, path):
    v = os.environ.get(env, "").strip()
    if v:
        return v
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def hf_token():
    return read_secret("HF_TOKEN", TOKEN_FILE)


def out_path(kind, ext):
    return os.path.join(OUT_DIR, "gen_%s_%s.%s" % (kind, time.strftime("%H%M%S"), ext))


def gradio_client():
    try:
        import gradio_client  # noqa: F401
    except ImportError:
        print("INSTALLING gradio_client", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gradio_client"], check=True)
    from gradio_client import Client, handle_file
    return Client, handle_file


def hf_client(space):
    Client, _ = gradio_client()
    tok = hf_token()
    try:
        return Client(space, token=tok or None, verbose=False)
    except TypeError:  # very old gradio_client
        return Client(space, hf_token=tok or None, verbose=False)


def classify(err):
    """Turn a Space error into one status word the skill knows how to explain."""
    m = str(err)
    low = m.lower()
    if "zerogpu" in low or "gpu quota" in low or "runs limit" in low or "exceeded your" in low:
        return "QUOTA_EXCEEDED", m
    if "nsfw" in low or "safety" in low or "inappropriate" in low:
        return "BLOCKED", m
    return "FAILED", m
