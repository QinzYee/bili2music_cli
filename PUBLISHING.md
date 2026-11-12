# 发布指南

把 `bili2music` 发布到 PyPI，让任何人都能 `pipx install bili2music` 使用。

> **状态：0.1.0 已于 2026-11-12 发布成功** — https://pypi.org/project/bili2music/0.1.0/
> 公网全新环境实测可安装，`b2m doctor` 全 OK。
> 后续版本发布照下方「2. 发布」流程走，注意先改版本号。

## 0. 发布前检查清单

- [x] `pyproject.toml` 元数据完整（license / authors / classifiers / keywords）
- [x] `LICENSE` 存在（MIT）
- [x] `twine check` 通过
- [x] 全新 venv 安装后 `b2m doctor` 全部 OK
- [x] 包内无密钥、无 `config.toml`、无下载的媒体文件
- [x] 源码无硬编码绝对路径
- [ ] 注册 PyPI 账号并开启 2FA ← **需要你**
- [ ] 生成 API token ← **需要你**
- [ ] （可选）建 GitHub 仓库并填 `[project.urls]` ← **需要你**

## 1. 注册 PyPI 并生成 token

PyPI 现在**强制要求 2FA**，没有例外。

1. 打开 https://pypi.org/account/register/ 注册（用户名建议用英文，和包名无关）
2. 进 https://pypi.org/manage/account/ 开启 2FA（TOTP App 或安全密钥）
3. 生成 API token：
   - 首次发布：https://pypi.org/manage/account/token/ 选 **「Entire account」**
   - 首次发布成功后，改成 **项目范围 token**（更安全）：项目的 Settings → API tokens
4. **不要**把 token 写进任何文件或 git。用下面任一方式让 twine 读到：

```bash
# 方式 A：环境变量（推荐，临时生效）
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=<你的 pypi token，形如 pypi-AgEI...，此处不要写成真实值>

# 方式 B：~/.pypirc（存到用户目录，权限 0600，绝不入库）
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-xxx

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-yyy
```

> TestPyPI 是独立的演练环境，账号也要单独注册（https://test.pypi.org/account/register/）。
> **首次发布强烈建议先发 TestPyPI 走一遍**，确认安装体验无误再发正式。

## 2. 发布（三条命令）

```bash
# 演练：只构建 + 校验，不上传
./scripts/publish.sh build

# 传到 TestPyPI 试装
./scripts/publish.sh testpypi

# 传到正式 PyPI
./scripts/publish.sh
```

脚本会自动：跑测试 → 构建 sdist + wheel → `twine check` → 上传。
用 `--no-isolation` 构建，因为你的默认 pip 源在构建隔离环境里拉不到 `setuptools`。

## 3. 发布后验证

```bash
pipx install bili2music
b2m doctor
b2m agent-guide | head -20

# 让 AI 接管
b2m skill            # 自动探测已安装的 AI 工具目录
```

## 4. 版本号规则

PyPI **不允许覆盖已上传的版本**，同号重传会直接报错。

```toml
# pyproject.toml
version = "0.1.0"   # 0.1.0 → 0.1.1 → 0.2.0
```

同步修改两处，保持一致：
- `pyproject.toml` 的 `version`
- `bili2music/__init__.py` 的 `__version__`

## 5. 可选但强烈建议：GitHub 仓库 + 自动发布

发布到 PyPI 后，README 里的 `YOUR_GITHUB` 占位和 `[project.urls]` 都需要真实地址。建好仓库后：

1. 填 `pyproject.toml` 里注释掉的 `[project.urls]`（取消注释并改地址）
2. 把 README 中所有 `YOUR_GITHUB` 替换成你的实际 GitHub 用户名
3. 加上 Trusted Publishing（免 token 发布，最安全）：
   - PyPI 项目 Settings → Publishing → 添加 GitHub Actions 为可信发布者
   - 之后打 tag 就自动发布，不再需要 token

## 6. 如果链接 404 / 包被占用

包名 `bili2music` 在撰写本指南时确认**未被占用**。若你发布前被人抢注：

```toml
# 换成备选名（同样未被占用）
name = "bili-to-music-cli"
# 或
name = "b2m"
```

改完记得同步 `README.md` 里的 `pipx install bili2music` 命令。
