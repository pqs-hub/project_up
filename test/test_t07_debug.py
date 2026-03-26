#!/usr/bin/env python3
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.transforms import create_engine

TEST_CODE = """
module test(input a, b, c, d, output x, y, z, w);
    assign x = a;
    assign y = b;
    assign z = c;
    assign w = d;
endmodule
""".strip()

engine = create_engine()
candidates = engine._get_candidates_for_transform(TEST_CODE, 'T07')

print(f"T07候选数量: {len(candidates)}")
for idx, pair in enumerate(candidates):
    print(f"\n候选{idx}: {pair}")
    print(f"  类型: {type(pair)}")
    if isinstance(pair, tuple):
        i, j = pair
        print(f"  对: ({i}, {j})")
