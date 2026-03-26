"""从 core/transforms.py 加载并导出符号。"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从 core.transforms 导入需要的符号
from core.transforms import (
    create_engine,
    VerilogObfuscationEngine,
    VerilogStructure,
    Transform,
    analyze,
    Selectors
)

# 导出符号
__all__ = [
    'create_engine',
    'VerilogObfuscationEngine', 
    'VerilogStructure',
    'Transform',
    'analyze',
    'Selectors'
]
