"""
AST-based Verilog Transformation Engine (Parameterized)
========================================
支持外部参数输入的 Verilog 代码变换引擎，可供 LLM 调用。

核心改进:
  1. TargetTokenHandler 装饰器统一处理候选筛选、索引选择、异常处理
  2. 变换函数只关注"如何修改代码"，不关注"如何找到目标"
  3. Selectors/Filters 类提供可复用的选择和过滤逻辑
  4. 支持外部参数输入，可供 LLM 调用
  5. 保持与原 TRANSFORM_REGISTRY 的完全兼容
"""

from __future__ import annotations
import re
import os
import json
import random
import tempfile
import logging
import inspect
from typing import Optional, List, Dict, Tuple, Any, Sequence, Callable, TypeVar, Generic, Literal
from dataclasses import dataclass, field
from functools import wraps

logger = logging.getLogger(__name__)

# ============================================================================
# pyslang 延迟导入
# ============================================================================

try:
    import pyslang
    HAS_PYSLANG = True
except ImportError:
    pyslang = None  # type: ignore
    HAS_PYSLANG = False

# ============================================================================
# 数据结构：AST 提取结果
# ============================================================================

@dataclass
class PortInfo:
    name: str
    direction: str           # 'input' | 'output' | 'inout'
    width: int               # 位宽，1 表示 1-bit
    range_str: str           # 原始范围字符串 '[7:0]' 或 ''
    range_high: Optional[int] = None
    range_low: Optional[int] = None
    offset: int = 0          # name 在源码中的偏移


@dataclass
class SignalInfo:
    name: str
    kind: str                # 'wire' | 'reg' | 'logic' | 'integer'
    width: int = 1
    offset: int = 0
    range_str: str = ''      # 原始范围字符串 '[7:0]' 或 '' (参数化时保留原文)


@dataclass
class ExprInfo:
    """表达式信息"""
    kind: str                # 'ternary' | 'binary_and' | 'binary_or' | 'other'
    text: str                # 完整表达式文本
    start: int               # 源码起始偏移
    end: int                 # 源码结束偏移
    # ternary 专用
    predicate: str = ""
    pred_start: int = 0
    pred_end: int = 0
    pred_first_id: str = ""  # predicate AST 中第一个 IdentifierName（用于生成 wire 名）
    true_expr: str = ""
    true_start: int = 0
    true_end: int = 0
    false_expr: str = ""
    false_start: int = 0
    false_end: int = 0
    # binary 专用
    left_text: str = ""
    left_start: int = 0
    left_end: int = 0
    op: str = ""
    right_text: str = ""
    right_start: int = 0
    right_end: int = 0


@dataclass
class AssignInfo:
    """赋值语句信息"""
    kind: str                # 'continuous' | 'blocking' | 'nonblocking'
    lhs: str
    rhs: str
    full_text: str
    start: int
    end: int
    rhs_expr: Optional[ExprInfo] = None
    lhs_name: str = ""       # 纯标识符名 (不含位选择)


@dataclass
class AlwaysInfo:
    text: str
    start: int
    end: int
    has_begin_end: bool = False
    nb_assigns: List['AssignInfo'] = field(default_factory=list)  # always 块内的 <= 赋值
    # sensitivity list 信息（由 pyslang AST 填充）
    sensitivity_text: str = ''      # 完整 sensitivity list 文本，如 '@(posedge clk or negedge rst)'
    clk_name: str = ''              # posedge 时钟信号名（如 'clk'），无则为空
    has_posedge: bool = False       # 是否含 posedge
    # body 边界（begin...end 内部的偏移，相对于 code 全局）
    body_start: int = 0             # begin 关键字结束后的偏移
    body_end: int = 0               # 最后一个 end 关键字开始前的偏移
    # body 内容特征（由 pyslang AST 填充）
    has_else: bool = False          # body 顶层是否含 if/else
    has_for: bool = False           # body 顶层是否含 for 循环
    # case 语句信息（由 pyslang AST 填充）
    case_items: List[Tuple[int, int, bool]] = field(default_factory=list)
    # (start_offset, end_offset, is_default) 每个 case 分支的全局偏移


@dataclass
class DeclInfo:
    """位宽声明信息"""
    text: str                # e.g. '[7:0]'
    high: int
    low: int
    start: int               # '[' 的偏移
    end: int                 # ']' 后的偏移
    context: str             # 'port' | 'wire' | 'reg' | 'assign'


@dataclass
class CaseInfo:
    """case 语句块信息（case (...) ... endcase）"""
    start: int               # 源码起始偏移（含 case）
    end: int                 # 源码结束偏移（含 endcase）
    branches: List[Tuple[int, int, bool]] = field(default_factory=list)
    # (start_offset, end_offset, is_default) 每个分支的全局偏移，由 pyslang AST 填充


@dataclass
class CommentInsertPoint:
    """注释插入点"""
    kind: Literal['before_line', 'inline_after', 'after_line']
    line_no: int
    line_text: str
    insert_offset: int


@dataclass
class VerilogStructure:
    """完整的 Verilog 模块结构"""
    code: str
    module_name: str = ""
    module_name_offset: int = 0
    ports: List[PortInfo] = field(default_factory=list)
    signals: List[SignalInfo] = field(default_factory=list)
    assignments: List[AssignInfo] = field(default_factory=list)
    always_blocks: List[AlwaysInfo] = field(default_factory=list)
    expressions: List[ExprInfo] = field(default_factory=list)
    declarations: List[DeclInfo] = field(default_factory=list)
    case_blocks: List[CaseInfo] = field(default_factory=list)  # case (...) ... endcase
    identifiers: Dict[str, str] = field(default_factory=dict)  # name → role

    # 查询接口
    def port_names(self) -> set:
        return {p.name for p in self.ports}

    def signal_names(self) -> set:
        return {s.name for s in self.signals}

    def all_identifiers(self) -> set:
        return self.port_names() | self.signal_names()

    def is_1bit(self, name: str) -> bool:
        for p in self.ports:
            if p.name == name:
                return p.width == 1
        for s in self.signals:
            if s.name == name:
                return s.width == 1
        return True  # 未知 → 保守假定 1-bit

    def get_width(self, name: str) -> int:
        for p in self.ports:
            if p.name == name:
                return p.width
        for s in self.signals:
            if s.name == name:
                return s.width
        return 1

    def ternary_exprs(self) -> List[ExprInfo]:
        return [e for e in self.expressions if e.kind == 'ternary']

    def binary_and_exprs(self) -> List[ExprInfo]:
        return [e for e in self.expressions if e.kind == 'binary_and']

    def binary_or_exprs(self) -> List[ExprInfo]:
        return [e for e in self.expressions if e.kind == 'binary_or']

    def continuous_assigns(self) -> List[AssignInfo]:
        return [a for a in self.assignments if a.kind == 'continuous']


@dataclass
class ParamSpec:
    """单个参数的规范"""
    name: str
    type: Literal['int', 'float', 'str', 'bool', 'choice', 'dict']
    default: Any
    description: str
    choices: Optional[List[Any]] = None  # 用于 'choice' 类型
    min_val: Optional[float] = None      # 用于数值类型
    max_val: Optional[float] = None


@dataclass
class Transform:
    id: str
    name: str
    description: str
    apply_func: Callable
    category: str
    complexity: int
    equivalence_preserving: bool = True
    
    # 新增：参数规范
    params: List[ParamSpec] = field(default_factory=list)
    
    def to_llm_schema(self) -> dict:
        """生成 LLM 可理解的 JSON Schema"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "complexity": self.complexity,
            "equivalence_preserving": self.equivalence_preserving,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "default": p.default,
                    "description": p.description,
                    **({"choices": p.choices} if p.choices else {}),
                    **({"min": p.min_val, "max": p.max_val} if p.min_val is not None else {})
                }
                for p in self.params
            ]
        }


# ============================================================================
# pyslang AST 分析器
# ============================================================================

def _parse_with_pyslang(code: str) -> Optional[VerilogStructure]:
    """用 pyslang 解析 Verilog 代码，提取结构化信息。
    
    同时使用 SyntaxTree（获取源码偏移）和 Compilation（语义求值，支持参数化位宽）。
    """
    if not HAS_PYSLANG:
        return None

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sv', delete=False, encoding='utf-8'
        ) as f:
            f.write(code)
            path = f.name
        try:
            tree = pyslang.SyntaxTree.fromFile(path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    except Exception as e:
        logger.warning(f"[AST] pyslang 解析失败: {e}")
        return None

    root = tree.root
    if not hasattr(root, 'members') or not root.members:
        return None

    # 构建 Compilation 以支持语义求值（参数化位宽等）
    comp_body = None
    try:
        comp = pyslang.Compilation()
        comp.addSyntaxTree(tree)
        comp_root = comp.getRoot()
        top_instances = comp_root.topInstances
        if top_instances:
            comp_body = top_instances[0].body
    except Exception as e:
        logger.debug(f"[AST] Compilation 构建失败，回退到纯语法树模式: {e}")

    vs = VerilogStructure(code=code)

    # 找第一个 ModuleDeclaration
    mod = None
    for m in root.members:
        if str(m.kind) == 'SyntaxKind.ModuleDeclaration':
            mod = m
            break
    if mod is None:
        return vs

    # 模块名
    header = mod.header
    if hasattr(header, 'name'):
        name_tok = header.name
        raw = getattr(name_tok, 'rawText', '') or getattr(name_tok, 'valueText', '')
        vs.module_name = raw.strip()
        loc = getattr(name_tok, 'location', None)
        if loc:
            vs.module_name_offset = loc.offset

    # 端口（优先用 Compilation portList，回退到 JSON 解析）
    if comp_body is not None:
        try:
            _extract_ports_compilation(comp_body, code, vs)
        except Exception:
            _extract_ports_pyslang(mod, code, vs)
    else:
        _extract_ports_pyslang(mod, code, vs)

    # 模块成员
    for member in mod.members:
        kind_str = str(member.kind)
        sr = member.sourceRange
        start_off = sr.start.offset
        end_off = sr.end.offset
        member_text = code[start_off:end_off]

        if kind_str in ('SyntaxKind.NetDeclaration', 'SyntaxKind.DataDeclaration'):
            _extract_signal_decl(member, code, vs, comp_body)
        elif kind_str == 'SyntaxKind.ContinuousAssign':
            _extract_continuous_assign(member, code, vs)
        elif kind_str == 'SyntaxKind.AlwaysBlock':
            info = _analyze_always_block_pyslang(member, code)
            # has_begin_end：always 块的直接 body 是 SequentialBlockStatement（begin...end）
            # 用 body_start > 0 作为判断依据（AST 填充成功说明有顶层 begin...end）
            # 回退：文本检查 always @(...) begin（begin 紧跟 sensitivity list，中间只有空白）
            has_be = info['body_start'] > 0 or bool(
                re.search(r'always\s*@[^;]+\)\s*\bbegin\b', member_text)
                and not re.search(r'always\s*@[^;]+\)\s*\bif\b', member_text)
            )
            vs.always_blocks.append(AlwaysInfo(
                text=member_text, start=start_off, end=end_off,
                has_begin_end=has_be,
                nb_assigns=info['nb_assigns'],
                sensitivity_text=info['sensitivity_text'],
                clk_name=info['clk_name'],
                has_posedge=info['has_posedge'],
                body_start=info['body_start'],
                body_end=info['body_end'],
                has_else=info['has_else'],
                has_for=info['has_for'],
                case_items=info['case_items'],
            ))

    # 位宽声明
    _extract_range_declarations(code, vs)

    # case 语句块（递归遍历语法树）
    _collect_case_blocks_pyslang(mod, vs.case_blocks)

    # 标识符角色映射
    vs.identifiers[vs.module_name] = 'module_name'
    for p in vs.ports:
        vs.identifiers[p.name] = 'port'
    for s in vs.signals:
        vs.identifiers[s.name] = s.kind

    return vs


def _analyze_always_block_pyslang(always_node, code: str) -> dict:
    """从 AlwaysBlock AST 节点提取所有结构信息，返回 dict 供 AlwaysInfo 填充。
    
    提取内容：
    - nb_assigns: 顶层 nonblocking assign（不递归进 if/case 分支）
    - sensitivity_text / clk_name / has_posedge
    - body_start / body_end（全局偏移）
    - has_else / has_for（body 顶层特征）
    - case_items: [(start, end, is_default), ...]
    """
    result = {
        'nb_assigns': [],
        'sensitivity_text': '',
        'clk_name': '',
        'has_posedge': False,
        'body_start': 0,
        'body_end': 0,
        'has_else': False,
        'has_for': False,
        'case_items': [],
    }

    try:
        stmt = getattr(always_node, 'statement', None)
        if stmt is None:
            return result

        # ── Sensitivity list ──────────────────────────────────────────────
        tc = getattr(stmt, 'timingControl', None)
        if tc is not None:
            tc_sr = getattr(tc, 'sourceRange', None)
            if tc_sr:
                result['sensitivity_text'] = code[tc_sr.start.offset:tc_sr.end.offset]
            # 递归找第一个 posedge SignalEventExpression
            def _find_posedge(node):
                kind = str(getattr(node, 'kind', ''))
                if kind == 'SyntaxKind.SignalEventExpression':
                    edge = getattr(node, 'edge', None)
                    if edge and 'PosEdge' in str(edge.kind):
                        sig = getattr(node, 'expr', None)
                        if sig:
                            sig_sr = getattr(sig, 'sourceRange', None)
                            if sig_sr:
                                return code[sig_sr.start.offset:sig_sr.end.offset].strip()
                for attr in ('expr', 'left', 'right', 'expression'):
                    child = getattr(node, attr, None)
                    if child is None:
                        continue
                    child_kind = str(getattr(child, 'kind', ''))
                    if child_kind.startswith('TokenKind'):
                        continue
                    found = _find_posedge(child)
                    if found:
                        return found
                return ''
            clk = _find_posedge(tc)
            if clk:
                result['clk_name'] = clk
                result['has_posedge'] = True

        # ── Body (SequentialBlockStatement) ──────────────────────────────
        body_stmt = getattr(stmt, 'statement', None)
        if body_stmt is None:
            return result

        body_sr = getattr(body_stmt, 'sourceRange', None)
        if body_sr:
            # body_start = 'begin' 关键字之后，body_end = 最后 'end' 之前
            # 用 begin token 的 end offset
            begin_tok = getattr(body_stmt, 'begin', None)
            end_tok = getattr(body_stmt, 'end', None)
            if begin_tok and end_tok:
                begin_loc = getattr(begin_tok, 'location', None)
                end_loc = getattr(end_tok, 'location', None)
                if begin_loc and end_loc:
                    result['body_start'] = begin_loc.offset + len('begin')
                    result['body_end'] = end_loc.offset

        # ── Body items ────────────────────────────────────────────────────
        items = getattr(body_stmt, 'items', None)
        if items is None:
            return result

        for item in items:
            item_kind = str(getattr(item, 'kind', ''))

            # nonblocking assign
            if item_kind == 'SyntaxKind.ExpressionStatement':
                item_sr = getattr(item, 'sourceRange', None)
                if item_sr:
                    text = code[item_sr.start.offset:item_sr.end.offset]
                    if '<=' in text:
                        m = re.match(r'([\w\[\]:]+)\s*<=\s*(.+?)\s*;?\s*$', text.strip(), re.DOTALL)
                        if m:
                            lhs = m.group(1).strip()
                            rhs = m.group(2).strip()
                            lhs_name_m = re.match(r'(\w+)', lhs)
                            result['nb_assigns'].append(AssignInfo(
                                kind='nonblocking',
                                lhs=lhs, rhs=rhs,
                                full_text=text,
                                start=item_sr.start.offset, end=item_sr.end.offset,
                                lhs_name=lhs_name_m.group(1) if lhs_name_m else lhs,
                            ))

            # if/else → has_else：只有真正含 else 分支时才标记
            elif item_kind == 'SyntaxKind.ConditionalStatement':
                else_clause = getattr(item, 'elseClause', None)
                if else_clause is not None:
                    result['has_else'] = True

            # for loop → has_for
            elif item_kind in ('SyntaxKind.ForLoopStatement', 'SyntaxKind.LoopStatement'):
                result['has_for'] = True

            # case statement → 提取分支偏移
            elif 'CaseStatement' in item_kind:
                case_items_node = getattr(item, 'items', None)
                if case_items_node:
                    for branch in case_items_node:
                        branch_kind = str(getattr(branch, 'kind', ''))
                        branch_sr = getattr(branch, 'sourceRange', None)
                        if branch_sr:
                            is_default = branch_kind == 'SyntaxKind.DefaultCaseItem'
                            result['case_items'].append((
                                branch_sr.start.offset,
                                branch_sr.end.offset,
                                is_default,
                            ))

    except Exception as e:
        logger.debug(f"[AST] _analyze_always_block_pyslang 失败: {e}")

    return result


# 保留旧名作为别名，兼容已有调用
def _extract_nb_assigns_pyslang(always_node, code: str) -> List['AssignInfo']:
    return _analyze_always_block_pyslang(always_node, code)['nb_assigns']


def _collect_case_blocks_pyslang(node: Any, out: List[CaseInfo]) -> None:
    """递归遍历 pyslang 语法树，收集 CaseStatement 节点及其分支偏移到 out。"""
    try:
        kind_str = str(getattr(node, "kind", ""))
        if "Case" in kind_str and "Statement" in kind_str:
            sr = getattr(node, "sourceRange", None)
            if sr is not None and hasattr(sr, "start") and hasattr(sr, "end"):
                start_off = getattr(sr.start, "offset", None)
                end_off = getattr(sr.end, "offset", None)
                if start_off is not None and end_off is not None:
                    # 提取分支信息
                    branches = []
                    case_items = getattr(node, "items", None)
                    if case_items:
                        for branch in case_items:
                            branch_kind = str(getattr(branch, "kind", ""))
                            branch_sr = getattr(branch, "sourceRange", None)
                            if branch_sr:
                                is_default = branch_kind == "SyntaxKind.DefaultCaseItem"
                                branches.append((
                                    branch_sr.start.offset,
                                    branch_sr.end.offset,
                                    is_default,
                                ))
                    out.append(CaseInfo(start=start_off, end=end_off, branches=branches))
        for child in getattr(node, "members", []) or []:
            _collect_case_blocks_pyslang(child, out)
        for name in ("body", "statement", "item", "items", "clause"):
            child = getattr(node, name, None)
            if child is None:
                continue
            # pyslang SyntaxList 不是 list/tuple，但可迭代
            try:
                for c in child:
                    _collect_case_blocks_pyslang(c, out)
            except TypeError:
                _collect_case_blocks_pyslang(child, out)
    except Exception:
        pass


def _extract_ports_compilation(comp_body, code: str, vs: VerilogStructure):
    """用 Compilation portList 提取端口信息，支持参数化位宽语义求值。"""
    try:
        port_names_ordered = []
        for p in comp_body.portList:
            port_names_ordered.append(p.name)

        for port_sym in comp_body.portList:
            name = port_sym.name
            if not name:
                continue

            # 方向：从 port symbol 的 direction 属性获取
            direction_raw = str(getattr(port_sym, 'direction', '')).lower()
            if 'out' in direction_raw:
                direction = 'output'
            elif 'inout' in direction_raw:
                direction = 'inout'
            else:
                direction = 'input'

            # 位宽：从内部 net/variable symbol 获取（语义求值后）
            width = 1
            rh, rl = None, None
            range_str = ''
            try:
                # portList 中的 port symbol 的 type 直接包含位宽
                t = port_sym.type
                width = t.bitWidth
                if width > 1:
                    rh, rl = width - 1, 0
                    range_str = f'[{rh}:{rl}]'
            except Exception:
                pass

            # offset：从 port symbol 的 location 获取
            offset = 0
            try:
                offset = port_sym.location.offset
            except Exception:
                pass

            vs.ports.append(PortInfo(
                name=name, direction=direction, width=width,
                range_str=range_str, range_high=rh, range_low=rl,
                offset=offset,
            ))
    except Exception as e:
        logger.debug(f"[AST] Compilation 端口提取失败，回退到 JSON 解析: {e}")
        # 清空已添加的端口，让调用方回退
        vs.ports.clear()
        raise


def _extract_ports_pyslang(mod, code: str, vs: VerilogStructure):
    """从 pyslang AST 提取端口信息，处理方向继承"""
    try:
        pj = json.loads(mod.header.ports.to_json())
    except Exception:
        return

    last_direction = 'input'

    for p in pj.get('ports', []):
        if not isinstance(p, dict) or p.get('kind') != 'ImplicitAnsiPort':
            continue

        header = p.get('header', {})
        direction_node = header.get('direction', {})
        direction_text = direction_node.get('text', '').strip().lower()

        if direction_text in ('input', 'output', 'inout'):
            last_direction = direction_text
        direction = last_direction

        decl = p.get('declarator', {})
        name_node = decl.get('name', {})
        name = name_node.get('text', '').strip()
        if not name:
            continue

        # 位宽
        dt = header.get('dataType', {})
        dims = dt.get('dimensions', [])
        width = 1
        rh, rl = None, None
        range_str = ''
        if dims:
            spec = dims[0].get('specifier', {})
            sel = spec.get('selector', {})
            if sel.get('kind') == 'SimpleRangeSelect':
                left_lit = _extract_literal_value(sel.get('left', {}))
                right_lit = _extract_literal_value(sel.get('right', {}))
                if left_lit is not None and right_lit is not None:
                    rh = max(left_lit, right_lit)
                    rl = min(left_lit, right_lit)
                    width = rh - rl + 1
                    range_str = f'[{left_lit}:{right_lit}]'

        vs.ports.append(PortInfo(
            name=name, direction=direction, width=width,
            range_str=range_str, range_high=rh, range_low=rl,
        ))


def _extract_literal_value(node: dict) -> Optional[int]:
    if node.get('kind') == 'IntegerLiteralExpression':
        lit = node.get('literal', {})
        
        # 优先使用 pyslang 解析的数值
        value = lit.get('value')
        if value is not None:
            return int(value)
        
        # 回退到文本解析
        text = lit.get('text', '')
        try:
            return int(text)
        except (ValueError, TypeError):
            return None
    return None


def _extract_signal_decl(member, code: str, vs: VerilogStructure, comp_body=None):
    """提取内部信号声明（wire/reg/logic/integer）。
    
    优先使用 Compilation body.find() 获取语义求值后的精确位宽（支持参数化表达式）。
    回退到正则解析，遇到非数字表达式时保留原始 range_str，width 保守设为 1。
    """
    sr = member.sourceRange
    text = code[sr.start.offset:sr.end.offset]
    kind_str = str(member.kind)

    if kind_str == 'SyntaxKind.NetDeclaration':
        sig_kind_default = 'wire'
    else:
        sig_kind_default = 'reg'

    # 用正则从语法文本中提取信号名和原始 range_str
    m = re.search(r'\b(?:wire|reg|logic|integer)\s+(?:\[([^:]+):([^\]]+)\]\s+)?(\w+)', text)
    if not m:
        return

    high_s, low_s, name = m.groups()
    raw_range = f'[{high_s}:{low_s}]' if (high_s and low_s) else ''

    # 优先：用 Compilation 语义符号获取精确位宽
    if comp_body is not None:
        try:
            sym = comp_body.find(name)
            if sym is not None:
                t = sym.type
                width = t.bitWidth
                # 从 type 字符串推断 sig_kind
                type_str = str(t)
                if str(sym.kind) == 'SymbolKind.Net':
                    sig_kind = 'wire'
                elif type_str.startswith('reg'):
                    sig_kind = 'reg'
                elif type_str.startswith('integer'):
                    sig_kind = 'integer'
                else:
                    sig_kind = 'logic'
                # 若 Compilation 解析出的位宽 > 1，用精确 range_str；否则保留原始文本
                if width > 1:
                    range_str = f'[{width - 1}:0]'
                else:
                    range_str = raw_range
                vs.signals.append(SignalInfo(
                    name=name, kind=sig_kind, width=width,
                    offset=sr.start.offset + text.find(name),
                    range_str=range_str,
                ))
                return
        except Exception as e:
            logger.debug(f"[AST] Compilation 解析信号 {name!r} 失败: {e}")

    # 回退：纯文本解析
    width = 1
    if high_s and low_s:
        try:
            hi = int(high_s.strip())
            lo = int(low_s.strip())
            width = abs(hi - lo) + 1
        except (ValueError, TypeError):
            # 参数化表达式（如 NUM_BLOCKS-1:0），保留原始文本，width 保守设为 1
            logger.debug(f"[AST] 参数化位宽 {raw_range!r} 无法静态求值，width 退化为 1")

    vs.signals.append(SignalInfo(
        name=name, kind=sig_kind_default, width=width,
        offset=sr.start.offset + text.find(name),
        range_str=raw_range,
    ))


def _extract_continuous_assign(member, code: str, vs: VerilogStructure):
    sr = member.sourceRange
    full_text = code[sr.start.offset:sr.end.offset]

    for asgn in member.assignments:
        try:
            lhs_node = asgn.left
            rhs_node = asgn.right

            lhs_sr = lhs_node.sourceRange
            lhs_text = code[lhs_sr.start.offset:lhs_sr.end.offset].strip()

            rhs_sr = rhs_node.sourceRange
            rhs_text = code[rhs_sr.start.offset:rhs_sr.end.offset].strip()
        except AttributeError:
            # asgn.left / asgn.right 可能是 Token（无 sourceRange），回退到文本解析
            m = re.search(r'assign\s+(\S+)\s*=\s*(.+?)\s*;', full_text, re.DOTALL)
            if not m:
                continue
            lhs_text, rhs_text = m.group(1).strip(), m.group(2).strip()
            rhs_expr = _regex_analyze_expr(rhs_text, sr.start.offset + m.start(2))
            lhs_name_m = re.match(r'(\w+)', lhs_text)
            lhs_name = lhs_name_m.group(1) if lhs_name_m else lhs_text
            ai = AssignInfo(
                kind='continuous',
                lhs=lhs_text, rhs=rhs_text,
                full_text=full_text,
                start=sr.start.offset, end=sr.end.offset,
                rhs_expr=rhs_expr,
                lhs_name=lhs_name,
            )
            vs.assignments.append(ai)
            if rhs_expr:
                vs.expressions.append(rhs_expr)
            continue

        lhs_name_m = re.match(r'(\w+)', lhs_text)
        lhs_name = lhs_name_m.group(1) if lhs_name_m else lhs_text

        rhs_expr = _analyze_expression(rhs_node, code)

        ai = AssignInfo(
            kind='continuous',
            lhs=lhs_text, rhs=rhs_text,
            full_text=full_text,
            start=sr.start.offset, end=sr.end.offset,
            rhs_expr=rhs_expr,
            lhs_name=lhs_name,
        )
        vs.assignments.append(ai)

        if rhs_expr:
            vs.expressions.append(rhs_expr)


def _first_identifier_in_node(node) -> str:
    """从 pyslang AST 节点递归找第一个 IdentifierName 的文本。
    
    注意：pyslang SyntaxNode 迭代会产生 Token，需要用具名属性访问子节点。
    """
    try:
        kind = str(getattr(node, 'kind', ''))

        if kind == 'SyntaxKind.IdentifierName':
            ident = getattr(node, 'identifier', None)
            if ident:
                text = getattr(ident, 'valueText', '') or getattr(ident, 'rawText', '')
                if text.strip():
                    return text.strip()
            return ''

        # ConditionalPredicate → conditions（SyntaxList，可迭代出 ConditionalPattern）
        if kind == 'SyntaxKind.ConditionalPredicate':
            conditions = getattr(node, 'conditions', None)
            if conditions is not None:
                for cond in conditions:
                    result = _first_identifier_in_node(cond)
                    if result:
                        return result
            return ''

        # ConditionalPattern → expr
        if kind == 'SyntaxKind.ConditionalPattern':
            expr = getattr(node, 'expr', None)
            if expr is not None:
                return _first_identifier_in_node(expr)
            return ''

        # ParenthesizedExpression → expression（内部表达式，不要迭代）
        if kind == 'SyntaxKind.ParenthesizedExpression':
            inner = getattr(node, 'expression', None)
            if inner is not None:
                return _first_identifier_in_node(inner)
            return ''

        # 二元表达式（Equality/Binary/Relational 等）→ left 优先
        for attr in ('left', 'right', 'operand', 'expression', 'expr'):
            child = getattr(node, attr, None)
            if child is None:
                continue
            # 跳过 Token（没有 kind 属性或 kind 是 TokenKind）
            child_kind = str(getattr(child, 'kind', ''))
            if child_kind.startswith('TokenKind'):
                continue
            result = _first_identifier_in_node(child)
            if result:
                return result

    except Exception:
        pass
    return ''


def _analyze_expression(node, code: str) -> Optional[ExprInfo]:
    kind_str = str(node.kind)
    nsr = node.sourceRange

    if kind_str == 'SyntaxKind.ConditionalExpression':
        pred = node.predicate
        true_br = node.left
        false_br = node.right
        return ExprInfo(
            kind='ternary',
            text=code[nsr.start.offset:nsr.end.offset],
            start=nsr.start.offset, end=nsr.end.offset,
            predicate=code[pred.sourceRange.start.offset:pred.sourceRange.end.offset].strip(),
            pred_start=pred.sourceRange.start.offset,
            pred_end=pred.sourceRange.end.offset,
            pred_first_id=_first_identifier_in_node(pred),
            true_expr=code[true_br.sourceRange.start.offset:true_br.sourceRange.end.offset].strip(),
            true_start=true_br.sourceRange.start.offset,
            true_end=true_br.sourceRange.end.offset,
            false_expr=code[false_br.sourceRange.start.offset:false_br.sourceRange.end.offset].strip(),
            false_start=false_br.sourceRange.start.offset,
            false_end=false_br.sourceRange.end.offset,
        )

    if kind_str == 'SyntaxKind.BinaryAndExpression':
        return _make_binary_expr_info('binary_and', node, code)

    if kind_str == 'SyntaxKind.BinaryOrExpression':
        return _make_binary_expr_info('binary_or', node, code)

    if kind_str == 'SyntaxKind.EqualityExpression':
        return _make_binary_expr_info('equality', node, code)

    if kind_str == 'SyntaxKind.AddExpression':
        return _make_binary_expr_info('add', node, code)

    # ParenthesizedExpression：剥一层括号，递归解析内部
    if kind_str == 'SyntaxKind.ParenthesizedExpression':
        inner = getattr(node, 'expression', None)
        if inner is not None:
            return _analyze_expression(inner, code)

    return None


def _make_binary_expr_info(kind: str, node, code: str) -> ExprInfo:
    nsr = node.sourceRange
    lsr = node.left.sourceRange
    rsr = node.right.sourceRange
    return ExprInfo(
        kind=kind,
        text=code[nsr.start.offset:nsr.end.offset],
        start=nsr.start.offset, end=nsr.end.offset,
        left_text=code[lsr.start.offset:lsr.end.offset].strip(),
        left_start=lsr.start.offset, left_end=lsr.end.offset,
        op=node.operatorToken.rawText.strip(),
        right_text=code[rsr.start.offset:rsr.end.offset].strip(),
        right_start=rsr.start.offset, right_end=rsr.end.offset,
    )


def _extract_range_declarations(code: str, vs: VerilogStructure):
    for m in re.finditer(r'\[(\d+)\s*:\s*(\d+)\]', code):
        high, low = int(m.group(1)), int(m.group(2))
        before = code[:m.start()].rstrip()
        if re.search(r'\b(input|output|inout)\b', before.split('\n')[-1]):
            ctx = 'port'
        elif re.search(r'\b(wire|reg|logic)\b', before.split('\n')[-1]):
            ctx = 'wire'
        else:
            ctx = 'other'
        vs.declarations.append(DeclInfo(
            text=m.group(0), high=high, low=low,
            start=m.start(), end=m.end(), context=ctx,
        ))


# ============================================================================
# 正则回退解析器
# ============================================================================

def _find_matching_end(code: str, begin_pos: int) -> int:
    """从 begin 后的位置开始扫描，找到与 begin 配对的 end（按 begin/end 计数），返回该 end 的结束位置。"""
    depth = 1
    for tok in re.finditer(r'\bbegin\b|\bend\b', code[begin_pos:]):
        if tok.group(0) == 'begin':
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return begin_pos + tok.end()
    return -1


def _parse_with_regex(code: str) -> VerilogStructure:
    vs = VerilogStructure(code=code)

    m = re.search(r'\bmodule\s+(\w+)', code)
    if m:
        vs.module_name = m.group(1)
        vs.module_name_offset = m.start(1)

    for m in re.finditer(
        r'\b(input|output|inout)\s+'
        r'(?:(wire|reg|logic)\s+)?'
        r'(?:(signed|unsigned)\s+)?'
        r'(?:\[(\d+):(\d+)\]\s+)?'
        r'(\w+)',
        code
    ):
        # groups:
        # 1 direction, 2 kind, 3 signedness(optional), 4 high_s, 5 low_s, 6 name
        direction, _, _, high_s, low_s, name = m.groups()
        width = 1
        rh, rl = None, None
        rng = ''
        if high_s and low_s:
            rh, rl = int(high_s), int(low_s)
            width = abs(rh - rl) + 1
            rng = f'[{high_s}:{low_s}]'
        vs.ports.append(PortInfo(
            name=name, direction=direction, width=width,
            range_str=rng, range_high=rh, range_low=rl,
            offset=m.start(6),
        ))

    for m in re.finditer(r'\b(wire|reg|logic)\s+(?:\[(\d+):(\d+)\]\s+)?(\w+)', code):
        kind, high_s, low_s, name = m.groups()
        width = 1
        if high_s and low_s:
            width = abs(int(high_s) - int(low_s)) + 1
        if name not in {p.name for p in vs.ports}:
            vs.signals.append(SignalInfo(
                name=name, kind=kind, width=width, offset=m.start(4),
            ))

    for m in re.finditer(r'assign\s+(\w[\w\[\]:]*)\s*=\s*([^;]+);', code):
        lhs, rhs = m.group(1).strip(), m.group(2).strip()
        lhs_name_m = re.match(r'(\w+)', lhs)
        lhs_name = lhs_name_m.group(1) if lhs_name_m else lhs
        rhs_expr = _regex_analyze_expr(rhs, m.start(2))

        vs.assignments.append(AssignInfo(
            kind='continuous', lhs=lhs, rhs=rhs,
            full_text=m.group(0),
            start=m.start(), end=m.end(),
            rhs_expr=rhs_expr, lhs_name=lhs_name,
        ))
        if rhs_expr:
            vs.expressions.append(rhs_expr)

    for m in re.finditer(r'always\s+@\s*\([^)]*\)\s*', code, re.DOTALL):
        head_end = m.end()
        begin_match = re.match(r'\bbegin\b', code[head_end:])
        if begin_match:
            begin_body_start = head_end + begin_match.end()
            end_end = _find_matching_end(code, begin_body_start)
            if end_end > 0:
                text = code[m.start():end_end]
                has_be = True
                block_end = end_end
            else:
                text = code[m.start():head_end]
                has_be = False
                block_end = head_end
        else:
            rest = re.match(r'[^;]+;', code[head_end:], re.DOTALL)
            if rest:
                block_end = head_end + rest.end()
                text = code[m.start():block_end]
                has_be = False
            else:
                continue
        vs.always_blocks.append(AlwaysInfo(
            text=text, start=m.start(), end=block_end,
            has_begin_end=has_be,
        ))

    _extract_range_declarations(code, vs)

    # case 语句块（正则）
    for m in re.finditer(r'\bcase\s*\([^)]+\)(.*?)\bendcase\b', code, re.DOTALL):
        vs.case_blocks.append(CaseInfo(start=m.start(), end=m.end()))

    vs.identifiers[vs.module_name] = 'module_name'
    for p in vs.ports:
        vs.identifiers[p.name] = 'port'
    for s in vs.signals:
        vs.identifiers[s.name] = s.kind

    return vs


def _regex_analyze_expr(rhs: str, base_offset: int) -> Optional[ExprInfo]:
    tm = re.match(r'(\w[\w\[\]:]*)\s*\?\s*(\w[\w\[\]:]*)\s*:\s*(\w[\w\[\]:]*)\s*$', rhs)
    if tm:
        return ExprInfo(
            kind='ternary', text=rhs,
            start=base_offset, end=base_offset + len(rhs),
            predicate=tm.group(1),
            true_expr=tm.group(2),
            false_expr=tm.group(3),
        )

    am = re.match(r'(\w[\w\[\]:]*)\s*&(?!&)\s*(\w[\w\[\]:]*)\s*$', rhs)
    if am:
        return ExprInfo(
            kind='binary_and', text=rhs,
            start=base_offset, end=base_offset + len(rhs),
            left_text=am.group(1), op='&', right_text=am.group(2),
        )

    om = re.match(r'(\w[\w\[\]:]*)\s*\|(?!\|)\s*(\w[\w\[\]:]*)\s*$', rhs)
    if om:
        return ExprInfo(
            kind='binary_or', text=rhs,
            start=base_offset, end=base_offset + len(rhs),
            left_text=om.group(1), op='|', right_text=om.group(2),
        )

    return None


# ============================================================================
# 统一入口
# ============================================================================

def analyze(code: str) -> VerilogStructure:
    """分析 Verilog 代码，返回结构化信息。优先 pyslang，失败回退正则。"""
    vs = _parse_with_pyslang(code)
    if vs is not None and (vs.module_name or vs.assignments or vs.ports):
        return vs
    return _parse_with_regex(code)


# ============================================================================
# 文本手术工具
# ============================================================================

def _replace_range(code: str, start: int, end: int, new_text: str) -> str:
    """精确替换源码中 [start, end) 范围的文本"""
    return code[:start] + new_text + code[end:]


VERILOG_KEYWORDS = frozenset({
    'module', 'endmodule', 'input', 'output', 'inout', 'assign', 'wire',
    'reg', 'logic', 'always', 'begin', 'end', 'if', 'else', 'case',
    'endcase', 'for', 'while', 'parameter', 'localparam', 'integer',
    'real', 'time', 'posedge', 'negedge', 'or', 'and', 'not', 'xor',
    'initial', 'task', 'endtask', 'function', 'endfunction', 'generate',
    'endgenerate', 'typedef', 'enum', 'struct',
    'signed', 'unsigned',
})


def _offset_to_line(code: str, offset: int) -> int:
    """将源码偏移转为 1-based 行号。"""
    if offset <= 0:
        return 1
    return code[:offset].count("\n") + 1


def _item_line_range(code: str, item: Any) -> Tuple[int, int]:
    """
    获取候选项对应的行号范围 (start_line, end_line)，均为 1-based。
    支持 AssignInfo, ExprInfo, PortInfo, SignalInfo, AlwaysInfo, CommentInsertPoint, DeclInfo 等。
    """
    if hasattr(item, "line_no"):  # CommentInsertPoint
        n = getattr(item, "line_no", 1)
        return (n, n)
    start = getattr(item, "start", None) or getattr(item, "offset", 0)
    end = getattr(item, "end", None) or getattr(item, "offset", start)
    return (_offset_to_line(code, start), _offset_to_line(code, end))


def _item_signal(item: Any) -> Optional[str]:
    """获取候选项关联的主信号名（用于按 target_signal 选择）。AssignInfo→lhs_name, PortInfo/SignalInfo→name。"""
    if hasattr(item, "lhs_name") and getattr(item, "lhs_name", ""):
        return getattr(item, "lhs_name", "").strip()
    if hasattr(item, "name") and getattr(item, "name", ""):
        return getattr(item, "name", "").strip()
    return None


def _select_target_by_line(items: List, code: str, target_line: int) -> Optional[int]:
    """
    按行号选择目标：返回第一个「行号范围包含 target_line」的候选的索引；
    若均不包含则返回 None。target_line 为 1-based。
    """
    if not items or target_line is None:
        return None
    for i, item in enumerate(items):
        lo, hi = _item_line_range(code, item)
        if lo <= target_line <= hi:
            return i
    return None


def _select_target_by_signal(items: List, code: str, target_signal: str) -> Optional[int]:
    """
    按信号名选择目标：返回第一个「主信号名等于 target_signal（忽略大小写）」的候选的索引；若无则返回 None。
    """
    if not items or not (target_signal and isinstance(target_signal, str)):
        return None
    want = target_signal.strip()
    if not want:
        return None
    want_lower = want.lower()
    for i, item in enumerate(items):
        sig = _item_signal(item)
        if sig and sig.lower() == want_lower:
            return i
    return None


def _select_target_or_first(items: List, target_token: Optional[int]) -> Optional[Any]:
    """根据 target_token 选择目标项"""
    if not items:
        return None
    if target_token is None:
        return items[0]
    if isinstance(target_token, int) and 0 <= target_token < len(items):
        return items[target_token]
    return None


# ============================================================================
# 装饰器系统
# ============================================================================

T = TypeVar('T')


class TargetTokenHandler(Generic[T]):
    """
    统一目标选择装饰器
    
    职责：
    - AST 解析（自动调用 analyze）
    - 候选提取（通过 selector）
    - 候选过滤（通过 filter_func）
    - 目标选择（根据 target_token）
    - 参数传递与验证
    - 异常处理和日志
    """
    
    def __init__(
        self,
        selector: Callable[[VerilogStructure], List[T]],
        filter_func: Optional[Callable[[T, VerilogStructure], bool]] = None,
        name: str = "Transform"
    ):
        self.selector = selector
        self.filter_func = filter_func
        self.name = name
    
    def __call__(self, func: Callable):
        @wraps(func)
        def wrapper(code: str, target_token: Optional[int] = None, **kwargs) -> str:
            # 1. 解析 AST
            vs = analyze(code)
            
            # 2. 提取候选
            all_items = self.selector(vs)
            
            # 3. 过滤候选
            if self.filter_func:
                candidates = [item for item in all_items if self.filter_func(item, vs)]
                logger.debug(f"[{self.name}] Filtered: {len(all_items)} → {len(candidates)}")
            else:
                candidates = all_items
            
            if not candidates:
                logger.debug(f"[{self.name}] No candidates found")
                return code
            
            # 3.5 若传入 target_signal 或 target_line，转换为 target_token（候选索引）；优先 target_signal
            target_signal = kwargs.pop("target_signal", None)
            target_line = kwargs.pop("target_line", None)
            resolved_by_hint = False
            if target_signal is not None:
                idx = _select_target_by_signal(candidates, code, str(target_signal))
                if idx is not None:
                    target_token = idx
                    resolved_by_hint = True
                    logger.debug(f"[{self.name}] target_signal={target_signal!r} → candidate index {idx}")
                else:
                    logger.debug(f"[{self.name}] target_signal={target_signal!r} not matched")
            if not resolved_by_hint and target_line is not None:
                try:
                    line_val = int(target_line)
                    idx = _select_target_by_line(candidates, code, line_val)
                    if idx is not None:
                        target_token = idx
                        resolved_by_hint = True
                        logger.debug(f"[{self.name}] target_line={line_val} → candidate index {idx}")
                    else:
                        logger.debug(f"[{self.name}] target_line={line_val} not in any candidate range, using first")
                except (TypeError, ValueError):
                    pass
            
            # 4. 选择目标（越界时回退到第一个候选，避免因生成器与引擎过滤不一致导致跳过变换）
            target = _select_target_or_first(candidates, target_token)
            if target is None and target_token is not None:
                logger.debug(
                    f"[{self.name}] target_token={target_token} "
                    f"out of range [0, {len(candidates)-1}], using first candidate"
                )
                target = candidates[0] if candidates else None
            if target is None:
                return code
            
            # 5. 执行变换（智能参数传递）
            try:
                sig = inspect.signature(func)
                params = sig.parameters
                
                # 检查函数是否接受 **kwargs
                has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                
                if has_var_keyword:
                    # 函数接受 **kwargs，直接传递所有参数
                    return func(code, vs, target, **kwargs)
                else:
                    # 函数只接受特定参数，过滤 kwargs
                    func_param_names = set(params.keys()) - {'code', 'vs', 'target'}
                    filtered_kwargs = {k: v for k, v in kwargs.items() if k in func_param_names}
                    return func(code, vs, target, **filtered_kwargs)
            except Exception as e:
                logger.error(f"[{self.name}] Transformation failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return code
        
        return wrapper


# ============================================================================
# 选择器和过滤器
# ============================================================================

class Selectors:
    """预定义的候选选择器"""
    
    @staticmethod
    def continuous_assigns(vs: VerilogStructure) -> List[AssignInfo]:
        return vs.continuous_assigns()
    
    @staticmethod
    def ternary_exprs(vs: VerilogStructure) -> List[ExprInfo]:
        return vs.ternary_exprs()
    
    @staticmethod
    def binary_and_exprs(vs: VerilogStructure) -> List[ExprInfo]:
        return vs.binary_and_exprs()
    
    @staticmethod
    def binary_or_exprs(vs: VerilogStructure) -> List[ExprInfo]:
        return vs.binary_or_exprs()
    
    @staticmethod
    def always_blocks(vs: VerilogStructure) -> List[AlwaysInfo]:
        return vs.always_blocks
    
    @staticmethod
    def declarations(vs: VerilogStructure) -> List[DeclInfo]:
        return vs.declarations

    @staticmethod
    def fsm_state_signals(vs: VerilogStructure) -> List[SignalInfo]:
        """FSM 状态寄存器"""
        fsm_patterns = ['current_state', 'next_state', 'state', 'fsm_state', 'cs', 'ns']
        return [
            sig for sig in vs.signals
            if sig.kind in ('reg', 'logic') and any(pat in sig.name for pat in fsm_patterns)
        ]

    @staticmethod
    def input_ports(vs: VerilogStructure) -> List[PortInfo]:
        """input 端口（排除关键字名）"""
        return [p for p in vs.ports if p.direction == "input" and p.name not in VERILOG_KEYWORDS]

    @staticmethod
    def signals(vs: VerilogStructure) -> List[SignalInfo]:
        """所有信号"""
        return getattr(vs, "signals", [])

    @staticmethod
    def case_blocks(vs: VerilogStructure) -> List[CaseInfo]:
        """所有 case (...) ... endcase 块"""
        return getattr(vs, "case_blocks", [])


class Filters:
    """预定义的候选过滤器"""
    
    @staticmethod
    def is_1bit_ternary(expr: ExprInfo, vs: VerilogStructure) -> bool:
        """三元表达式的 predicate 是 1-bit 信号"""
        if expr.kind != 'ternary':
            return False
        sel = expr.predicate.strip()
        m = re.match(r'(\w+)', sel)
        if not m:
            return False
        return vs.is_1bit(m.group(1))
    
    @staticmethod
    def has_operator(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """赋值的 RHS 包含运算符"""
        return bool(re.search(r'[&|^~?:+\-*/]', asgn.rhs))
    
    @staticmethod
    def no_outer_parens(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """RHS 没有外层括号"""
        rhs = asgn.rhs.strip()
        return not (rhs.startswith('(') and rhs.endswith(')'))
    
    @staticmethod
    def not_simple_identifier(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """RHS 不是单个标识符"""
        rhs = asgn.rhs.strip()
        return not re.match(r"^[\w'\[\]:]+$", rhs)
    
    @staticmethod
    def is_complex_rhs(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """组合过滤器：复杂 RHS（有运算符、无外层括号、非单标识符）"""
        return (
            Filters.has_operator(asgn, vs) and
            Filters.no_outer_parens(asgn, vs) and
            Filters.not_simple_identifier(asgn, vs)
        )
    
    @staticmethod
    def has_ternary_rhs(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """RHS 包含三元表达式"""
        return asgn.rhs_expr is not None and asgn.rhs_expr.kind == 'ternary'

    @staticmethod
    def has_begin_end(ab: AlwaysInfo, vs: VerilogStructure) -> bool:
        """always 块带 begin/end"""
        return getattr(ab, "has_begin_end", False)

    @staticmethod
    def has_binary_and_or_rhs(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """RHS 为 binary_and 或 binary_or 表达式"""
        if not asgn.rhs_expr:
            return False
        k = getattr(asgn.rhs_expr, "kind", "")
        return k in ("binary_and", "binary_or")

    @staticmethod
    def has_bit_constant(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """RHS 含 1'b0 或 1'b1 常量"""
        return "1'b0" in asgn.rhs or "1'b1" in asgn.rhs

    @staticmethod
    def has_multiple_non_default_branches(cb: 'CaseInfo', vs: VerilogStructure) -> bool:
        """case 块有至少 2 个非 default 分支（T41 需要）"""
        if not cb.branches:
            return False
        return sum(1 for _, _, is_def in cb.branches if not is_def) >= 2

    @staticmethod
    def has_input_port(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """模块有至少一个 input 端口（T45 需要）"""
        return any(p.direction == 'input' for p in vs.ports)

    @staticmethod
    def has_equality_or_add_rhs(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """RHS 为 == 或 + 表达式（T47 需要）"""
        expr = asgn.rhs_expr
        return bool(expr and getattr(expr, "kind", "") in ("equality", "add"))

    @staticmethod
    def has_multiple_continuous_assigns(_dummy: Any, vs: VerilogStructure) -> bool:
        """模块中至少有两条 continuous assign（T48 需要）"""
        return len([a for a in vs.assignments if a.kind == "continuous"]) >= 2

    @staticmethod
    def is_simple_expr(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """简单表达式（长度<20，无三元，LHS非concatenation）"""
        if len(asgn.rhs) > 20:
            return False
        if '?' in asgn.rhs:
            return False
        if '{' in asgn.lhs or '}' in asgn.lhs:
            return False
        return True
    
    @staticmethod
    def is_constant_rhs(asgn: AssignInfo, vs: VerilogStructure) -> bool:
        """RHS 是常量字面量"""
        return bool(re.match(r"^\d+'[bdh][0-9a-fA-F]+$", asgn.rhs.strip()))
    
    @staticmethod
    def is_port_or_wire_decl(decl: DeclInfo, vs: VerilogStructure) -> bool:
        """位宽声明在端口或 wire 上下文"""
        return decl.context in ('port', 'wire') and decl.high > decl.low
    
    @staticmethod
    def can_convert_to_async_reset(ab: AlwaysInfo, vs: VerilogStructure) -> bool:
        """可以转换为异步复位的 always 块"""
        block_text = ab.text
        if ' or ' in block_text[:50]:
            return False
        rst_match = re.search(r'\bif\s*\(\s*(rst\w*|reset\w*)\s*\)', block_text)
        if not rst_match:
            return False
        sens_match = re.search(r'always\s*@\s*\(\s*posedge\s+(\w+)\s*\)', block_text)
        return sens_match is not None


# ============================================================================
# 参数化的变换函数
# ============================================================================

# --- T03: 冗余逻辑注入 ---
def ast_redundant_logic(
    code: str,
    target_token: Optional[int] = None,
    redundant_name: Optional[str] = None,
    name_prefix: str = "_tap_",
) -> str:
    """
    T03: 冗余逻辑注入。

    - target_token: 指定第几个端口（从 0 计），支持 input / output。
    - redundant_name: 可选，外部指定冗余信号名（如 "status_tap"）；若为空则使用 name_prefix+端口名。
    - name_prefix: 在未显式给 redundant_name 时使用的前缀（默认 "_tap_"）。
    """
    vs = analyze(code)
    # 支持在 input / output 上注入，从端口派生冗余信号
    candidates = [
        p for p in vs.ports
        if p.direction in ("input", "output") and p.name not in VERILOG_KEYWORDS
    ]
    target = _select_target_or_first(candidates, target_token)
    if target is None:
        return code

    base_name = (redundant_name or f"{name_prefix}{target.name}").strip()
    # 简单清洗：确保是合法标识符
    if not re.match(r"[A-Za-z_]", base_name):
        base_name = f"_{base_name}"
    safe_name = re.sub(r"[^A-Za-z0-9_$]", "_", base_name)

    # 用端口 AST 偏移定位模块端口列表结束的 ';'，无需正则扫描全文
    # 最后一个端口的 offset 之后找第一个 ';'
    last_port_offset = max((p.offset for p in vs.ports if p.offset > 0), default=0)
    if last_port_offset > 0:
        semi_pos = code.find(';', last_port_offset)
    else:
        # 回退：正则找 );
        semi_m = re.search(r'\)\s*;', code)
        semi_pos = semi_m.end() - 1 if semi_m else -1
    if semi_pos < 0:
        return code

    insert_pos_raw = semi_pos + 1  # ';' 之后
    nl = code.find('\n', insert_pos_raw)
    insert_pos = nl if nl >= 0 else insert_pos_raw
    
    width_prefix = f'[{target.range_high}:{target.range_low}] ' if getattr(target, "range_high", None) is not None and getattr(target, "range_low", None) is not None and target.width > 1 else ''
    width = getattr(target, "width", 1) or 1

    if target.direction == "input":
        # 从 input 端口派生的冗余逻辑
        expr = f"{target.name} & {{{width}{{1'b1}}}}"
    else:
        # 从 output 端口派生的镜像信号（不改动输出驱动，只阅读）
        expr = f"{target.name} ^ {{{width}{{1'b0}}}}"

    dummy_line = f"\n  wire {width_prefix}{safe_name} = {expr};\n"
    
    return code[:insert_pos] + dummy_line + code[insert_pos:]


# --- T04/T20: 灵活误导性注释（参数化） ---
def _extract_comment_insert_points(code: str, vs: VerilogStructure) -> List[CommentInsertPoint]:
    """提取所有可插入注释的位置，优先选择内部位置而非模块前。"""
    inline_points: List[CommentInsertPoint] = []  # 行尾注释（高优先级）
    before_line_points: List[CommentInsertPoint] = []  # 块前注释（中优先级）
    module_points: List[CommentInsertPoint] = []  # module前注释（低优先级）
    
    lines = code.split('\n')
    line_offsets: List[int] = []
    offset = 0
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith('//'):
            continue

        line_offset = line_offsets[line_no - 1]

        # B/D：行尾追加注释（最高优先级）
        if any(kw in stripped for kw in (
            'input ', 'output ', 'wire ', 'reg ', 'assign ', '<=', '=='
        )):
            inline_points.append(CommentInsertPoint(
                kind='inline_after',
                line_no=line_no,
                line_text=stripped[:80],
                insert_offset=line_offset + len(line),
            ))
        # module前的注释（最低优先级）
        elif stripped.startswith('module '):
            module_points.append(CommentInsertPoint(
                kind='before_line',
                line_no=line_no,
                line_text=stripped[:80],
                insert_offset=line_offset,
            ))
        # A/C/E：块前新行注释（中等优先级）
        elif any(kw in stripped for kw in (
            'always', 'assign', 'endmodule', 'if (', 'case ', 'begin'
        )):
            before_line_points.append(CommentInsertPoint(
                kind='before_line',
                line_no=line_no,
                line_text=stripped[:80],
                insert_offset=line_offset,
            ))

    # 按优先级合并：行尾 > 块前 > module前
    return inline_points + before_line_points + module_points


def _generate_misleading_comment(
    point: CommentInsertPoint,
    vs: VerilogStructure,
    custom_text: Optional[str] = None,
    comment_style: Optional[str] = None,
) -> str:
    """根据插入位置及语义锚点生成误导注释。"""
    if custom_text:
        # 确保custom_text的每一行都以//开头，避免生成非法代码
        if point.kind == 'inline_after':
            # 行尾注释：单行处理
            return f'  // {custom_text.replace(chr(10), " ")}'  # 移除换行符
        else:
            # 对于before_line，特别是在module前，必须确保所有内容都是注释
            # 检查是否在module定义之前
            is_before_module = 'module' in point.line_text.lower()
            
            lines = custom_text.split('\n')
            commented_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # 如果在module前且该行不是注释，强制注释化
                if is_before_module and not stripped.startswith('//'):
                    commented_lines.append(f'// {stripped}')
                elif stripped.startswith('//'):
                    commented_lines.append(stripped)
                else:
                    # 非module前的位置，保持原样但确保是注释
                    commented_lines.append(f'// {stripped}')
            
            return '\n'.join(commented_lines) + '\n' if commented_lines else ''

    line_text = point.line_text.lower()

    # T04 兼容旧参数：在模块前用历史模板
    if comment_style and point.kind == 'before_line' and 'module' in line_text:
        style_templates = {
            'generated': (
                '// ========================================\n'
                '// Code Analysis - Generated Module\n'
                '// ========================================\n'
            ),
            'copyright': (
                '// Copyright (c) 2024 Anonymous Corporation\n'
                '// Confidential and Proprietary\n'
                '// Auto-generated - Do Not Modify\n'
            ),
            'warning': (
                '// WARNING: This file is auto-generated\n'
                '// Manual changes will be lost\n'
            ),
            'simple': '// Auto-generated code\n',
        }
        return style_templates.get(comment_style, style_templates['generated'])

    if 'module' in line_text and point.kind == 'before_line':
        return f"// {random.choice(['UART Transmitter - 9600 baud', 'SPI Master Controller', 'I2C Slave Interface', 'Clock Divider - ratio 4', 'PWM Generator - 8bit resolution', 'CRC-32 Calculator'])}\n"
    if ('input' in line_text or 'output' in line_text) and point.kind == 'inline_after':
        return f"  // {random.choice(['active low reset', 'clock enable signal', 'data valid strobe', 'chip select, active high', 'write enable'])}"
    if 'always' in line_text and point.kind == 'before_line':
        return f"{random.choice(['// Sequential logic - register update', '// Clock domain crossing handler', '// Pipeline stage 2 control'])}\n"
    if 'assign' in line_text and point.kind == 'before_line':
        return f"{random.choice(['// Registered output with enable', '// Tri-state buffer control', '// Glitch filter output'])}\n"
    if ('==' in line_text or '<=' in line_text) and point.kind == 'inline_after':
        return f"  // {random.choice(['reset condition', 'overflow detected', 'handshake complete', 'error recovery path'])}"
    if 'endmodule' in line_text:
        return "\n// Verified: simulation passed all test vectors\n// DO NOT MODIFY\n"
    return '// internal logic\n'


def ast_flexible_comment(
    code: str,
    target_token: Optional[int] = None,
    custom_text: Optional[str] = None,
    custom_description: Optional[str] = None,
    comment_style: Optional[str] = None,
) -> str:
    """
    T04/T20：可在多位置插入误导性注释，target_token 对应候选插入点索引。

    兼容旧参数：
    - T04: comment_style
    - T20: custom_description
    """
    vs = analyze(code)
    insert_points = _extract_comment_insert_points(code, vs)
    if not insert_points:
        return code

    point = _select_target_or_first(insert_points, target_token)
    if point is None and target_token is not None:
        logger.debug("[T04/T20] target_token=%s out of range [0, %s], using first candidate", target_token, len(insert_points) - 1)
        point = insert_points[0]
    if point is None:
        return code

    text = custom_text if custom_text else custom_description
    comment = _generate_misleading_comment(point, vs, text, comment_style)
    return code[:point.insert_offset] + comment + code[point.insert_offset:]



# --- T07: 赋值重排 ---
def _t07_valid_pairs(assigns: list, code: str) -> List[Tuple[int, int]]:
    """返回所有可交换的 (i, j) 对（i < j），要求无数据依赖且文本不同。
    优先相邻对（j == i+1），再考虑非相邻对，保证 target_token=0 时行为与旧版一致。
    """
    n = len(assigns)
    adjacent = []
    non_adjacent = []
    for i in range(n):
        for j in range(i + 1, n):
            a1, a2 = assigns[i], assigns[j]
            dep = (re.search(r"\b" + re.escape(a1.lhs_name) + r"\b", a2.rhs) or
                   re.search(r"\b" + re.escape(a2.lhs_name) + r"\b", a1.rhs))
            if dep:
                continue
            if code[a1.start:a1.end] == code[a2.start:a2.end]:
                continue
            if j == i + 1:
                adjacent.append((i, j))
            else:
                non_adjacent.append((i, j))
    return adjacent + non_adjacent


def ast_assign_reorder(code: str, target_token: Optional[int] = None) -> str:
    """T07: 交换两条独立的 assign（支持非相邻对）。target_token 指定第几对（从 0 计）。"""
    vs = analyze(code)
    assigns = vs.continuous_assigns()
    if len(assigns) < 2:
        return code
    valid_pairs = _t07_valid_pairs(assigns, code)
    pair = _select_target_or_first(valid_pairs, target_token)
    if pair is None:
        return code
    i, j = pair
    a1, a2 = assigns[i], assigns[j]
    text1 = code[a1.start:a1.end]
    text2 = code[a2.start:a2.end]
    # 先替换靠后的（j），再替换靠前的（i），避免偏移错位
    result = code[:a2.start] + text1 + code[a2.end:]
    # a1 的偏移不变（j > i，前面的位置未动）
    result = result[:a1.start] + text2 + result[a1.end:]
    return result


# --- T09: 德摩根 AND ---
@TargetTokenHandler(
    selector=Selectors.binary_and_exprs,
    name="T09"
)
def ast_demorgan_and(code: str, vs: VerilogStructure, target: ExprInfo) -> str:
    """T09: a & b → ~(~a | ~b)，仅在位宽匹配时应用以保证功能等价"""
    
    # 提取信号名（去除位选择和其他操作符）
    def extract_signal_name(expr_text):
        expr_text = expr_text.strip()
        # 匹配信号名（可能带位选择）
        match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)', expr_text)
        return match.group(1) if match else None
    
    a_name = extract_signal_name(target.left_text)
    b_name = extract_signal_name(target.right_text)
    
    # 检查位宽是否匹配
    if a_name and b_name:
        a_width = vs.get_width(a_name)
        b_width = vs.get_width(b_name)
        
        # 只在位宽相同时应用变换，避免位宽扩展导致的行为差异
        if a_width != b_width and a_width > 0 and b_width > 0:
            return code
    
    def smart_negate(s):
        s = s.strip()
        return s[1:].strip() if s.startswith('~') else f'~{s}'
    
    neg_a = smart_negate(target.left_text)
    neg_b = smart_negate(target.right_text)
    new_expr = f'~({neg_a} | {neg_b})'
    return _replace_range(code, target.start, target.end, new_expr)


# --- T10: 德摩根 OR ---
@TargetTokenHandler(
    selector=Selectors.binary_or_exprs,
    name="T10"
)
def ast_demorgan_or(code: str, vs: VerilogStructure, target: ExprInfo) -> str:
    """T10: a | b → ~(~a & ~b)，仅在位宽匹配时应用以保证功能等价"""
    
    # 提取信号名（去除位选择和其他操作符）
    def extract_signal_name(expr_text):
        expr_text = expr_text.strip()
        # 匹配信号名（可能带位选择）
        match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)', expr_text)
        return match.group(1) if match else None
    
    a_name = extract_signal_name(target.left_text)
    b_name = extract_signal_name(target.right_text)
    
    # 检查位宽是否匹配
    if a_name and b_name:
        a_width = vs.get_width(a_name)
        b_width = vs.get_width(b_name)
        
        # 只在位宽相同时应用变换，避免位宽扩展导致的行为差异
        if a_width != b_width and a_width > 0 and b_width > 0:
            return code
    
    def smart_negate(s):
        s = s.strip()
        return s[1:].strip() if s.startswith('~') else f'~{s}'
    
    neg_a = smart_negate(target.left_text)
    neg_b = smart_negate(target.right_text)
    new_expr = f'~({neg_a} & {neg_b})'
    return _replace_range(code, target.start, target.end, new_expr)


# --- T12: 中间信号注入（参数化） ---
@TargetTokenHandler(
    selector=Selectors.continuous_assigns,
    filter_func=Filters.has_ternary_rhs,
    name="T12"
)
def ast_intermediate_signal(
    code: str, 
    vs: VerilogStructure, 
    target: AssignInfo,
    wire_name: str = '',
) -> str:
    """T12: 三元 predicate 抽取为 wire。wire_name 指定中间信号名，留空则自动生成 __{first_id}_tmp。"""
    expr = target.rhs_expr
    if not expr or expr.kind != 'ternary':
        return code

    if wire_name and re.match(r'^[A-Za-z_]\w*$', wire_name):
        tmp_name = wire_name
    else:
        # pred_first_id 由 AST 解析阶段填充，无需正则
        first_id = expr.pred_first_id or f'cond{len(expr.predicate)}'
        tmp_name = f'__{first_id}_tmp'

    # 避免与已有标识符冲突
    while tmp_name in vs.all_identifiers():
        tmp_name += '_'
    
    line_start = code.rfind('\n', 0, target.start) + 1
    indent = ''
    for ch in code[line_start:target.start]:
        if ch in ' \t':
            indent += ch
        else:
            break
    
    # 使用标准Verilog语法：分离wire声明和assign语句
    # predicate通常是1位，但为了安全也可以不指定位宽
    wire_decl = f'{indent}wire {tmp_name};\n'
    wire_assign = f'{indent}assign {tmp_name} = {expr.predicate};\n'
    new_assign = f'{indent}assign {target.lhs} = {tmp_name} ? {expr.true_expr} : {expr.false_expr};'
    
    return code[:line_start] + wire_decl + wire_assign + new_assign + code[target.end:]


# --- T19: 虚假模式注入 ---
# 多种死代码模式（均不可达），target_token 选择其一，缺省用 0。
# 若增删模式，需同步修改 AttackConfigGenerator 中 T19 的 candidates 数量。
T19_FALSE_PATTERNS = [
    (
        "  always @(*) begin\n"
        "    if (1'b0) begin\n"
        "    end\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    if (1'b0) ; else ;\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) case (1'b0)\n"
        "    1'b1: ;\n"
        "    default: ;\n"
        "  endcase\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    if (1'b1) if (1'b0) ;\n"
        "  end\n"
        "\n"
    ),
    (
        "  initial begin\n"
        "    if (1'b0) ;\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    case (1'b0)\n"
        "      1'b1: ;\n"
        "      default: ;\n"
        "    endcase\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    if (1'b0) begin end else if (1'b0) begin end\n"
        "  end\n"
        "\n"
    ),
]


def ast_false_pattern_inject(
    code: str,
    target_token: Optional[int] = None,
    custom_dead_stmts: Optional[str] = None,
) -> str:
    """T19: 虚假模式注入（可选：由外部提供自定义死代码语句）。

    - target_token 选择固定死代码模式索引（0..len(T19_FALSE_PATTERNS)-1）
    - 若 custom_dead_stmts 非空：将其包进 if (1'b0) 的不可达分支中，从而保证不影响 RTL 功能。
    """
    endmodule_m = re.search(r'\bendmodule\b', code)
    if not endmodule_m:
        return code
    
    insert_pos = endmodule_m.start()
    patterns = T19_FALSE_PATTERNS
    idx = 0 if target_token is None else 0
    if target_token is not None and 0 <= target_token < len(patterns):
        idx = target_token

    # 1) 优先使用自定义死代码语句（不可达分支包装）
    if custom_dead_stmts is not None:
        dead = str(custom_dead_stmts).strip()
        if dead:
            # 简单安全过滤：避免 LLM 直接生成 another always/endmodule 等外层结构
            banned = ("always", "initial", "module", "endmodule")
            low = dead.lower()
            if any(b in low for b in banned):
                return code

            # 将自定义语句作为 if(1'b0) 分支内容插入（确保语义不可达）
            indented_lines = []
            for line in dead.splitlines():
                line = line.rstrip()
                if not line:
                    continue
                indented_lines.append("      " + line)
            dead_body = "\n".join(indented_lines) if indented_lines else "      ;"

            false_block = (
                "  always @(*) begin\n"
                "    if (1'b0) begin\n"
                f"{dead_body}\n"
                "    end\n"
                "  end\n"
                "\n"
            )
            return code[:insert_pos] + false_block + code[insert_pos:]

    # 2) 否则回退到固定模板
    false_block = patterns[idx]
    
    return code[:insert_pos] + false_block + code[insert_pos:]


# --- T20: 误导性注释（参数化） ---
def ast_misleading_comment(
    code: str,
    target_token: Optional[int] = None,
    custom_description: Optional[str] = None,
    custom_text: Optional[str] = None,
) -> str:
    """T20: 误导性注释（转发到灵活注释实现）。"""
    return ast_flexible_comment(
        code=code,
        target_token=target_token,
        custom_text=custom_text,
        custom_description=custom_description,
    )


# --- T30: 常量恒等变换（参数化） ---
@TargetTokenHandler(
    selector=Selectors.continuous_assigns,
    filter_func=Filters.has_bit_constant,
    name="T30"
)
def ast_constant_identity(
    code: str, 
    vs: VerilogStructure, 
    target: AssignInfo,
    zero_pattern: str = "(1'b1 & 1'b0)",
    one_pattern: str = "(1'b1 | 1'b0)"
) -> str:
    """T30: 1'b0 → (1'b1 & 1'b0), 1'b1 → (1'b1 | 1'b0)"""
    eq_pos = code.find('=', target.start + len('assign'))
    if eq_pos < 0:
        return code
    
    rhs_start = eq_pos + 1
    while rhs_start < len(code) and code[rhs_start] in ' \t':
        rhs_start += 1
    
    semi_pos = code.find(';', rhs_start)
    if semi_pos < 0:
        return code
    
    actual_rhs = code[rhs_start:semi_pos].strip()
    
    if "1'b0" in actual_rhs:
        new_rhs = actual_rhs.replace("1'b0", zero_pattern, 1)
        return code[:rhs_start] + ' ' + new_rhs + code[semi_pos:]
    
    if "1'b1" in actual_rhs:
        new_rhs = actual_rhs.replace("1'b1", one_pattern, 1)
        return code[:rhs_start] + ' ' + new_rhs + code[semi_pos:]
    
    return code


# --- T31: 中间信号注入（参数化） ---
@TargetTokenHandler(
    selector=Selectors.continuous_assigns,
    name="T31"
)
def ast_simple_assign_intermediate(
    code: str, 
    vs: VerilogStructure, 
    target: AssignInfo,
    wire_name: str = '',
) -> str:
    """T31: assign var = expr -> wire <tmp> = expr; assign var = <tmp>（中间信号名可控）"""
    # 若 LLM 未给 wire_name，则兜底生成一个基于 lhs_name 的名字
    if wire_name and re.match(r'^[A-Za-z_]\w*$', wire_name) and wire_name not in VERILOG_KEYWORDS:
        tmp_name = wire_name
    else:
        tmp_name = f'__{target.lhs_name}_tmp'

    # 避免与现有标识符冲突
    while tmp_name in vs.all_identifiers():
        tmp_name += '_'
    
    line_start = code.rfind('\n', 0, target.start) + 1
    indent = ''
    for ch in code[line_start:target.start]:
        if ch in ' \t':
            indent += ch
        else:
            break
    
    # 获取目标信号的位宽信息
    lhs_signal = None
    for sig in vs.signals:
        if sig.name == target.lhs_name:
            lhs_signal = sig
            break
    
    # 构建wire声明（带位宽）
    if lhs_signal and lhs_signal.range_str:
        # 有显式位宽声明
        wire_decl = f'{indent}wire {lhs_signal.range_str} {tmp_name};\n'
    else:
        # 无显式位宽，使用默认（1位）
        wire_decl = f'{indent}wire {tmp_name};\n'
    
    # 使用标准assign语句进行赋值
    wire_assign = f'{indent}assign {tmp_name} = {target.rhs};\n'
    new_assign = f'{indent}assign {target.lhs} = {tmp_name};'
    
    return code[:line_start] + wire_decl + wire_assign + new_assign + code[target.end:]


# --- T32: 位宽算术变换（参数化） ---
@TargetTokenHandler(
    selector=Selectors.declarations,
    filter_func=Filters.is_port_or_wire_decl,
    name="T32"
)
def ast_bitwidth_arithmetic(
    code: str, 
    vs: VerilogStructure, 
    target: DeclInfo,
    offset: int = 1,
    use_multiply: bool = False
) -> str:
    """T32: [7:0] → [8-1:1-1] (支持自定义偏移)，保证输出合法且位宽不变。"""
    orig_width = target.high - target.low + 1
    if use_multiply:
        high_factor = (target.high + offset) // 2
        low_factor = (target.low + offset) // 2 if target.low > 0 else 0
        new_high = high_factor * 2 - offset
        new_low = low_factor * 2
        if new_high < new_low or (new_high - new_low + 1) != orig_width:
            return code
        new_text = f'[{high_factor}*2-{offset}:{low_factor}*2+{offset}-{offset}]'
    else:
        new_high = target.high + offset - offset
        new_low = target.low + offset - offset
        if new_high < new_low or (new_high - new_low + 1) != orig_width:
            return code
        new_text = f'[{target.high + offset}-{offset}:{target.low + offset}-{offset}]'
    return _replace_range(code, target.start, target.end, new_text)


# --- T34: 通用对抗性重命名（参数化） ---
def ast_universal_rename(
    code: str, 
    target_token: Optional[int] = None,
    custom_map: Optional[Dict[str, str]] = None,
    fallback_prefix: str = 'unused_',
    allow_port_rename: bool = False,  # 默认禁止端口重命名，避免testbench冲突
) -> str:
    """T34: 通用对抗性重命名（仅内部信号，不重命名端口）。

    返回 (code, rename_map) 供 testbench 同步替换。
    注意：默认不重命名端口，避免与testbench端口连接冲突。
    """
    vs = analyze(code)
    port_names = {p.name for p in vs.ports}
    existing_names = vs.all_identifiers()
    
    default_map = {
        'out': 'input_data', 'enable': 'disable', 'high': 'low',
        'valid': 'invalid', 'ready': 'busy', 'data': 'ctrl',
        'clk': 'reset', 'zero': 'one', 'one': 'zero',
        'sel': 'desel', 'active': 'inactive', 'start': 'stop',
        'write': 'read', 'set': 'clear',
    }
    
    if custom_map:
        adversarial_map = {**default_map, **custom_map}
    else:
        adversarial_map = default_map

    def _is_keyword(name: str) -> bool:
        return name in VERILOG_KEYWORDS

    # 与 _get_candidates_T34 保持一致：最多返回 2 个候选（优先内部，再端口）。
    internal_ordered = [
        s.name for s in vs.signals
        if s.name not in port_names and s.name and not _is_keyword(s.name)
    ]
    port_ordered = [
        p.name for p in vs.ports
        if p.name and not _is_keyword(p.name)
    ]

    internal_mapped = next((n for n in internal_ordered if n.lower() in adversarial_map), None)
    internal_fallback = next((n for n in internal_ordered if len(n) > 1), None)
    port_mapped = next((n for n in port_ordered if n.lower() in adversarial_map), None)
    port_fallback = next((n for n in port_ordered if len(n) > 0), None)

    probe_candidates: List[str] = []
    if internal_mapped is not None:
        probe_candidates.append(internal_mapped)
    elif internal_fallback is not None:
        probe_candidates.append(internal_fallback)

    if allow_port_rename and port_mapped is not None:
        if port_mapped not in probe_candidates:
            probe_candidates.append(port_mapped)
    elif allow_port_rename and port_fallback is not None:
        if port_fallback not in probe_candidates:
            probe_candidates.append(port_fallback)

    if not probe_candidates:
        return (code, None)

    if target_token is None:
        target_token = 0
    if target_token < 0 or target_token >= len(probe_candidates):
        return (code, None)

    original = probe_candidates[target_token]
    if original.lower() in adversarial_map:
        replacement = adversarial_map[original.lower()]
    else:
        replacement = f'{fallback_prefix}{original}'

    # 冲突/退化检查：避免关键字/重复/与现有标识符重合
    if replacement == original or _is_keyword(replacement):
        return (code, None)
    if replacement in existing_names:
        return (code, None)
    if not re.search(r'\b' + re.escape(original) + r'\b', code):
        return (code, None)

    new_code = re.sub(r'\b' + re.escape(original) + r'\b', replacement, code)
    if new_code == code:
        return (code, None)

    return (new_code, {original: replacement})


# --- T41: Case 分支重排（AST） ---
@TargetTokenHandler(selector=Selectors.case_blocks, filter_func=Filters.has_multiple_non_default_branches, name="T41")
def ast_case_branch_reorder(code: str, vs: VerilogStructure, target: CaseInfo) -> str:
    """T41: case 分支重排。用 CaseInfo.branches（AST 偏移）旋转非 default 分支。"""
    if not target.branches:
        # branches 未填充（pyslang 解析失败），回退到正则
        return _ast_case_branch_reorder_regex(code, target)

    non_default = [(s, e) for s, e, is_def in target.branches if not is_def]
    default_br  = [(s, e) for s, e, is_def in target.branches if is_def]

    if len(non_default) < 2:
        return code

    # 旋转：把第一个非 default 分支移到最后
    rotated = non_default[1:] + [non_default[0]]
    all_ordered = rotated + default_br

    # 按原始偏移顺序重建：先收集原始文本，再按新顺序拼接
    original_texts = [code[s:e] for s, e in non_default + default_br]
    new_texts = [code[s:e] for s, e in all_ordered]

    # 替换区间：从第一个分支开始到最后一个分支结束
    all_branches = non_default + default_br
    region_start = min(s for s, e in all_branches)
    region_end   = max(e for s, e in all_branches)

    # 保留分支之间的空白（间隔文本），按原始顺序拼接
    # 构建：原始分支按位置排序，提取间隔
    sorted_orig = sorted(non_default + default_br, key=lambda x: x[0])
    gaps = []
    for i in range(len(sorted_orig) - 1):
        gaps.append(code[sorted_orig[i][1]:sorted_orig[i+1][0]])

    # 新顺序的分支文本（按原始位置顺序对应新内容）
    sorted_new_texts = [code[s:e] for s, e in all_ordered]
    # 重新拼接：new_text[0] + gap[0] + new_text[1] + gap[1] + ...
    new_region = sorted_new_texts[0]
    for i, gap in enumerate(gaps):
        new_region += gap + sorted_new_texts[i + 1]

    return code[:region_start] + new_region + code[region_end:]


def _ast_case_branch_reorder_regex(code: str, target: CaseInfo) -> str:
    """T41 回退：正则解析 case 分支（当 AST branches 未填充时）。"""
    _CASE_BODY_RE = re.compile(r'\bcase\s*\([^)]+\)(.*?)\bendcase\b', re.DOTALL)
    _BRANCH_PATTERN = re.compile(
        r'(\b(?:default\s*:|[\w\']+\s*:).*?)(?=\b(?:default\s*:|[\w\']+\s*:)|\Z)', re.DOTALL
    )
    block_text = code[target.start:target.end]
    body_m = _CASE_BODY_RE.search(block_text)
    if not body_m:
        return code
    body = body_m.group(1)
    branches = _BRANCH_PATTERN.findall(body)
    non_default = [b for b in branches if not b.strip().startswith("default")]
    default_br = [b for b in branches if b.strip().startswith("default")]
    if len(non_default) < 2:
        return code
    rotated = non_default[1:] + [non_default[0]]
    new_body = "".join(rotated) + "".join(default_br)
    body_start_in_block = body_m.start(1)
    body_end_in_block = body_m.end(1)
    replace_start = target.start + body_start_in_block
    replace_end = target.start + body_end_in_block
    return code[:replace_start] + new_body + code[replace_end:]


# --- T45: 假性组合逻辑环 ---
def ast_pseudo_comb_loop(code: str, target_token: Optional[int] = None) -> str:
    """T45: 假性组合逻辑环 (利用矛盾项 X & ~X)。target_token 指定第几个连续赋值（从 0 计）。"""
    vs = analyze(code)
    cont = vs.continuous_assigns()
    inps = [p.name for p in vs.ports if p.direction == "input"]
    if not cont or not inps:
        return code

    idx = 0 if target_token is None else max(0, min(target_token, len(cont) - 1))
    asgn = cont[idx]
    inp = inps[0]  # 矛盾项固定用第一个 input

    new_rhs = f"({inp} & ~{inp}) ? ~{asgn.lhs_name} : {asgn.rhs}"
    return code[: asgn.start] + f"assign {asgn.lhs} = {new_rhs};" + code[asgn.end :]


# --- T47: 数据流破碎（参数化） ---
@TargetTokenHandler(
    selector=Selectors.continuous_assigns,
    name="T47"
)
def ast_dataflow_shattering(
    code: str, 
    vs: VerilogStructure, 
    target: AssignInfo,
    width: int = None
) -> str:
    """T47: Shannon 展开比较器/加法器。自动检测位宽，确保功能等价。"""
    expr = target.rhs_expr
    # 支持 equality (==) 和 add (+)，以及 ParenthesizedExpression 包裹的情况
    if expr and expr.kind in ('equality', 'add'):
        a = expr.left_text.strip()
        op = expr.op.strip()
        b = expr.right_text.strip()
    else:
        # rhs_expr 未解析到目标类型，回退到正则
        comp_m = re.search(
            r'\(?\s*([a-zA-Z_][a-zA-Z0-9_\[\]]*)\s*(==|\+)\s*([a-zA-Z_][a-zA-Z0-9_\[\]]*)\s*\)?',
            target.rhs
        )
        if not comp_m:
            return code
        a, op, b = comp_m.group(1), comp_m.group(2), comp_m.group(3)

    # 提取信号名（去除位选择）
    a_name = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)', a).group(1) if a else None
    b_name = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)', b).group(1) if b else None
    
    # 自动检测位宽（如果未指定）
    if width is None:
        # 获取操作数的实际位宽
        a_width = vs.get_width(a_name) if a_name else 1
        b_width = vs.get_width(b_name) if b_name else 1
        
        # 对于比较操作，使用两者中的较大位宽
        # 对于加法操作，也使用较大位宽（结果可能需要额外的进位位）
        width = max(a_width, b_width)
        
        # 如果检测失败或位宽为1，使用默认值4（但这可能仍然不正确）
        if width <= 1:
            width = 4
    
    # 验证位宽合理性（避免过大的展开）
    if width > 32:
        # 位宽过大，不适合Shannon展开，保持原样
        return code
    
    out_var = target.lhs_name or target.lhs
    wires = []

    if op == '==':
        for i in range(width):
            wire_name = f'_n{i+1:02d}'
            wires.append(f'  wire {wire_name} = {a}[{i}] ^ {b}[{i}];')
        final_expr = ' & '.join([f'~_n{i+1:02d}' for i in range(width)])
        wires.append(f'  assign {out_var} = {final_expr};')
    else:  # op == '+'
        wires.append(f'  wire _n01 = {a}[0] ^ {b}[0];')
        wires.append(f'  wire _c01 = {a}[0] & {b}[0];')
        for i in range(1, width):
            wires.append(f'  wire _n{i+1:02d} = {a}[{i}] ^ {b}[{i}] ^ _c{i:02d};')
            wires.append(f'  wire _c{i+1:02d} = ({a}[{i}] & {b}[{i}]) | ({a}[{i}] & _c{i:02d}) | ({b}[{i}] & _c{i:02d});')
        sum_bits = ', '.join([f'_n{i+1:02d}' for i in range(width)])
        wires.append(f'  assign {out_var} = {{{sum_bits}}};')

    new_code = '\n'.join(wires)
    return code[:target.start] + new_code + code[target.end:]


# --- T48: 逆向拓扑重排 ---
def ast_anti_topological_shuffle(code: str, target_token: Optional[int] = None) -> str:
    """T48: 逆向拓扑并发重排 (颠倒赋值语句顺序)"""
    vs = analyze(code)
    assigns = [a for a in vs.assignments if a.kind == 'continuous']
    if len(assigns) < 2: 
        return code
    
    # 收集所有assign语句的文本
    assign_texts = [code[a.start:a.end] for a in assigns]
    # 反转顺序
    reversed_texts = list(reversed(assign_texts))
    
    # 从后向前替换，避免偏移量变化
    result = code
    for i in range(len(assigns) - 1, -1, -1):
        a = assigns[i]
        new_text = reversed_texts[i]
        result = result[:a.start] + new_text + result[a.end:]
    
    return result


# ============================================================================
# LLM 调用接口
# ============================================================================

class VerilogObfuscationEngine:
    """供 LLM 调用的高级接口"""
    
    def __init__(self):
        self.registry: Dict[str, Transform] = {}
    
    def get_available_transforms(self) -> List[dict]:
        """返回所有可用规则的 JSON Schema"""
        return [t.to_llm_schema() for t in self.registry.values()]
    
    def get_transform_info(self, transform_id: str) -> Optional[dict]:
        """获取单个规则的详细信息"""
        if transform_id not in self.registry:
            return None
        return self.registry[transform_id].to_llm_schema()
    
    def apply_transform(
        self, 
        code: str, 
        transform_id: str, 
        target_token: Optional[int] = None,
        **params
    ) -> str:
        """
        执行变换
        
        Args:
            code: 原始代码
            transform_id: 规则 ID（如 'T32'）
            target_token: 目标索引
            **params: 规则特定的参数
        
        Returns:
            变换后的代码
        """
        if transform_id not in self.registry:
            raise ValueError(f"未知的规则 ID: {transform_id}")
        
        transform = self.registry[transform_id]
        
        target_line = params.pop("target_line", None)
        target_signal = params.pop("target_signal", None)
        # 统一解析：若调用方只给了 target_line/target_signal 未给 target_token，先解析为候选索引（与 nth_occurrence 等价）
        if target_token is None and (target_line is not None or target_signal is not None):
            resolved = self._resolve_target_token(code, transform_id, target_line, target_signal)
            if resolved is not None:
                target_token = resolved
        validated_params = self._validate_params(transform, params)
        sig = inspect.signature(transform.apply_func)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            if target_line is not None:
                validated_params["target_line"] = target_line
            if target_signal is not None:
                validated_params["target_signal"] = target_signal
        # 未用 TargetTokenHandler 的变换（T03/T04/T07/T19/T20）已在上方用 target_token 解析，此处仅对装饰器传 line/signal
        
        self._last_rename_map = None
        result = transform.apply_func(code, target_token, **validated_params)
        if isinstance(result, tuple) and len(result) == 2:
            code, self._last_rename_map = result[0], result[1]
        else:
            code = result
        return code
    
    def get_last_rename_map(self):
        """重命名类规则应用后，返回本次使用的 旧名->新名 映射；非重命名或未应用时为 None。"""
        return getattr(self, '_last_rename_map', None)
    
    def _get_candidates_for_transform(self, code: str, transform_id: str) -> List[Any]:
        """获取某变换的候选列表（与 get_target_line_signal 一致），用于解析 target_line/target_signal。"""
        tid = TRANSFORM_ALIASES.get(transform_id, transform_id)
        if tid in AST_CANDIDATES_GETTER:
            return AST_CANDIDATES_GETTER[tid](code)
        sel_filter = AST_SELECTOR_REGISTRY.get(tid)
        if not sel_filter:
            return []
        selector, filter_func = sel_filter
        vs = analyze(code)
        all_items = selector(vs)
        if filter_func:
            return [item for item in all_items if filter_func(item, vs)]
        return all_items

    def _resolve_target_token(
        self,
        code: str,
        transform_id: str,
        target_line: Optional[int],
        target_signal: Optional[str],
    ) -> Optional[int]:
        """
        将 target_line / target_signal 解析为 0-based 候选索引，与 get_target_line_signal 的候选顺序一致。
        优先按 target_signal 匹配，再按 target_line；保证与「先 nth_occurrence 转 line/signal，再按 line/signal 选」一致。
        """
        candidates = self._get_candidates_for_transform(code, transform_id)
        if not candidates:
            return None
        idx = None
        if target_signal:
            idx = _select_target_by_signal(candidates, code, str(target_signal))
        if idx is None and target_line is not None:
            try:
                idx = _select_target_by_line(candidates, code, int(target_line))
            except (TypeError, ValueError):
                pass
        return idx

    def get_target_line_signal(
        self, code: str, transform_id: str, target_token: int
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        根据 target_token（0-based 候选索引）返回该候选对应的 (target_line, target_signal)。
        用于将 SFT 中的 nth_occurrence 转为 target_line/target_signal。
        应用时通过 _resolve_target_token 用同一套候选列表 + _select_target_by_signal/line 反解回索引，
        故与「nth_occurrence 指定第 N 个候选」一一对应；仅当多个候选落在同一行或同一信号时按「第一个匹配」选。
        若该变换无法解析或候选不足，返回 (None, None)。
        """
        candidates = self._get_candidates_for_transform(code, transform_id)
        if target_token is None or target_token < 0 or target_token >= len(candidates):
            return (None, None)
        item = candidates[target_token]
        lo, hi = _item_line_range(code, item)
        sig = _item_signal(item)
        return (lo, sig if sig else None)
    
    def _validate_params(self, transform: Transform, params: dict) -> dict:
        """验证并转换参数类型"""
        validated = {}
        
        for param_spec in transform.params:
            value = params.get(param_spec.name, param_spec.default)
            
            # 类型转换
            if param_spec.type == 'int':
                value = int(value)
                if param_spec.min_val is not None and value < param_spec.min_val:
                    logger.warning(f"参数 {param_spec.name} 值 {value} 小于最小值 {param_spec.min_val}，使用最小值")
                    value = int(param_spec.min_val)
                if param_spec.max_val is not None and value > param_spec.max_val:
                    logger.warning(f"参数 {param_spec.name} 值 {value} 大于最大值 {param_spec.max_val}，使用最大值")
                    value = int(param_spec.max_val)
            
            elif param_spec.type == 'float':
                value = float(value)
                if param_spec.min_val is not None and value < param_spec.min_val:
                    value = float(param_spec.min_val)
                if param_spec.max_val is not None and value > param_spec.max_val:
                    value = float(param_spec.max_val)
            
            elif param_spec.type == 'bool':
                if isinstance(value, str):
                    value = value.lower() in ('true', '1', 'yes')
                else:
                    value = bool(value)
            
            elif param_spec.type == 'dict':
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        logger.warning(f"参数 {param_spec.name} JSON 解析失败，使用默认值")
                        value = param_spec.default
            
            elif param_spec.type == 'choice':
                if param_spec.choices and value not in param_spec.choices:
                    logger.warning(f"参数 {param_spec.name} 值 {value} 不在选项中，使用默认值")
                    value = param_spec.default
            
            validated[param_spec.name] = value
        
        return validated


# ============================================================================
# 注册表（带完整参数规范）
# ============================================================================

AST_TRANSFORM_REGISTRY: Dict[str, Transform] = {
    'T03': Transform(
        'T03', 'Redundant Logic', 'signal & 1\'b1', 
        ast_redundant_logic, 'visual', 2,
        params=[
            ParamSpec(
                name='redundant_name',
                type='str',
                default='',
                description='外部指定冗余信号名（留空则使用 name_prefix+端口名）',
            ),
            ParamSpec(
                name='name_prefix',
                type='str',
                default='_tap_',
                description='在未显式给 redundant_name 时使用的前缀',
            ),
        ]
    ),
    
    'T07': Transform(
        'T07', 'Assign Reorder', 'Shuffle assigns', 
        ast_assign_reorder, 'structure', 2,
        params=[]
    ),
    
    'T09': Transform(
        'T09', 'DeMorgan AND', 'a&b -> ~(~a|~b)', 
        ast_demorgan_and, 'logic', 4,
        params=[]
    ),
    
    'T10': Transform(
        'T10', 'DeMorgan OR', 'a|b -> ~(~a&~b)', 
        ast_demorgan_or, 'logic', 4,
        params=[]
    ),
    
    'T12': Transform(
        'T12', 'Intermediate Signal', 'sel -> wire_tmp', 
        ast_intermediate_signal, 'logic', 4,
        params=[
            ParamSpec(
                name='wire_name',
                type='str',
                default='',
                description='中间信号名，留空则自动生成 __{sel}_tmp'
            ),
        ]
    ),
    
    'T19': Transform(
        'T19', 'False Pattern', 'Dead code always', 
        ast_false_pattern_inject, 'visual', 4,
        params=[
            ParamSpec(
                name='custom_dead_stmts',
                type='str',
                default='',
                description='自定义死代码语句（会被包进 if(1\'b0) 不可达分支；默认空则使用固定模板）'
            )
        ]
    ),
    
    'T20': Transform(
        'T20', 'Flexible Misleading Comment', 'Insert context-aware misleading comment',
        ast_flexible_comment, 'visual', 4,
        params=[
            ParamSpec(
                name='custom_text',
                type='str',
                default='',
                description='自定义误导性描述'
            )
        ]
    ),
    
    'T30': Transform(
        'T30', 'Constant Identity', '1\'b0 -> (1&0)', 
        ast_constant_identity, 'logic', 3,
        params=[
            ParamSpec(
                name='zero_pattern',
                type='choice',
                default="(1'b1 & 1'b0)",
                choices=[
                    "(1'b1 & 1'b0)",
                    "(~1'b1)",
                    "(1'b0 | 1'b0)",
                    "(1'b1 ^ 1'b1)"
                ],
                description='替换 1\'b0 的等价表达式'
            ),
            ParamSpec(
                name='one_pattern',
                type='choice',
                default="(1'b1 | 1'b0)",
                choices=[
                    "(1'b1 | 1'b0)",
                    "(~1'b0)",
                    "(1'b1 & 1'b1)",
                    "(1'b0 ^ 1'b1)"
                ],
                description='替换 1\'b1 的等价表达式'
            )
        ]
    ),
    
    'T31': Transform(
        'T31', 'Simple Intermediate', 'assign x=y -> wire t=y; assign x=t', 
        ast_simple_assign_intermediate, 'logic', 4,
        params=[
            ParamSpec(
                name='wire_name',
                type='str',
                default='',
                description='中间信号名（空则自动生成 __{lhs}_tmp）'
            )
        ]
    ),
    
    'T32': Transform(
        'T32', 'Bitwidth Arithmetic', '[7:0] -> [8-1:0]', 
        ast_bitwidth_arithmetic, 'structure', 2,
        params=[
            ParamSpec(
                name='offset',
                type='int',
                default=1,
                description='算术偏移量（决定 x+offset-offset 的值）',
                min_val=1,
                max_val=10
            ),
            ParamSpec(
                name='use_multiply',
                type='bool',
                default=False,
                description='是否使用乘法形式（如 2*4-1 而非 8-1）'
            )
        ]
    ),
    
    'T34': Transform(
        'T34', 'Internal Signal Rename', 'Misleading internal signals (ports excluded)', 
        ast_universal_rename, 'visual', 3,
        params=[
            ParamSpec(
                name='custom_map',
                type='dict',
                default={},
                description='自定义重命名映射表'
            ),
            ParamSpec(
                name='fallback_prefix',
                type='str',
                default='unused_',
                description='兜底前缀'
            )
        ]
    ),
    
    'T41': Transform(
        'T41', 'Case Reorder', 'Rotate case branches', 
        ast_case_branch_reorder, 'structure', 2,
        params=[]
    ),
    
    'T45': Transform(
        'T45', 'Pseudo Loop', 'X&~X contradiction', 
        ast_pseudo_comb_loop, 'logic', 5,
        params=[]
    ),
    
    'T47': Transform(
        'T47', 'Dataflow Shatter', 'Shannon expansion', 
        ast_dataflow_shattering, 'structure', 5,
        params=[
            ParamSpec(
                name='width',
                type='int',
                default=4,
                description='位宽（用于 Shannon 展开）',
                min_val=2,
                max_val=16
            )
        ]
    ),
    
    'T48': Transform(
        'T48', 'Anti-Topological', 'Reverse statement order', 
        ast_anti_topological_shuffle, 'structure', 4,
        params=[]
    ),
}

# 用于 get_target_line_signal：transform_id -> (selector, filter_func)
AST_SELECTOR_REGISTRY: Dict[str, Tuple[Callable, Optional[Callable]]] = {
    # T03: 在 analyze 中自行过滤 input/output 端口，这里先选出所有端口
    "T03": (lambda vs: getattr(vs, "ports", []), None),
    "T09": (Selectors.binary_and_exprs, None),
    "T10": (Selectors.binary_or_exprs, None),
    "T12": (Selectors.continuous_assigns, Filters.has_ternary_rhs),
    "T30": (Selectors.continuous_assigns, Filters.has_bit_constant),
    "T31": (Selectors.continuous_assigns, None),
    "T32": (Selectors.declarations, Filters.is_port_or_wire_decl),
    "T34": (Selectors.continuous_assigns, None),
    "T47": (Selectors.continuous_assigns, Filters.has_equality_or_add_rhs),
    "T45": (Selectors.continuous_assigns, Filters.has_input_port),
    "T48": (Selectors.continuous_assigns, Filters.has_multiple_continuous_assigns),
    "T41": (Selectors.case_blocks, Filters.has_multiple_non_default_branches),
}


def _get_candidates_T07(code: str) -> List[AssignInfo]:
    """T07 可交换对中每对的第一个 assign（相邻对优先，再非相邻对）。"""
    vs = analyze(code)
    assigns = vs.continuous_assigns()
    if len(assigns) < 2:
        return []
    pairs = _t07_valid_pairs(assigns, code)
    return [assigns[i] for i, j in pairs]


def _get_candidates_T34(code: str) -> List[Any]:
    """T34 候选：只返回内部信号，不包括端口（避免testbench冲突）。"""
    vs = analyze(code)
    port_names = {p.name for p in vs.ports}
    default_map = {
        'out', 'enable', 'high', 'valid', 'ready', 'data', 'clk', 'zero',
        'one', 'sel', 'active', 'start', 'write', 'set', 'disable', 'low',
        'invalid', 'busy', 'ctrl', 'reset', 'desel', 'inactive', 'stop',
        'read', 'clear',
    }
    internal_ordered = [
        s.name for s in vs.signals
        if s.name not in port_names and s.name and s.name not in VERILOG_KEYWORDS
    ]
    port_ordered = [
        p.name for p in vs.ports
        if p.name and p.name not in VERILOG_KEYWORDS
    ]

    internal_mapped = next((n for n in internal_ordered if n.lower() in default_map), None)
    internal_fallback = next((n for n in internal_ordered if len(n) > 1), None)
    port_mapped = next((n for n in port_ordered if n.lower() in default_map), None)
    port_fallback = next((n for n in port_ordered if len(n) > 0), None)

    candidates: List[str] = []
    if internal_mapped is not None:
        candidates.append(internal_mapped)
    elif internal_fallback is not None:
        candidates.append(internal_fallback)

    # 不再添加端口到候选列表，只重命名内部信号
    # 这样避免端口重命名导致testbench连接失败
    # if port_mapped is not None and port_mapped not in candidates:
    #     candidates.append(port_mapped)
    # elif port_fallback is not None and port_fallback not in candidates:
    #     candidates.append(port_fallback)

    return candidates


def _get_candidates_T04_T20(code: str) -> List[CommentInsertPoint]:
    """T04/T20 注释插入点。"""
    vs = analyze(code)
    return _extract_comment_insert_points(code, vs)


def _get_candidates_T19(code: str) -> List[Any]:
    """T19 注入位置为 endmodule 前，返回一个占位项以便得到行号。"""
    pos = code.find("endmodule")
    if pos < 0:
        return []
    return [type("_T19Item", (), {"start": pos, "end": pos + 9})()]


# 需要 code 才能得到候选的变换：transform_id -> (code -> candidates)
AST_CANDIDATES_GETTER: Dict[str, Callable[[str], List[Any]]] = {
    "T07": _get_candidates_T07,
    "T19": _get_candidates_T19,
    "T20": _get_candidates_T04_T20,
    "T34": _get_candidates_T34,
}


# ============================================================================
# 语义化别名与映射
# ============================================================================

TRANSFORM_ALIASES: Dict[str, str] = {
    'EXPR_DEMORGAN_AND': 'T09', 'EXPR_DEMORGAN_OR': 'T10',
    'EXPR_CONST_IDENTITY': 'T30',
    'TOPO_ASSIGN_REORDER': 'T07', 'TOPO_INTERMEDIATE_SIGNAL': 'T12',
    'TOPO_DATAFLOW_SHATTER': 'T47', 'TOPO_ANTI_TOPOLOGICAL': 'T48',
    'NAME_ADVERSARIAL': 'T34', 'GHOST_FALSE_PATTERN': 'T19',
    'DOC_COMMENT_DECOY': 'T20', 'DOC_BITWIDTH_ARITHMETIC': 'T32'
}

TRANSFORM_SEMANTIC_NAMES = {v: k for k, v in TRANSFORM_ALIASES.items()}


# ============================================================================
# 工厂函数
# ============================================================================

def create_engine() -> VerilogObfuscationEngine:
    """创建并初始化混淆引擎"""
    engine = VerilogObfuscationEngine()
    engine.registry = AST_TRANSFORM_REGISTRY
    return engine


def patch_registry():
    """注入 AST 版本到全局注册表"""
    try:
        from src.rules.transformations import TRANSFORM_REGISTRY
        for tid, t in AST_TRANSFORM_REGISTRY.items():
            TRANSFORM_REGISTRY[tid] = t
        logger.info(f"[AST] Successfully patched {len(AST_TRANSFORM_REGISTRY)} rules.")
    except ImportError:
        logger.warning("[AST] Global TRANSFORM_REGISTRY not found for patching.")


def apply_ast_transform(code: str, name: str, **params) -> str:
    """按别名或 ID 应用变换（支持参数）。支持 target_token、target_line（1-based）、target_signal。"""
    tid = TRANSFORM_ALIASES.get(name, name)
    t = AST_TRANSFORM_REGISTRY.get(tid)
    if not t:
        return code
    
    target_token = params.pop("target_token", None)
    target_line = params.pop("target_line", None)
    target_signal = params.pop("target_signal", None)
    if target_line is not None:
        params["target_line"] = target_line
    if target_signal is not None:
        params["target_signal"] = target_signal
    return t.apply_func(code, target_token, **params)


# ============================================================================
# LLM 使用示例
# ============================================================================

def example_llm_usage():
    """演示 LLM 如何调用该引擎"""
    
    # 创建引擎
    engine = create_engine()
    
    # 1. LLM 查询可用的变换规则
    available_transforms = engine.get_available_transforms()
    print("=== 可用的变换规则 ===")
    for transform in available_transforms[:3]:  # 只显示前 3 个
        print(json.dumps(transform, indent=2))
    
    # 2. LLM 获取特定规则的详细信息
    t32_info = engine.get_transform_info('T32')
    print("\n=== T32 规则详情 ===")
    print(json.dumps(t32_info, indent=2))
    
    # 3. 示例代码
    verilog_code = """
module test(
    input [7:0] data_in,
    input enable,
    output [7:0] result
);
    assign result = enable ? data_in : 8'h00;
endmodule
"""
    
    print("\n=== 原始代码 ===")
    print(verilog_code)
    
    # 4. LLM 决策：应用 T32 变换（自定义参数）
    print("\n=== 应用 T32 (offset=2, use_multiply=False) ===")
    obf_code = engine.apply_transform(
        code=verilog_code,
        transform_id='T32',
        target_token=0,
        offset=2,
        use_multiply=False
    )
    print(obf_code)
    
    # 5. LLM 决策：应用 T30 变换（自定义模式）
    print("\n=== 应用 T30 (自定义 zero_pattern) ===")
    obf_code2 = engine.apply_transform(
        code=verilog_code,
        transform_id='T30',
        target_token=0,
        zero_pattern="(~1'b1)",
        one_pattern="(~1'b0)"
    )
    print(obf_code2)
    
    # 6. LLM 决策：应用 T34 变换（自定义映射；包含端口名重命名能力）
    print("\n=== 应用 T34 (自定义映射表) ===")
    obf_code3 = engine.apply_transform(
        code=verilog_code,
        transform_id='T34',
        custom_map={"enable": "signal_invalid", "result": "garbage_out"},
        fallback_prefix="hidden_",
    )
    print(obf_code3)
    
    # 7. LLM 决策：应用 T12 变换（自定义前后缀）
    print("\n=== 应用 T12 (自定义 prefix/suffix) ===")
    obf_code4 = engine.apply_transform(
        code=verilog_code,
        transform_id='T12',
        target_token=0,
        prefix='_internal_',
        suffix='_signal'
    )
    print(obf_code4)
    
    # 8. LLM 决策序列（多步变换）
    print("\n=== 多步变换序列 ===")
    code = verilog_code
    
    # 步骤 1: 位宽算术化
    code = engine.apply_transform(code, 'T32', target_token=0, offset=1)
    print("步骤 1 (T32):")
    print(code)
    
    # 步骤 2: 添加误导性注释
    code = engine.apply_transform(code, 'T20', custom_description="SPI Master Controller - Mode 3")
    print("\n步骤 2 (T20):")
    print(code)
    
    # 步骤 3: 三元表达式中间信号注入
    code = engine.apply_transform(code, 'T12', prefix='__ctrl_', suffix='_sel')
    print("\n步骤 3 (T12):")
    print(code)


# ============================================================================
# 强化学习接口（为 LLM Agent 设计）
# ============================================================================

class RLObfuscationInterface:
    """强化学习专用接口"""
    
    def __init__(self):
        self.engine = create_engine()
        self.history: List[Dict] = []
    
    def get_state_representation(self, code: str) -> dict:
        """
        获取代码的状态表示（供 RL Agent 作为状态空间）
        
        Returns:
            包含代码特征的字典
        """
        vs = analyze(code)
        return {
            'num_ports': len(vs.ports),
            'num_signals': len(vs.signals),
            'num_assignments': len(vs.assignments),
            'num_always_blocks': len(vs.always_blocks),
            'num_ternary_exprs': len(vs.ternary_exprs()),
            'num_binary_and': len(vs.binary_and_exprs()),
            'num_binary_or': len(vs.binary_or_exprs()),
            'code_length': len(code),
            'has_fsm': len(Selectors.fsm_state_signals(vs)) > 0,
        }
    
    def get_action_space(self) -> List[dict]:
        """
        获取动作空间（所有可用的变换及其参数）
        
        Returns:
            动作空间定义
        """
        return self.engine.get_available_transforms()
    
    def step(self, code: str, action: dict) -> Tuple[str, dict]:
        """
        执行一步变换（RL 的 step 函数）
        
        Args:
            code: 当前代码
            action: 包含 transform_id, target_token, params 的字典
        
        Returns:
            (新代码, 执行信息)
        """
        transform_id = action['transform_id']
        target_token = action.get('target_token', None)
        params = action.get('params', {})
        
        try:
            new_code = self.engine.apply_transform(
                code=code,
                transform_id=transform_id,
                target_token=target_token,
                **params
            )
            
            success = new_code != code
            
            info = {
                'success': success,
                'transform_id': transform_id,
                'code_length_delta': len(new_code) - len(code),
            }
            
            # 记录历史
            self.history.append({
                'action': action,
                'info': info,
            })
            
            return new_code, info
            
        except Exception as e:
            logger.error(f"变换执行失败: {e}")
            return code, {'success': False, 'error': str(e)}
    
    def reset(self):
        """重置历史记录"""
        self.history = []


# ============================================================================
# 测试与演示
# ============================================================================

if __name__ == "__main__":
    # 基础使用示例
    print("=" * 60)
    print("基础使用示例")
    print("=" * 60)
    example_llm_usage()
    
    # RL 接口示例
    print("\n" + "=" * 60)
    print("强化学习接口示例")
    print("=" * 60)
    
    rl_interface = RLObfuscationInterface()
    
    code = """
module counter(
    input clk,
    input rst,
    output [7:0] count
);
    reg [7:0] count;
    always @(posedge clk) begin
        if (rst)
            count <= 8'h00;
        else
            count <= count + 1;
    end
endmodule
"""
    
    # 获取状态表示
    state = rl_interface.get_state_representation(code)
    print("代码状态:", json.dumps(state, indent=2))
    
    # 获取动作空间
    action_space = rl_interface.get_action_space()
    print(f"\n可用动作数量: {len(action_space)}")
    
    # 执行一个动作
    action = {
        'transform_id': 'T32',
        'target_token': 0,
        'params': {'offset': 2, 'use_multiply': False}
    }
    
    new_code, info = rl_interface.step(code, action)
    print(f"\n动作执行结果: {info}")
    print("\n变换后代码:")
    print(new_code)

