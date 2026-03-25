#!/usr/bin/env python3
"""
将 data/qualified_samples.json 转换为 evaluate.py 可直接使用的 dataset.json 格式。

输出格式（与 evaluate.py 期望一致）：
[
  {
    "task_id": "q000001",
    "prompt": "<spec 文本>",
    "canonical_solution": "<原始 RTL 代码，模块名为 RefModule>",
    "test": "<testbench 文本，实例化 RefModule + TopModule>"
  },
  ...
]

说明：
- qualified_samples.json 中字段为：
  - spec: 文字描述
  - rtl: 原始实现（模块名各不相同，如 mpc_controller）
  - testbench: 已经写好的自检 testbench（直接实例化该模块）
- 为复用现有 evaluate.py 的“RefModule + TopModule”结构，这里简单做一层包装：
  1) 将原始 rtl 模块名改成统一的 RefModule；
  2) 将 testbench 中对原始模块名的实例化保留，用于后续仿真时与 TopModule 一起编译。

后续流程：
- 针对这个 dataset.json 生成按规则变换后的攻击结果目录（每个 task_id 一条 JSON，含 "final" 字段）。
- 再用 evaluate.py --dataset <本脚本输出> --results <攻击结果目录> 运行 original/adversarial 评估。
"""

import argparse
import json
import re
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def detect_module_name(rtl: str) -> str:
    """从 Verilog 代码中解析第一个 module 名称。"""
    m = re.search(r"\bmodule\s+([A-Za-z_]\w*)\b", rtl)
    if not m:
        raise ValueError("无法在 RTL 中找到 module 声明")
    return m.group(1)


def rewrite_module_name_to_refmodule(rtl: str, orig_name: str) -> str:
    """
    将原始模块名统一改名为 RefModule。
    仅替换 module 声明处的名字，不做全局替换，避免误伤信号名等。
    """
    pattern = rf"(\bmodule\s+){orig_name}(\b)"
    replaced, count = re.subn(pattern, r"\1RefModule\2", rtl, count=1)
    if count == 0:
        # 兜底：如果没替换到，保持原样（后续仿真时依然依据原名实例化）
        return rtl
    return replaced


def load_qualified(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("qualified_samples.json 顶层必须是列表")
    return data


def convert(qualified_path: Path, out_path: Path, start: int = 0, end: Optional[int] = None):
    raw = load_qualified(qualified_path)
    if end is None or end > len(raw):
        end = len(raw)
    raw = raw[start:end]

    out = []
    for idx, item in enumerate(raw):
        spec = item.get("spec", "")
        rtl = item.get("rtl", "")
        tb = item.get("testbench", "")
        if not spec or not rtl or not tb:
            # 跳过不完整样本
            continue

        try:
            orig_name = detect_module_name(rtl)
        except ValueError:
            # 无法解析 module 名时，直接用原始代码
            orig_name = None

        if orig_name:
            canonical = rewrite_module_name_to_refmodule(rtl, orig_name)
        else:
            canonical = rtl

        task = {
            "task_id": f"q{start + idx:06d}",
            "prompt": spec,
            "canonical_solution": canonical,
            "test": tb,
        }
        out.append(task)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"写入 {len(out)} 条任务到 {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Convert qualified_samples.json to dataset.json for evaluate.py")
    parser.add_argument(
        "--input",
        type=str,
        default=str(PROJECT_ROOT / "data" / "qualified_samples.json"),
        help="qualified_samples.json 路径",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "data" / "qualified_dataset.json"),
        help="输出 dataset.json 路径",
    )
    parser.add_argument("--start", type=int, default=0, help="起始样本索引（包含）")
    parser.add_argument("--end", type=int, default=None, help="结束样本索引（不包含）")
    args = parser.parse_args()

    convert(Path(args.input), Path(args.output), start=args.start, end=args.end)


if __name__ == "__main__":
    main()

