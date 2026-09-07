#!/usr/bin/env python3
"""
一键部署到 Hugging Face Spaces (Docker)
用法:
    python deploy_hf.py <space_id>
    # 例如: python deploy_hf.py zengjun2004/western-theory-ai  （把 zengjun2004 换成你的 HF 用户名/组织）

前置要求:
    1. 已登录 Hugging Face 命令行 (huggingface_hub): 安装并执行
       pip install huggingface_hub
       huggingface-cli login
    2. 已在 huggingface.co 创建同名 Space (SDK 选 Docker，也可留空由下方脚本自动建)
流程:
    1. 将最新 wiki-site/docs 同步到 hf-space/wiki-site/docs
    2. 用 huggingface_hub.create_repo 创建 Space(Docker)
    3. 上传 hf-space 目录下所有文件
"""
import os, shutil, sys, pathlib, tempfile

ROOT = pathlib.Path(__file__).parent.resolve()
SPACE_DIR = ROOT / "hf-space"
DOCS_SRC = ROOT / "wiki-site" / "docs"
DOCS_DST = SPACE_DIR / "wiki-site" / "docs"


def sync_docs():
    """把最新 docs 同步进 hf-space（先清空再复制，保证与源码一致）"""
    print("[1/3] 同步 wiki-site/docs → hf-space/wiki-site/docs ...")
    if DOCS_DST.exists():
        shutil.rmtree(DOCS_DST)
    DOCS_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DOCS_SRC, DOCS_DST)
    n = sum(1 for _ in DOCS_DST.rglob("*") if _.is_file())
    print(f"      已同步 {n} 个文件")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    space_id = sys.argv[1]  # 形如 user/space
    # 去掉可能的 "https://huggingface.co/spaces/"
    space_id = space_id.rstrip("/").replace("https://huggingface.co/spaces/", "")

    sync_docs()

    print(f"[2/3] 创建/定位 Space: {space_id} ...")
    from huggingface_hub import create_repo, upload_folder

    url = create_repo(
        repo_id=space_id,
        repo_type="space",
        space_sdk="docker",
        exist_ok=True,
    )
    print(f"      Space 就绪: {url}")

    print("[3/3] 上传 hf-space 目录 ...")
    upload_folder(
        repo_id=space_id,
        repo_type="space",
        folder_path=str(SPACE_DIR),
        commit_message="deploy: 西方文论 Wiki AI (FastAPI + DeepSeek + 静态站点)",
    )
    print(f"\n✅ 部署完成！访问: {url.replace('/spaces/', '/spaces/')}")
    print("   ⚠️ 记得在 Space 的 Settings → Variables and Secrets 中添加:")
    print("      DEEPSEEK_API_KEY = sk-xxxx")


if __name__ == "__main__":
    main()
