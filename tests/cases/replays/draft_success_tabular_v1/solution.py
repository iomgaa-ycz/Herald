"""Tabular Playground Series - May 2022: 二分类 AUC 优化方案。

策略：LightGBM + XGBoost 5-fold CV 集成，重点特征交互工程。
"""

from __future__ import annotations

import json
import os
import sys
import time
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

warnings.filterwarnings("ignore")

DATA_DIR = os.environ.get("HERALD_DATA_DIR", "/home/yuchengzhang/Code/Herald2/workspace/data")
WORKING_DIR = "/home/yuchengzhang/Code/Herald2/workspace/working"

N_FOLDS = 5
SEED = 42
N_JOBS = 16


# === GENE:DATA_START ===
def load_data(config: dict[str, object]) -> dict[str, object]:
    """从 DATA_DIR 读取训练集和测试集。"""
    print(f"[DATA] 加载数据 from {DATA_DIR}")
    train = pd.read_csv(os.path.join(DATA_DIR, "train.csv"))
    test = pd.read_csv(os.path.join(DATA_DIR, "test.csv"))
    print(f"[DATA] 训练集: {train.shape}, 测试集: {test.shape}")

    target = train["target"].values
    train_id = train["id"].values
    test_id = test["id"].values

    train = train.drop(columns=["id", "target"])
    test = test.drop(columns=["id"])

    return {
        "train": train,
        "test": test,
        "target": target,
        "train_id": train_id,
        "test_id": test_id,
    }
# === GENE:DATA_END ===


# === GENE:FEATURE_ENG_START ===
def build_features(
    data: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    """特征工程：拆分 f_27、构造交互特征。"""
    train = data["train"].copy()
    test = data["test"].copy()

    print("[FEAT] 开始特征工程...")
    t0 = time.time()

    # Phase 1: 拆分 f_27 为 10 个单字符类别特征
    for i in range(10):
        col = f"f_27_{i}"
        train[col] = train["f_27"].str[i]
        test[col] = test["f_27"].str[i]
        # 转换为整数编码 (A=0, B=1, ...)
        train[col] = train[col].apply(lambda x: ord(x) - ord("A"))
        test[col] = test[col].apply(lambda x: ord(x) - ord("A"))

    # f_27 字符求和作为额外特征
    train["f_27_sum"] = sum(train[f"f_27_{i}"] for i in range(10))
    test["f_27_sum"] = sum(test[f"f_27_{i}"] for i in range(10))

    # f_27 唯一字符数
    train["f_27_nunique"] = train[[f"f_27_{i}" for i in range(10)]].nunique(axis=1)
    test["f_27_nunique"] = test[[f"f_27_{i}" for i in range(10)]].nunique(axis=1)

    train = train.drop(columns=["f_27"])
    test = test.drop(columns=["f_27"])

    # Phase 2: 连续特征交互（组间）
    cont_group1 = [f"f_{i:02d}" for i in range(7)]  # f_00 ~ f_06
    cont_group2 = [f"f_{i}" for i in range(19, 27)]  # f_19 ~ f_26

    # 组内统计
    train["cont1_mean"] = train[cont_group1].mean(axis=1)
    test["cont1_mean"] = test[cont_group1].mean(axis=1)
    train["cont1_std"] = train[cont_group1].std(axis=1)
    test["cont1_std"] = test[cont_group1].std(axis=1)

    train["cont2_mean"] = train[cont_group2].mean(axis=1)
    test["cont2_mean"] = test[cont_group2].mean(axis=1)
    train["cont2_std"] = train[cont_group2].std(axis=1)
    test["cont2_std"] = test[cont_group2].std(axis=1)

    # 离散特征统计
    cat_cols = [f"f_{i:02d}" for i in range(7, 19)]
    train["cat_sum"] = train[cat_cols].sum(axis=1)
    test["cat_sum"] = test[cat_cols].sum(axis=1)
    train["cat_mean"] = train[cat_cols].mean(axis=1)
    test["cat_mean"] = test[cat_cols].mean(axis=1)
    train["cat_std"] = train[cat_cols].std(axis=1)
    test["cat_std"] = test[cat_cols].std(axis=1)

    # Phase 3: 选择性两两交互（连续特征组1内部乘积）
    for i in range(len(cont_group1)):
        for j in range(i + 1, len(cont_group1)):
            col = f"inter_{cont_group1[i]}_{cont_group1[j]}"
            train[col] = train[cont_group1[i]] * train[cont_group1[j]]
            test[col] = test[cont_group1[i]] * test[cont_group1[j]]

    # f_28 对数变换（处理大范围值）
    for df in [train, test]:
        df["f_28_abs"] = df["f_28"].abs()
        df["f_28_sign"] = np.sign(df["f_28"])
        df["f_28_log"] = np.sign(df["f_28"]) * np.log1p(df["f_28"].abs())

    print(f"[FEAT] 特征工程完成，最终特征数: {train.shape[1]}，耗时: {time.time() - t0:.1f}s")

    return {
        "train": train,
        "test": test,
    }
# === GENE:FEATURE_ENG_END ===


# === GENE:MODEL_START ===
def get_lgb_params() -> dict:
    """LightGBM 参数。"""
    return {
        "objective": "binary",
        "metric": "auc",
        "boosting_type": "gbdt",
        "learning_rate": 0.05,
        "num_leaves": 127,
        "max_depth": -1,
        "min_child_samples": 50,
        "feature_fraction": 0.7,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "n_jobs": N_JOBS,
        "verbose": -1,
        "seed": SEED,
    }


def get_xgb_params() -> dict:
    """XGBoost 参数。"""
    return {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "learning_rate": 0.05,
        "max_depth": 8,
        "min_child_weight": 50,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "nthread": N_JOBS,
        "seed": SEED,
        "verbosity": 0,
    }
# === GENE:MODEL_END ===


# === FIXED:EVALUATE ===
def evaluate(y_pred: np.ndarray, y_true: np.ndarray, config: dict[str, object]) -> float:
    """AUC 评估。"""
    return roc_auc_score(y_true, y_pred)
# === FIXED:EVALUATE_END ===


# === FIXED:TRAIN_LOOP ===
def main(config: dict[str, object]) -> dict[str, object]:
    """主训练流程：LightGBM + XGBoost 5-fold CV 集成。"""
    print("=" * 60)
    print("Tabular Playground Series - May 2022")
    print(f"目标: 二分类 AUC 最大化, {N_FOLDS}-fold CV")
    print("=" * 60)

    # Phase 1: 数据加载与特征工程
    data = load_data(config)
    features = build_features(data, config)

    X_train = features["train"].values.astype(np.float32)
    X_test = features["test"].values.astype(np.float32)
    y_train = data["target"]
    test_id = data["test_id"]
    feat_names = features["train"].columns.tolist()

    print(f"\n[TRAIN] X_train: {X_train.shape}, X_test: {X_test.shape}")

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)

    # Phase 2: LightGBM 训练
    print("\n" + "=" * 40)
    print("[LGB] 开始 LightGBM 训练...")
    print("=" * 40)

    lgb_params = get_lgb_params()
    lgb_oof = np.zeros(len(y_train))
    lgb_test_preds = np.zeros(len(X_test))

    for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
        t0 = time.time()
        X_tr, X_val = X_train[train_idx], X_train[val_idx]
        y_tr, y_val = y_train[train_idx], y_train[val_idx]

        dtrain = lgb.Dataset(X_tr, label=y_tr, feature_name=feat_names)
        dval = lgb.Dataset(X_val, label=y_val, feature_name=feat_names, reference=dtrain)

        model = lgb.train(
            lgb_params,
            dtrain,
            num_boost_round=3000,
            valid_sets=[dval],
            callbacks=[
                lgb.early_stopping(100),
                lgb.log_evaluation(200),
            ],
        )

        lgb_oof[val_idx] = model.predict(X_val)
        lgb_test_preds += model.predict(X_test) / N_FOLDS

        fold_auc = roc_auc_score(y_val, lgb_oof[val_idx])
        print(f"  [LGB] Fold {fold}: AUC = {fold_auc:.6f}, "
              f"best_iter = {model.best_iteration}, 耗时 {time.time() - t0:.1f}s")

    lgb_cv_auc = roc_auc_score(y_train, lgb_oof)
    print(f"\n[LGB] CV AUC = {lgb_cv_auc:.6f}")

    # Phase 3: XGBoost 训练
    print("\n" + "=" * 40)
    print("[XGB] 开始 XGBoost 训练...")
    print("=" * 40)

    xgb_params = get_xgb_params()
    xgb_oof = np.zeros(len(y_train))
    xgb_test_preds = np.zeros(len(X_test))

    for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
        t0 = time.time()
        X_tr, X_val = X_train[train_idx], X_train[val_idx]
        y_tr, y_val = y_train[train_idx], y_train[val_idx]

        dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=feat_names)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=feat_names)

        model = xgb.train(
            xgb_params,
            dtrain,
            num_boost_round=3000,
            evals=[(dval, "val")],
            early_stopping_rounds=100,
            verbose_eval=200,
        )

        xgb_oof[val_idx] = model.predict(dval)
        dtest = xgb.DMatrix(X_test, feature_names=feat_names)
        xgb_test_preds += model.predict(dtest) / N_FOLDS

        fold_auc = roc_auc_score(y_val, xgb_oof[val_idx])
        print(f"  [XGB] Fold {fold}: AUC = {fold_auc:.6f}, "
              f"best_iter = {model.best_iteration}, 耗时 {time.time() - t0:.1f}s")

    xgb_cv_auc = roc_auc_score(y_train, xgb_oof)
    print(f"\n[XGB] CV AUC = {xgb_cv_auc:.6f}")

    # Phase 4: 集成
    print("\n" + "=" * 40)
    print("[ENS] 模型集成...")
    print("=" * 40)

    # 简单加权平均（根据 CV AUC 分配权重）
    w_lgb = lgb_cv_auc / (lgb_cv_auc + xgb_cv_auc)
    w_xgb = xgb_cv_auc / (lgb_cv_auc + xgb_cv_auc)
    print(f"  权重: LGB={w_lgb:.4f}, XGB={w_xgb:.4f}")

    oof_ensemble = w_lgb * lgb_oof + w_xgb * xgb_oof
    test_ensemble = w_lgb * lgb_test_preds + w_xgb * xgb_test_preds

    ensemble_auc = roc_auc_score(y_train, oof_ensemble)
    print(f"\n[ENS] Ensemble CV AUC = {ensemble_auc:.6f}")

    # Phase 5: 生成提交文件
    submission = pd.DataFrame({"id": test_id, "target": test_ensemble})
    submission_path = os.path.join(WORKING_DIR, "submission.csv")
    submission.to_csv(submission_path, index=False)
    print(f"\n[OUT] 提交文件已保存: {submission_path}")
    print(f"[OUT] 提交文件形状: {submission.shape}")
    print(f"[OUT] 预测值范围: [{test_ensemble.min():.4f}, {test_ensemble.max():.4f}]")

    result = {
        "metric_name": "auc",
        "metric_value": float(ensemble_auc),
        "model_type": "lgb+xgb_ensemble",
        "submission_path": submission_path,
        "lgb_cv_auc": float(lgb_cv_auc),
        "xgb_cv_auc": float(xgb_cv_auc),
    }

    print(f"\n{'=' * 60}")
    print(f"最终结果: AUC = {ensemble_auc:.6f}")
    print(f"{'=' * 60}")

    return result
# === FIXED:TRAIN_LOOP_END ===


# === FIXED:ENTRY ===
if __name__ == "__main__":
    runtime_config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    result = main(runtime_config)
    print(json.dumps(result, ensure_ascii=False))
# === FIXED:ENTRY_END ===
