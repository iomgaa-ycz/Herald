# templates/tabular_ml.py
import json
import os
import sys

DATA_DIR = os.environ["HERALD_DATA_DIR"]  # 由沙箱注入，指向赛题 prepared/public/

# === GENE:DATA_START ===
def load_data(config):
    """
    从 DATA_DIR 读取数据。
    返回: {"train": pd.DataFrame, "val": pd.DataFrame,
           "test": pd.DataFrame, "target": np.ndarray}
    """
    pass  # LLM 填充
# === GENE:DATA_END ===

# === GENE:FEATURE_ENG_START ===
def build_features(data, config):
    """
    输入: load_data 的返回值 + config
    返回: {"train": pd.DataFrame, "val": pd.DataFrame, "test": pd.DataFrame}
    """
    pass  # LLM 填充
# === GENE:FEATURE_ENG_END ===

# === GENE:MODEL_START ===
def build_model(config):
    """
    返回: (model_instance, model_type: "xgboost" | "lightgbm" | "catboost" | "nn")
    """
    pass  # LLM 填充
# === GENE:MODEL_END ===

# === GENE:POSTPROCESS_START ===
def build_postprocess(config):
    """
    返回: {"predict_fn": callable, "format_output": callable}
    """
    pass  # LLM 填充
# === GENE:POSTPROCESS_END ===

# === FIXED:EVALUATE ===
# R4: evaluate() 占位实现，保证骨架可直接运行（除 GENE 区域）
# Claude Agent 在生成代码时必须覆盖此实现，明确按锁定指标计算评估值
def evaluate(y_pred, y_true, config):
    """评估模型性能（占位实现，必须由 Claude 明确实现）

    Args:
        y_pred: 模型预测值
        y_true: 真实标签
        config: 执行配置，必须包含 metric_name

    Returns:
        float: 评估分数
    """
    raise NotImplementedError("必须按锁定 metric_name 显式实现 evaluate()")
# === FIXED:EVALUATE_END ===


# === FIXED:TRAIN_LOOP ===
def main(config):
    # 1. 数据加载（从 DATA_DIR 只读引用）
    data = load_data(config)

    # 2. 特征工程
    features = build_features(data, config)

    # 3. 模型构建与训练
    model, model_type = build_model(config)
    model.fit(features["train"], data["target"])

    # 4. 预测与后处理
    postprocess = build_postprocess(config)
    val_pred = postprocess["predict_fn"](model, features["val"])
    test_pred = postprocess["predict_fn"](model, features["test"])
    test_output = postprocess["format_output"](test_pred)

    # 5. 评估
    metric_name = config.get("metric_name")
    if not metric_name:
        raise ValueError("config.metric_name 不能为空")

    metric_value = evaluate(val_pred, data["val_target"], config)

    # 6. 保存 submission（写到 cwd，不碰 DATA_DIR）
    submission_path = os.path.join(os.getcwd(), "submission.csv")

    return {
        "metric_name": metric_name,
        "metric_value": float(metric_value),
        "model_type": model_type,
    }
# === FIXED:TRAIN_LOOP_END ===

# === FIXED:ENTRY ===
if __name__ == "__main__":
    config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    metrics = main(config)
    print(json.dumps(metrics))
# === FIXED:ENTRY_END ===
