from __future__ import annotations
import json
import os


def load_config(name: str, config_dir: str) -> dict:
    """加载配置：优先 {name}.yaml（需 pyyaml），否则 {name}.json。

    自动忽略以 "_" 开头的键（这些是给人看的说明，不参与计算）。
    """
    yaml_path = os.path.join(config_dir, f"{name}.yaml")
    json_path = os.path.join(config_dir, f"{name}.json")
    if os.path.exists(yaml_path):
        try:
            import yaml
            with open(yaml_path, encoding="utf-8") as f:
                return _strip(yaml.safe_load(f))
        except ImportError:
            pass  # 未装 pyyaml，回退到 json
    if not os.path.exists(json_path):
        return {}
    with open(json_path, encoding="utf-8") as f:
        return _strip(json.load(f))


def _strip(d: dict) -> dict:
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if not str(k).startswith("_")}
