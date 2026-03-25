# simulator.py
import tempfile
import subprocess
from pathlib import Path


def simulate_verilog(verilog_code: str, testbench: str) -> bool:
    """
    用 iverilog + vvp 仿真一条样本。

    - verilog_code: dataset["canonical_solution"]，一个完整的 RefModule
    - testbench:    dataset["test"]，一个完整的 testbench（内部会输出 PASS/FAIL）

    判定规则（可根据你 testbench 的约定微调）：
    - 编译失败 / 运行超时 → False
    - 输出中包含 "FAIL" 或 "ERROR" 或 "Simulation timeout" → False
    - 否则视为 True
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        dut_path = tmpdir_path / "dut.v"
        tb_path = tmpdir_path / "tb.v"
        out_path = tmpdir_path / "sim.out"

        # 写入 RTL 和 testbench
        dut_path.write_text(verilog_code, encoding="utf-8")
        tb_path.write_text(testbench, encoding="utf-8")

        # 1) iverilog 编译（使用 -g2012 启用 SystemVerilog 2012）
        compile_cmd = [
            "iverilog",
            "-g2012",
            "-o",
            str(out_path),
            str(dut_path),
            str(tb_path),
        ]
        try:
            comp = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            return False

        if comp.returncode != 0:
            # 编译失败直接视为仿真失败
            # 需要的话可以把 comp.stdout/comp.stderr 打到日志里
            return False

        # 2) vvp 运行
        try:
            run = subprocess.run(
                ["vvp", str(out_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except Exception:
            return False

        out = (run.stdout or "") + (run.stderr or "")

        # 根据你的 testbench 约定判定：
        # - 有 FAIL / ERROR / Simulation timeout → 失败
        # - 否则认为通过
        fail_keywords = ["FAIL", "ERROR", "Simulation timeout"]
        if any(kw in out for kw in fail_keywords):
            return False

        return run.returncode == 0