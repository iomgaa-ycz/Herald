"""Tabular 任务 Genome 模板。"""

from __future__ import annotations

import json
import os
import sys

DATA_DIR = os.environ["HERALD_DATA_DIR"]


# === GENE:DATA_START ===
def load_data(config: dict[str, object]) -> dict[str, object]:
    """从 DATA_DIR 读取数据并返回训练、验证、测试集合。"""
    pass  # LLM 填充


# === GENE:DATA_END ===


# === GENE:FEATURE_ENG_START ===
def build_features(
    data: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    """执行特征工程并返回可供训练和预测的特征。"""
    pass  # LLM 填充


# === GENE:FEATURE_ENG_END ===


# === GENE:MODEL_START ===
def build_model(config: dict[str, object]) -> tuple[object, str]:
    """构建模型并返回模型实例与模型类型。"""
    pass  # LLM 填充


# === GENE:MODEL_END ===


# === GENE:POSTPROCESS_START ===
def build_postprocess(config: dict[str, object]) -> dict[str, object]:
    """返回预测函数与提交结果格式化函数。"""
    pass  # LLM 填充


# === GENE:POSTPROCESS_END ===


# === FIXED:EVALUATE ===
def evaluate(y_pred: object, y_true: object, config: dict[str, object]) -> float:
    """按锁定指标评估验证集表现。"""
    raise NotImplementedError("必须按锁定 metric_name 显式实现 evaluate()")


# === FIXED:EVALUATE_END ===


# === FIXED:TRAIN_LOOP ===
def main(config: dict[str, object]) -> dict[str, object]:
    """最小训练主流程骨架。"""
    data = load_data(config)
    features = build_features(data, config)

    model, model_type = build_model(config)
    model.fit(features["train"], data["target"])

    postprocess = build_postprocess(config)
    val_pred = postprocess["predict_fn"](model, features["val"])
    test_pred = postprocess["predict_fn"](model, features["test"])
    test_output = postprocess["format_output"](test_pred)

    metric_name = config.get("metric_name")
    if not metric_name:
        raise ValueError("config.metric_name 不能为空")

    val_target = data.get("val_target")
    metric_value = None
    if val_target is not None:
        metric_value = float(evaluate(val_pred, val_target, config))

    submission_path = os.path.join(os.getcwd(), "submission.csv")
    if hasattr(test_output, "to_csv"):
        test_output.to_csv(submission_path, index=False)

    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "model_type": model_type,
        "submission_path": submission_path,
    }


# === FIXED:TRAIN_LOOP_END ===


# === FIXED:ENTRY ===
if __name__ == "__main__":
    runtime_config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(main(runtime_config), ensure_ascii=False))


# === FIXED:ENTRY_END ===
