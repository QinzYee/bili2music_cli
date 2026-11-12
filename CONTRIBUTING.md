# 贡献指南

## 开发环境

```bash
git clone https://github.com/QinzYee/bili2music_cli.git
cd bili2music_cli
python -m venv .venv

# Windows
.venv/Scripts/pip install -e ".[dev]"
# macOS / Linux
source .venv/bin/activate && pip install -e ".[dev]"
```

若默认 pip 镜像在构建隔离环境里拉不到 `setuptools`，加官方源：

```bash
pip install -i https://pypi.org/simple -e ".[dev]"
```

## 常用命令

```bash
python -m pytest -q                    # 跑测试（46 个）
python -m bili2music doctor            # 环境自检
python -m bili2music agent-guide       # 查看面向 Agent 的接口约定
python -m build --sdist --wheel --no-isolation   # 本地构建
python -m twine check dist/*           # 校验元数据
```

## 提交前自查

- [ ] `python -m pytest -q` 全绿
- [ ] 改动涉及 CLI 参数时，同步更新 `bili2music/agent_guide.py`（Agent 的权威说明）
- [ ] 改动涉及技能流程时，同步更新 `skills/bili-download/SKILL.md` 和
      `bili2music/skills/bili-download/SKILL.md`（两份必须一致）
- [ ] 没有硬编码的本地绝对路径
- [ ] 没有提交密钥、Cookie、`config.toml`、下载的媒体文件
- [ ] 版本号变更时，同步 `pyproject.toml` 与 `bili2music/__init__.py`
- [ ] 在 `CHANGELOG.md` 补一条记录

## 提交信息

用前缀说明类型，例如：

```
feat: 支持按 BV 号直接下载
fix: 修复风控时未正确返回 v_voucher 提示
docs: 更新安装说明
refactor: 拆分 planner 与 downloader
```

## 设计约束（改动请勿破坏）

1. **确认前绝不下载**：`--dry-run` 出清单，用户确认后才 `plan`。
2. **`--json` 模式不得交互**：stdout 只有一行 JSON，日志走 stderr，绝不等待输入。
3. **降级可用**：大模型不可用时必须回退到规则式问答与排序，不能直接报错退出。
4. **指令随版本**：Agent 的调用约定写在 `agent_guide.py` 里，不依赖外部文档。

## 合规

本项目仅用于下载用户有权访问的内容。请勿用于批量抓取或再分发他人作品。
