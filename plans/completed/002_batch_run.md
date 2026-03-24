# 手动验证 4 Phase 初始化流程

## Context

用户希望手动运行几个 mle-bench 竞赛，验证 `main.py` 的 4 个初始化 Phase 是否正常工作：
- Phase 1: 配置加载（ConfigManager）
- Phase 2: 工作空间创建（Workspace）
- Phase 3: 数据库初始化（HeraldDB）
- Phase 4: EventBus 初始化

**确认**：main.py 保持单竞赛模式，无需新增批量功能。

---

## Verification Plan

### 验证步骤

```bash
# 1. 激活环境
conda activate herald

# 2. 运行第一个竞赛
python core/main.py --run_workspace_dir workspace/aerial-cactus --run_competition_dir ~/.cache/mle-bench/data/aerial-cactus-identification

# 3. 运行第二个竞赛
python core/main.py --run_workspace_dir workspace/cassava --run_competition_dir ~/.cache/mle-bench/data/cassava-leaf-disease-classification

# 4. 运行第三个竞赛
python core/main.py --run_workspace_dir workspace/dogs-vs-cats --run_competition_dir ~/.cache/mle-bench/data/dogs-vs-cats-redux-kernels-edition
```

### 验证成功标志

每个命令应输出：
```
配置加载完成: workspace_dir=workspace/xxx
工作空间已创建: workspace/xxx
数据库已初始化: workspace/xxx/database/herald.db
事件流系统已初始化
```

### 验证目录结构

```bash
ls workspace/aerial-cactus/
# 预期：data/ working/ history/ logs/ best/ database/

ls workspace/aerial-cactus/database/
# 预期：herald.db
```

---

## Files to Modify

无需修改代码，直接执行验证即可。

---

## Notes

- 当前 `main.py` 已支持 `--run_workspace_dir` 和 `--run_competition_dir` 参数
- 竞赛数据位于 `~/.cache/mle-bench/data/`
