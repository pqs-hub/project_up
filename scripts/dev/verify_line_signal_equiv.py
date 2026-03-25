#!/usr/bin/env python3
"""
验证：用 target_line/target_signal 应用变换 与 用 target_token（nth_occurrence）应用变换 结果一致。
对每个有候选的规则，取第 k 个候选：先按 target_token=k 应用得 result_a，
再 get_target_line_signal(code, tid, k) 得 (line, sig)，按 target_line=line, target_signal=sig 应用得 result_b，比较 result_a == result_b。
"""
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from ast_transforms_loader import create_engine


def _seed_for(code: str, tid: str, k: int) -> None:
    """固定随机种子，使 T20 等带 random 的变换两次应用结果可比。"""
    random.seed((hash(code) & 0x7FFFFFFF) + hash(tid) + k)

# 多段样本：覆盖 always、assign、 ternary、端口等，便于多个规则有候选
SAMPLE_MODULES = [
    """module RefModule (
  input clk,
  input rst,
  input [1:0] sel,
  output reg [7:0] out
);
  always @(posedge clk) begin
    if (rst) out <= 0;
    else out <= sel[0] ? 8'd1 : 8'd0;
  end
endmodule""",
    """module RefModule (
  input a,
  input b,
  input c,
  output wire y
);
  wire t = a & b;
  assign y = c ? t : 1'b0;
  assign out2 = a | b;
endmodule""",
    """module RefModule (
  input [7:0] x,
  input [7:0] y,
  output wire [7:0] s
);
  assign s = x + y;
  assign p = x & y;
endmodule""",
]


def main():
    engine = create_engine()
    all_tids = sorted(engine.registry.keys())
    failed = []
    passed = []
    skipped = []

    for code in SAMPLE_MODULES:
        for tid in all_tids:
            candidates = engine._get_candidates_for_transform(code, tid)
            n = len(candidates)
            if n == 0:
                skipped.append((tid, "no candidates"))
                continue
            for k in range(min(2, n)):  # 每个规则最多测前 2 个候选
                line, sig = engine.get_target_line_signal(code, tid, k)
                if line is None and sig is None:
                    skipped.append((tid, f"k={k} get_target_line_signal returned None"))
                    continue
                _seed_for(code, tid, k)
                # 方式 A：按 target_token=k 应用
                try:
                    result_a = engine.apply_transform(
                        code, tid, target_token=k
                    )
                except Exception as e:
                    failed.append((tid, code[:40], k, f"apply target_token={k} raised: {e}"))
                    continue
                # 解析 back：用 target_line/target_signal 得到的索引应与 k 一致（否则为「多候选同线/同信号」）
                resolved_idx = engine._resolve_target_token(code, tid, line, sig)
                if resolved_idx != k:
                    skipped.append((tid, f"k={k} ambiguous (resolved_idx={resolved_idx}, same line/signal)"))
                    continue
                _seed_for(code, tid, k)
                # 方式 B：仅用 target_line / target_signal，不传 target_token
                params_b = {}
                if line is not None:
                    params_b["target_line"] = line
                if sig:
                    params_b["target_signal"] = sig
                try:
                    result_b = engine.apply_transform(
                        code, tid, target_token=None, **params_b
                    )
                except Exception as e:
                    failed.append((tid, code[:40], k, f"apply line/signal raised: {e}"))
                    continue
                if result_a != result_b:
                    failed.append((
                        tid, code[:40], k,
                        f"result mismatch (by_token vs by_line/signal)",
                    ))
                else:
                    passed.append((tid, k))

    # 去重 skipped（同一规则可能多次无候选）
    skipped_list = sorted(set((t, msg) for t, msg in skipped))
    print("=== 验证 target_line/target_signal 与 target_token 等价 ===\n")
    print(f"通过: {len(passed)} 次 (规则+候选)")
    print(f"失败: {len(failed)} 次")
    print(f"跳过: {len(skipped_list)} 种 (规则+原因)")
    # 跳过原因分类
    no_candidates = [(t, m) for t, m in skipped_list if "no candidates" in m]
    get_none = [(t, m) for t, m in skipped_list if "get_target_line_signal returned None" in m]
    ambiguous = [(t, m) for t, m in skipped_list if "ambiguous" in m]
    print("\n跳过明细:")
    print(f"  - 无候选 (该代码下该规则无适用位置): {len(no_candidates)} 种")
    for t, m in no_candidates:
        print(f"      {t}: {m}")
    print(f"  - get_target_line_signal 返回 (None,None) (候选不足或 k 越界): {len(get_none)} 种")
    for t, m in get_none[:5]:
        print(f"      {t}: {m}")
    if len(get_none) > 5:
        print(f"      ... 共 {len(get_none)} 种")
    print(f"  - 歧义 (多候选同线/同信号，按行号或信号反解出的索引 ≠ k): {len(ambiguous)} 种")
    for t, m in ambiguous[:10]:
        print(f"      {t}: {m}")
    if len(ambiguous) > 10:
        print(f"      ... 共 {len(ambiguous)} 种")
    if failed:
        print("\n失败明细:")
        for tid, code_snip, k, msg in failed[:20]:
            print(f"  {tid} k={k} {msg}")
        if len(failed) > 20:
            print(f"  ... 共 {len(failed)} 条")
    if passed:
        by_tid = {}
        for t, k in passed:
            by_tid.setdefault(t, []).append(k)
        print("\n通过的规则 (示例):")
        for t in sorted(by_tid.keys())[:15]:
            print(f"  {t}: 候选索引 {sorted(set(by_tid[t]))}")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
