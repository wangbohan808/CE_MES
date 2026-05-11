# [WEIGH-106] 称重工位：方案二动态限（μ±σ）与历史持久化
import json
import os
import sys
from typing import List, Optional, Tuple

_DEFAULT_HISTORY_REL = "weigh_106_history.json"


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def history_file_path() -> str:
    """方案二历史文件绝对路径：来自 config.yaml weigh_history_json_path（相对则相对 _base_dir）。"""
    from test_tool import test as _test

    raw = str(getattr(_test.load_cfg, "weigh_history_json_path", "") or "").strip()
    if not raw:
        raw = _DEFAULT_HISTORY_REL
    if os.path.isabs(raw):
        return os.path.normpath(raw)
    return os.path.normpath(os.path.join(_base_dir(), raw))


def _ensure_empty_history_file(path: str) -> None:
    """文件不存在时创建默认 {"weights":[]}；已存在则不改动。"""
    if os.path.exists(path):
        return
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"weights": []}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_history_weights() -> List[float]:
    path = history_file_path()
    _ensure_empty_history_file(path)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        w = data.get("weights")
        if not isinstance(w, list):
            return []
        out: List[float] = []
        for x in w:
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                continue
        return out
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_history_weights(weights: List[float]) -> None:
    path = history_file_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            pass
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"weights": weights}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def window_slice_bounds(t: int, history_len: int) -> Tuple[int, int]:
    """当前判第 t 台（1 起算），history 为已完成的 w_1..w_{t-1}，长度须为 t-1。
    返回 [start, end) 下标，供 history[start:end] 截取参与 μ、σ 的样本。"""
    if history_len != t - 1:
        raise ValueError("history_len must equal t - 1")
    if t - 1 <= 32:
        return 0, t - 1
    return t - 1 - 32, t - 1


def history_window_for_unit_t(t: int, history: List[float]) -> List[float]:
    if len(history) != t - 1:
        return []
    lo, hi = window_slice_bounds(t, len(history))
    return history[lo:hi]


def population_mean_sigma(xs: List[float]) -> Tuple[float, float]:
    """总体均值 μ 与总体标准差 σ（分母 n）。"""
    m = len(xs)
    if m == 0:
        return 0.0, 0.0
    mu = sum(xs) / m
    if m == 1:
        return mu, 0.0
    s = sum((x - mu) ** 2 for x in xs)
    sigma = (s / m) ** 0.5
    return mu, sigma


def scheme2_dynamic_limits(
    t: int, history: List[float]
) -> Optional[Tuple[float, float, float, float]]:
    """第 t 台、已有 history（长度 t-1）时，返回 (lower, upper, mu, sigma)；无法计算则 None。"""
    wnd = history_window_for_unit_t(t, history)
    if not wnd:
        return None
    mu, sigma = population_mean_sigma(wnd)
    return mu - sigma, mu + sigma, mu, sigma
