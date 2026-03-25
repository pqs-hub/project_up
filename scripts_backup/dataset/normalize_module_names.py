#!/usr/bin/env python3
"""
对数据集做预处理，尽量让 canonical_solution 里的模块名
与 testbench 中实例化的 DUT 名字一致。

策略（保守版）：
- 在 canonical_solution 中用正则提取第一个 module 名称：
    module RefModule (...);
- 在 testbench 中寻找形如：
    <SomeName> dut ( ... );
- 若二者都存在且不同，则把 canonical_solution 里的模块名
  从 <old_name> 全部替换为 <dut_name>（仅限 module 声明处和 endmodule 之前的同名标识）。

注意：
- 原始文件 data/qualified_dataset.json 不会被覆盖，
  会写出一个新的 data/qualified_dataset.normalized.json。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_DIR / "data" / "qualified_dataset.json"
OUT_PATH = PROJECT_DIR / "data" / "qualified_dataset.normalized.json"


MODULE_RE = re.compile(r"\bmodule\s+(\w+)", re.MULTILINE)
DUT_RE = re.compile(r"\b(\w+)\s+dut\s*\(", re.MULTILINE)


def normalize_item(item: dict) -> dict:
    code = item.get("canonical_solution", "")
    tb = item.get("test", "")
    if not code or not tb:
        return item

    m_mod = MODULE_RE.search(code)
    m_dut = DUT_RE.search(tb)
    if not m_mod or not m_dut:
        return item

    old_name = m_mod.group(1)
    dut_name = m_dut.group(1)
    if not old_name or not dut_name or old_name == dut_name:
        return item

    # 只替换 canonical_solution 里的模块名：
    # - module <old_name>
    # - endmodule 前的同名引用（极少，通常没有）
    # 为简单起见，这里使用 \bold_name\b 全文替换，
    # 若你担心误伤，可改成只替换 module 行。
    pattern = re.compile(rf"\b{re.escape(old_name)}\b")
    new_code = pattern.sub(dut_name, code)
    item["canonical_solution"] = new_code
    return item


def main() -> None:
    if not DATA_PATH.exists():
        raise SystemExit(f"dataset not found: {DATA_PATH}")

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    changed = 0

    for item in data:
        before = item.get("canonical_solution", "")
        normalize_item(item)
        after = item.get("canonical_solution", "")
        if before != after:
            changed += 1

    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出规范化数据集: {OUT_PATH}")
    print(f"其中 {changed} 条样本修改了 canonical_solution 的模块名。")


if __name__ == "__main__":
    main()

