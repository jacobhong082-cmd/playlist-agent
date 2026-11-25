"""필요한 모델만 받기 (작사·작곡 도우미 LM 은 빼서 용량 절약)."""
import os, sys
from huggingface_hub import HfApi, snapshot_download

dest = sys.argv[1]
files = HfApi().list_repo_files("ACE-Step/Ace-Step1.5")
print("repo folders:", sorted({f.split("/")[0] for f in files}))
snapshot_download("ACE-Step/Ace-Step1.5", local_dir=dest,
                  ignore_patterns=["acestep-5Hz-lm-*", "acestep-5Hz-lm-*/*", "*.md"])
for root, _, fs in os.walk(dest):
    size = sum(os.path.getsize(os.path.join(root, f)) for f in fs)
    if fs:
        print(f"{root}: {len(fs)} files, {size/1e9:.2f} GB")
