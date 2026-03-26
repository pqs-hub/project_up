"""Testbench 运行器，用于验证 Verilog 代码功能等价性。"""
import tempfile
import subprocess
from pathlib import Path


class TestbenchRunner:
    """Testbench 运行器类"""
    
    def __init__(self, simulator: str = "iverilog", timeout: int = 30):
        """
        初始化 Testbench 运行器
        
        Args:
            simulator: 仿真器类型，目前支持 "iverilog"
            timeout: 超时时间（秒）
        """
        self.simulator = simulator
        self.timeout = timeout
        self.available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """检查仿真器是否可用"""
        try:
            # 检查 iverilog 是否可用
            result = subprocess.run(
                ["iverilog", "-V"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def run(self, design_code: str, testbench_code: str) -> dict:
        """
        运行 testbench 验证设计代码
        
        Args:
            design_code: 设计代码（RTL）
            testbench_code: 测试台代码
            
        Returns:
            包含验证结果的字典：
            - passed: bool, 是否通过测试
            - error: str, 错误信息（如果有）
            - output: str, 仿真输出
        """
        if not self.available:
            return {
                "passed": False,
                "error": f"Simulator {self.simulator} not available",
                "output": ""
            }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            design_path = tmpdir_path / "design.v"
            tb_path = tmpdir_path / "tb.v"
            out_path = tmpdir_path / "sim.out"
            
            # 写入文件
            design_path.write_text(design_code, encoding="utf-8")
            tb_path.write_text(testbench_code, encoding="utf-8")
            
            # 编译
            compile_cmd = [
                "iverilog",
                "-g2012",
                "-o", str(out_path),
                str(design_path),
                str(tb_path)
            ]
            
            try:
                comp_result = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
            except subprocess.TimeoutExpired:
                return {
                    "passed": False,
                    "error": "Compilation timeout",
                    "output": ""
                }
            except Exception as e:
                return {
                    "passed": False,
                    "error": f"Compilation error: {str(e)}",
                    "output": ""
                }
            
            if comp_result.returncode != 0:
                return {
                    "passed": False,
                    "error": f"Compilation failed: {comp_result.stderr}",
                    "output": comp_result.stdout
                }
            
            # 运行仿真
            try:
                run_result = subprocess.run(
                    ["vvp", str(out_path)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout * 4  # 运行时间更长
                )
            except subprocess.TimeoutExpired:
                return {
                    "passed": False,
                    "error": "Simulation timeout",
                    "output": ""
                }
            except Exception as e:
                return {
                    "passed": False,
                    "error": f"Simulation error: {str(e)}",
                    "output": ""
                }
            
            output = (run_result.stdout or "") + (run_result.stderr or "")
            
            # 判断是否通过
            fail_keywords = ["FAIL", "ERROR", "Simulation timeout", "fatal"]
            passed = run_result.returncode == 0 and not any(kw in output for kw in fail_keywords)
            
            return {
                "passed": passed,
                "error": "" if passed else "Testbench failed",
                "output": output
            }
