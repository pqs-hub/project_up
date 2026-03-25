"""从 transforms.py 加载并导出符号"""
import importlib.util
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "ast_transforms_2",
    _here / "transforms.py",
)
_ast2 = importlib.util.module_from_spec(_spec)
sys.modules["ast_transforms_2"] = _ast2
_spec.loader.exec_module(_ast2)

create_engine = _ast2.create_engine
VerilogObfuscationEngine = _ast2.VerilogObfuscationEngine
VerilogStructure = _ast2.VerilogStructure
Transform = _ast2.Transform
analyze = _ast2.analyze
Selectors = _ast2.Selectors
Filters = _ast2.Filters
extract_comment_insert_points = _ast2._extract_comment_insert_points
AST_TRANSFORM_REGISTRY = _ast2.AST_TRANSFORM_REGISTRY


def load_ast_transforms():
    """返回包含AST_TRANSFORM_REGISTRY的对象"""
    class ASTTransforms:
        AST_TRANSFORM_REGISTRY = _ast2.AST_TRANSFORM_REGISTRY
    return ASTTransforms()
