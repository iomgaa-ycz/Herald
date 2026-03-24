# 修复 Workspace 数据链接路径（兼容多数据源）

## Context

Workspace 在创建符号链接时需要兼容两种竞赛数据源：

1. **mle-bench 竞赛**：`{competition_dir}/prepared/public/` 结构，`private/` 数据不可暴露
2. **N1eBanG 竞赛**：直接是真实地址，无 `prepared/public` 子目录

**逻辑**：
- 优先检查 `prepared/public/` 是否存在
- 存在 → 链接 `prepared/public/` 内容
- 不存在 → 直接链接根目录内容

---

## Proposed Changes

**文件**: [core/workspace.py](core/workspace.py)

```python
# [MODIFY] _link_competition_data 方法（第 75-82 行）
def _link_competition_data(self, competition_dir: Path) -> None:
    """软链接竞赛数据到 data/ 目录。

    优先链接 prepared/public/ 中的内容（mle-bench 格式），
    若不存在则直接链接根目录（N1eBanG 格式）。
    """
    src = Path(competition_dir).expanduser().resolve()

    # 检查是否存在 prepared/public/ 子目录
    public_dir = src / "prepared" / "public"
    data_src = public_dir if public_dir.exists() else src

    for item in data_src.iterdir():
        dst = self.data_dir / item.name
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(item)
```

---

## Verification Plan

```bash
# 1. 清理旧工作空间
rm -rf workspace/aerial-cactus

# 2. 测试 mle-bench 格式（有 prepared/public）
conda run -n herald python -m core.main --run_workspace_dir workspace/aerial-cactus --run_competition_dir ~/.cache/mle-bench/data/aerial-cactus-identification

# 3. 验证 data/ 目录内容（应只有 public 数据）
ls -la workspace/aerial-cactus/data/
# 预期：description.md, train.csv, test.zip 等（无 .zip 和 prepared）
```

---

## Files to Modify

| 文件 | 操作 | 变更内容 |
|-----|------|---------|
| `core/workspace.py` | MODIFY | 修改 `_link_competition_data()` 添加兼容逻辑 |
