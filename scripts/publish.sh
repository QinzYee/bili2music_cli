#!/usr/bin/env bash
# 一键发布 bili2music 到 PyPI。
#
# 用法:
#   ./scripts/publish.sh              # 构建 + 校验 + 上传到 PyPI
#   ./scripts/publish.sh testpypi     # 构建 + 校验 + 上传到 TestPyPI（先用这个练手）
#   ./scripts/publish.sh build        # 只构建 + 校验，不上传
#
# 前置条件:
#   1. 在 https://pypi.org/manage/account/token/ 生成 API token
#   2. 写进 ~/.pypirc，或用环境变量 TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-xxx
#   3. 版本号必须比已发布的高（改 pyproject.toml 的 version）
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET="${1:-pypi}"

# 用项目自己的 venv，避免污染系统 Python
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  echo "[x] 找不到 .venv，请先创建：python -m venv .venv && .venv/Scripts/pip install -e '.[dev]'" >&2
  exit 1
fi

echo "==> 清理旧产物"
rm -rf dist build || true

echo "==> 跑测试"
"$PY" -m pytest -q

echo "==> 构建 sdist + wheel"
# 构建隔离环境常拉不到 setuptools，用 --no-isolation 走本地已有依赖
"$PY" -m build --sdist --wheel --no-isolation

echo "==> 校验包元数据"
"$PY" -m twine check dist/*

if [ "$TARGET" = "build" ]; then
  echo "==> 仅构建，未上传。产物在 dist/："
  ls -lh dist/
  exit 0
fi

if [ "$TARGET" = "testpypi" ]; then
  REPO_ARGS="--repository testpypi"
  echo "==> 上传到 TestPyPI（需先在 test.pypi.org 生成 token）"
  echo "    安装验证：pipx install --index-url https://test.pypi.org/simple/ bili2music"
else
  REPO_ARGS=""
  echo "==> 上传到 PyPI 正式环境"
fi

# shellcheck disable=SC2086
"$PY" -m twine upload $REPO_ARGS dist/*

echo "==> 完成。验证安装："
echo "    pipx install bili2music && b2m doctor"
