"""ACE-Step 1.5 를 GPU 없는 GitHub 서버에 설치 (torch 는 CPU 버전 따로 설치)."""
import subprocess, sys, tomllib
from pathlib import Path

ace = Path(sys.argv[1])
deps = tomllib.loads((ace / "pyproject.toml").read_text())["project"]["dependencies"]
skip = ("torch", "torchvision", "torchaudio", "nano-vllm", "mlx", "gradio", "tensorboard", "lightning", "lycoris")
keep = []
for d in deps:
    name = d.split(";")[0].strip()
    marker = d.split(";", 1)[1] if ";" in d else ""
    base = name.split("[")[0].split("=")[0].split(">")[0].split("<")[0].split("!")[0].strip().lower()
    if base in skip or base.startswith("torch") and base != "torchao":
        continue
    if "darwin" in marker and "!=" not in marker:
        continue
    if "aarch64" in marker and "!=" not in marker:
        continue
    keep.append(name)
print("installing:", keep)
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *keep])
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "-e", str(ace)])
