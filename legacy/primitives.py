"""
6 Core Attack Primitives - Compressed from 34 transformation rules.

Each primitive encapsulates a family of semantically related attacks with
parameterized control over strategy and intensity. Designed for cleaner
action spaces in RL/search-based attack frameworks and stronger paper narratives.

Primitives:
    P1: Expr-Morph    - Expression rewrite       (T09,T10,T22,T30)
    P2: Topo-Shatter  - Topology fragmentation   (T07,T12,T31,T35,T47,T48)
    P3: Seq-Morph     - Temporal restructure      (T40,T41)
    P4: Ghost-Inject  - Phantom injection         (T03,T19,T45)
    P5: Name-Corrupt  - Identifier corruption     (T34)
    P6: Doc-Camouflage - Documentation camouflage (T20,T32)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Any, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class PrimitiveResult:
    """Result of applying an attack primitive."""
    code: str
    changed: bool
    primitive_id: str
    applied_rules: List[str]
    params_used: Dict[str, Any]
    description: str


@dataclass
class AttackPrimitive:
    """A high-level attack primitive encapsulating multiple T-rules."""
    id: str                          # P1-P6
    name: str                        # Short name (e.g., 'Expr-Morph')
    full_name: str                   # Full descriptive name
    description: str
    constituent_rules: List[str]     # T-rule IDs this primitive wraps
    apply_func: Callable             # (code, **params) -> PrimitiveResult
    category: str                    # expression/topology/temporal/phantom/identifier/documentation
    attack_dimension: str            # What cognitive/structural dimension it attacks
    default_params: Dict[str, Any]   # Default parameter values


# ============================================================================
# P1: Expr-Morph - Expression Rewrite
# Source: T09, T10, T22, T30
# ============================================================================

def apply_expr_morph(
    code: str,
    complexity_level: int = 3,
    transformation_type: str = 'auto',
    target_token: Optional[int] = None,
) -> PrimitiveResult:
    """
    P1: Expression Rewrite.
    Transforms boolean/arithmetic expressions into logically equivalent
    but structurally complex forms.

    Args:
        complexity_level: 1-5, controls how many/which sub-rules to apply.
        transformation_type: 'demorgan' | 'ternary' | 'constant' | 'parentheses' | 'auto'
        target_token: optional token position hint passed to underlying rules.
    """
    from transformations import apply_transform, TRANSFORM_REGISTRY

    # Rule candidates per type, ordered by increasing complexity
    type_rules: Dict[str, List[str]] = {
        'demorgan':    ['T09', 'T10', 'T22'],
        # T11/T37 removed; use T12 to handle ternary-related expression shapes.
        'ternary':     ['T12'],
        'constant':    ['T30'],
        'parentheses': ['T30'],
    }

    complexity_level = max(1, min(5, complexity_level))

    if transformation_type == 'auto':
        if '?' in code and ':' in code:
            transformation_type = 'ternary'
        elif '&' in code or '|' in code:
            transformation_type = 'demorgan'
        elif "1'b" in code or "1'h" in code:
            transformation_type = 'constant'
        else:
            transformation_type = 'parentheses'

    candidates = type_rules.get(transformation_type, type_rules['demorgan'])
    # complexity_level controls how many rules from the list to try
    candidates = candidates[:complexity_level]

    applied_rules: List[str] = []
    result_code = code

    for rule_id in candidates:
        if rule_id not in TRANSFORM_REGISTRY:
            continue
        try:
            new_code = apply_transform(result_code, rule_id, target_token)
            if new_code != result_code:
                result_code = new_code
                applied_rules.append(TRANSFORM_REGISTRY[rule_id].name)
                if complexity_level <= 2:
                    break  # Low complexity: stop after first successful rule
        except Exception as e:
            logger.debug(f"P1 rule {rule_id} failed: {e}")

    return PrimitiveResult(
        code=result_code,
        changed=result_code != code,
        primitive_id='P1',
        applied_rules=applied_rules,
        params_used={'complexity_level': complexity_level, 'transformation_type': transformation_type},
        description=f"Expr-Morph(type={transformation_type}, level={complexity_level})",
    )


# ============================================================================
# P2: Topo-Shatter - Topology Fragmentation
# Source: T07, T12, T31, T35, T47, T48
# ============================================================================

def apply_topo_shatter(
    code: str,
    fragmentation_depth: int = 3,
    reorder_pattern: str = 'none',
    target_token: Optional[int] = None,
) -> PrimitiveResult:
    """
    P2: Topology Fragmentation.
    Breaks direct signal paths by inserting intermediate wire nodes or
    reordering assignment statements.

    Args:
        fragmentation_depth: 1-10, controls depth of intermediate signal injection.
        reorder_pattern: 'none' | 'reverse' | 'shuffle'
        target_token: optional token position hint.
    """
    from transformations import apply_transform, TRANSFORM_REGISTRY

    # Select fragmentation rules based on depth tier
    if fragmentation_depth <= 2:
        frag_rules = ['T12']
    elif fragmentation_depth <= 4:
        frag_rules = ['T31', 'T35']
    elif fragmentation_depth <= 7:
        frag_rules = ['T31']
    else:
        frag_rules = ['T47']

    reorder_rules: Dict[str, List[str]] = {
        'reverse': ['T48'],
        'shuffle': ['T07', 'T48'],
        'none': [],
    }

    rules_to_apply = frag_rules + reorder_rules.get(reorder_pattern, [])
    applied_rules: List[str] = []
    result_code = code

    for rule_id in rules_to_apply:
        if rule_id not in TRANSFORM_REGISTRY:
            continue
        try:
            new_code = apply_transform(result_code, rule_id, target_token)
            if new_code != result_code:
                result_code = new_code
                applied_rules.append(TRANSFORM_REGISTRY[rule_id].name)
        except Exception as e:
            logger.debug(f"P2 rule {rule_id} failed: {e}")

    return PrimitiveResult(
        code=result_code,
        changed=result_code != code,
        primitive_id='P2',
        applied_rules=applied_rules,
        params_used={'fragmentation_depth': fragmentation_depth, 'reorder_pattern': reorder_pattern},
        description=f"Topo-Shatter(depth={fragmentation_depth}, reorder={reorder_pattern})",
    )


# ============================================================================
# P3: Seq-Morph - Temporal Restructure
# Source: T40, T41
# ============================================================================

def apply_seq_morph(
    code: str,
    restructure_type: str = 'auto',
    target_token: Optional[int] = None,
) -> PrimitiveResult:
    """
    P3: Temporal Restructure.
    Reorganizes sequential logic blocks and FSMs while preserving
    state transition equivalence.

    Args:
        restructure_type: 'split' | 'reset' | 'case' | 'auto'
        target_token: optional token position hint.
    """
    from transformations import apply_transform, TRANSFORM_REGISTRY

    type_rules: Dict[str, List[str]] = {
        'split':  [],
        'reset':  ['T40'],
        'case':   ['T41'],
        'auto':   ['T41', 'T40'],
    }

    candidates = type_rules.get(restructure_type, type_rules['auto'])
    applied_rules: List[str] = []
    result_code = code

    for rule_id in candidates:
        if rule_id not in TRANSFORM_REGISTRY:
            continue
        try:
            new_code = apply_transform(result_code, rule_id, target_token)
            if new_code != result_code:
                result_code = new_code
                applied_rules.append(TRANSFORM_REGISTRY[rule_id].name)
                if restructure_type != 'auto':
                    break  # Non-auto: stop after first success
        except Exception as e:
            logger.debug(f"P3 rule {rule_id} failed: {e}")

    return PrimitiveResult(
        code=result_code,
        changed=result_code != code,
        primitive_id='P3',
        applied_rules=applied_rules,
        params_used={'restructure_type': restructure_type},
        description=f"Seq-Morph(type={restructure_type})",
    )


# ============================================================================
# P4: Ghost-Inject - Phantom Injection
# Source: T03, T19, T45
# ============================================================================

def apply_ghost_inject(
    code: str,
    phantom_type: str = 'deadcode',
    complexity: int = 2,
    target_token: Optional[int] = None,
) -> PrimitiveResult:
    """
    P4: Phantom Injection.
    Injects dead code that appears functional but has no semantic effect,
    causing cognitive overload in the model.

    Args:
        phantom_type: 'loop' | 'deadcode' | 'redundant' | 'auto'
        complexity: 1-5, controls how elaborate the phantom is.
        target_token: optional token position hint.
    """
    from transformations import apply_transform, TRANSFORM_REGISTRY

    type_rules: Dict[str, List[str]] = {
        'loop':      ['T45'],
        'deadcode':  ['T19'],
        'redundant': ['T03'],
        'auto':      ['T45', 'T19', 'T03'],
    }

    candidates = type_rules.get(phantom_type, type_rules['auto'])

    # Higher complexity: prepend strongest phantoms
    if complexity >= 4:
        strong = [r for r in ['T45'] if r not in candidates[:2]]
        candidates = strong + candidates

    applied_rules: List[str] = []
    result_code = code
    max_apply = max(1, complexity - 1)  # complexity controls how many rules to stack

    for rule_id in candidates:
        if len(applied_rules) >= max_apply:
            break
        if rule_id not in TRANSFORM_REGISTRY:
            continue
        try:
            new_code = apply_transform(result_code, rule_id, target_token)
            if new_code != result_code:
                result_code = new_code
                applied_rules.append(TRANSFORM_REGISTRY[rule_id].name)
        except Exception as e:
            logger.debug(f"P4 rule {rule_id} failed: {e}")

    return PrimitiveResult(
        code=result_code,
        changed=result_code != code,
        primitive_id='P4',
        applied_rules=applied_rules,
        params_used={'phantom_type': phantom_type, 'complexity': complexity},
        description=f"Ghost-Inject(type={phantom_type}, complexity={complexity})",
    )


# ============================================================================
# P5: Name-Corrupt - Identifier Corruption
# Source: T34
# ============================================================================

def apply_name_corrupt(
    code: str,
    corruption_strategy: str = 'adversarial',
    target_identifier: Optional[str] = None,
    target_token: Optional[int] = None,
) -> PrimitiveResult:
    """
    P5: Identifier Corruption.
    Renames identifiers to break semantic hints or introduce semantic conflicts.

    Args:
        corruption_strategy: 'adversarial' | 'generic' | 'fsm_specific' | 'auto'
        target_identifier: specific identifier to corrupt (neural param - model selects).
        target_token: optional token position hint.
    """
    from transformations import apply_transform, TRANSFORM_REGISTRY

    # T16 已删除并与 T34 合并：统一只使用 T34。
    strategy_rules: Dict[str, List[str]] = {
        'adversarial':  ['T34'],
        'generic':      ['T34'],
        'fsm_specific': ['T34'],
        'auto':         ['T34'],
    }

    candidates = strategy_rules.get(corruption_strategy, strategy_rules['auto'])
    applied_rules: List[str] = []
    result_code = code

    for rule_id in candidates:
        if rule_id not in TRANSFORM_REGISTRY:
            continue
        try:
            new_code = apply_transform(result_code, rule_id, target_token)
            if new_code != result_code:
                result_code = new_code
                applied_rules.append(TRANSFORM_REGISTRY[rule_id].name)
                if corruption_strategy != 'auto':
                    break
        except Exception as e:
            logger.debug(f"P5 rule {rule_id} failed: {e}")

    return PrimitiveResult(
        code=result_code,
        changed=result_code != code,
        primitive_id='P5',
        applied_rules=applied_rules,
        params_used={'corruption_strategy': corruption_strategy, 'target_identifier': target_identifier},
        description=f"Name-Corrupt(strategy={corruption_strategy})",
    )


# ============================================================================
# P6: Doc-Camouflage - Documentation & Visual Camouflage
# Source: T20, T32
# ============================================================================

def apply_doc_camouflage(
    code: str,
    comment_text: Optional[str] = None,
    style_change: str = 'comment',
    target_token: Optional[int] = None,
) -> PrimitiveResult:
    """
    P6: Documentation & Visual Camouflage.
    Injects misleading comments, changes formatting, or alters declaration styles
    to create cognitive distraction.

    Args:
        comment_text: custom comment text to inject (neural param - model generates).
                      If provided, injected directly before applying comment rules.
        style_change: 'comment' | 'spacing' | 'declaration' | 'bitwidth' | 'all'
        target_token: optional token position hint.
    """
    from transformations import apply_transform, TRANSFORM_REGISTRY
    import re

    style_rules: Dict[str, List[str]] = {
        'comment':     ['T20'],
        'spacing':     [],   # T05 已移除
        'declaration': [],   # T36 已移除
        'bitwidth':    ['T32'],
        'all':         ['T20', 'T32'],
    }

    candidates = style_rules.get(style_change, style_rules['comment'])
    applied_rules: List[str] = []
    result_code = code

    # Inject custom comment_text if provided (neural param path)
    if comment_text is not None and style_change in ('comment', 'all'):
        match = re.search(r'(module\s+\w+[^;]*;)', result_code)
        if match:
            pos = match.end()
            result_code = result_code[:pos] + f'\n// {comment_text}' + result_code[pos:]
        else:
            result_code = f'// {comment_text}\n' + result_code
        if result_code != code:
            applied_rules.append('custom_comment')
        # Skip T20 since we already injected a comment
        candidates = [r for r in candidates if r != 'T20']

    for rule_id in candidates:
        if rule_id not in TRANSFORM_REGISTRY:
            continue
        try:
            new_code = apply_transform(result_code, rule_id, target_token)
            if new_code != result_code:
                result_code = new_code
                applied_rules.append(TRANSFORM_REGISTRY[rule_id].name)
                if style_change not in ('all',):
                    break
        except Exception as e:
            logger.debug(f"P6 rule {rule_id} failed: {e}")

    return PrimitiveResult(
        code=result_code,
        changed=result_code != code,
        primitive_id='P6',
        applied_rules=applied_rules,
        params_used={'comment_text': comment_text, 'style_change': style_change},
        description=f"Doc-Camouflage(style={style_change})",
    )


# ============================================================================
# Primitive Registry
# ============================================================================

PRIMITIVE_REGISTRY: Dict[str, AttackPrimitive] = {
    'P1': AttackPrimitive(
        id='P1',
        name='Expr-Morph',
        full_name='Expression Rewrite',
        description=(
            'Transforms boolean/arithmetic expressions into logically equivalent '
            'but structurally complex forms via DeMorgan, ternary expansion, '
            'constant identity, and nested negation.'
        ),
        constituent_rules=['T09', 'T10', 'T22', 'T30'],
        apply_func=apply_expr_morph,
        category='expression',
        attack_dimension='Concurrent Semantics + Logic Abstraction',
        default_params={'complexity_level': 3, 'transformation_type': 'auto'},
    ),
    'P2': AttackPrimitive(
        id='P2',
        name='Topo-Shatter',
        full_name='Topology Fragmentation',
        description=(
            'Breaks direct signal paths by inserting intermediate wire nodes '
            '(signal relay, dataflow decomposition, Shannon expansion) or '
            'reordering assignment statements.'
        ),
        constituent_rules=['T07', 'T12', 'T31', 'T35', 'T47', 'T48'],
        apply_func=apply_topo_shatter,
        category='topology',
        attack_dimension='Structural Topology',
        default_params={'fragmentation_depth': 3, 'reorder_pattern': 'none'},
    ),
    'P3': AttackPrimitive(
        id='P3',
        name='Seq-Morph',
        full_name='Temporal Restructure',
        description=(
            'Reorganizes sequential logic blocks and FSMs while preserving '
            'state transition equivalence: reset conversion and case reordering.'
        ),
        constituent_rules=['T40', 'T41'],
        apply_func=apply_seq_morph,
        category='temporal',
        attack_dimension='Temporal Abstraction',
        default_params={'restructure_type': 'auto'},
    ),
    'P4': AttackPrimitive(
        id='P4',
        name='Ghost-Inject',
        full_name='Phantom Injection',
        description=(
            'Injects dead code that appears functional but has no semantic effect: '
            'pseudo combinational loops, false pattern blocks, and redundant logic.'
        ),
        constituent_rules=['T03', 'T19', 'T45'],
        apply_func=apply_ghost_inject,
        category='phantom',
        attack_dimension='Cognitive Overload',
        default_params={'phantom_type': 'deadcode', 'complexity': 2},
    ),
    'P5': AttackPrimitive(
        id='P5',
        name='Name-Corrupt',
        full_name='Identifier Corruption',
        description=(
            'Corrupts identifier names to break semantic hints or create conflicts: '
            'adversarial renaming (semantic inversion), FSM state variable poisoning, '
            'and generic suffix renaming.'
        ),
        constituent_rules=['T34'],
        apply_func=apply_name_corrupt,
        category='identifier',
        attack_dimension='Visual + Semantic',
        default_params={'corruption_strategy': 'adversarial', 'target_identifier': None},
    ),
    'P6': AttackPrimitive(
        id='P6',
        name='Doc-Camouflage',
        full_name='Documentation & Visual Camouflage',
        description=(
            'Creates cognitive distraction via misleading protocol comments, '
            'decoy annotations, whitespace changes, port declaration style shifts, '
            'and bitwidth arithmetic expressions.'
        ),
        constituent_rules=['T20', 'T32'],
        apply_func=apply_doc_camouflage,
        category='documentation',
        attack_dimension='Cognitive + Documentation',
        default_params={'comment_text': None, 'style_change': 'comment'},
    ),
}


# ============================================================================
# Public API
# ============================================================================

def apply_primitive(
    code: str,
    primitive_id: str,
    **params: Any,
) -> PrimitiveResult:
    """Apply a single attack primitive to Verilog code.

    Args:
        code: Input Verilog code string.
        primitive_id: One of 'P1'-'P6'.
        **params: Primitive-specific parameters (override defaults).

    Returns:
        PrimitiveResult with transformed code and metadata.

    Raises:
        ValueError: If primitive_id is not recognized.
    """
    if primitive_id not in PRIMITIVE_REGISTRY:
        raise ValueError(
            f"Unknown primitive: {primitive_id}. "
            f"Available: {list(PRIMITIVE_REGISTRY.keys())}"
        )
    primitive = PRIMITIVE_REGISTRY[primitive_id]
    merged = {**primitive.default_params, **params}
    try:
        return primitive.apply_func(code, **merged)
    except Exception as e:
        logger.warning(f"Primitive {primitive_id} raised: {e}")
        return PrimitiveResult(
            code=code, changed=False, primitive_id=primitive_id,
            applied_rules=[], params_used=merged, description=f"{primitive_id} failed",
        )


def apply_primitives_combo(
    code: str,
    primitive_ids: List[str],
    params_per_primitive: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[str, List[PrimitiveResult]]:
    """Apply multiple primitives sequentially.

    Args:
        code: Input Verilog code.
        primitive_ids: Ordered list of primitive IDs to apply.
        params_per_primitive: Optional dict mapping primitive_id -> param overrides.

    Returns:
        (final_code, list_of_results)
    """
    params_per_primitive = params_per_primitive or {}
    results: List[PrimitiveResult] = []
    current = code
    for pid in primitive_ids:
        result = apply_primitive(current, pid, **params_per_primitive.get(pid, {}))
        results.append(result)
        current = result.code
    return current, results


def apply_combo_preset(code: str, preset_name: str) -> Tuple[str, List[PrimitiveResult]]:
    """Apply a named combo preset.

    Args:
        code: Input Verilog code.
        preset_name: Key from PRIMITIVE_COMBO_PRESETS.

    Returns:
        (final_code, list_of_results)
    """
    if preset_name not in PRIMITIVE_COMBO_PRESETS:
        raise ValueError(
            f"Unknown preset: {preset_name}. "
            f"Available: {list(PRIMITIVE_COMBO_PRESETS.keys())}"
        )
    preset = PRIMITIVE_COMBO_PRESETS[preset_name]
    return apply_primitives_combo(
        code,
        preset['primitives'],
        params_per_primitive=preset.get('params', {}),
    )


def get_primitive(primitive_id: str) -> AttackPrimitive:
    """Get a primitive by ID."""
    if primitive_id not in PRIMITIVE_REGISTRY:
        raise ValueError(f"Unknown primitive: {primitive_id}")
    return PRIMITIVE_REGISTRY[primitive_id]


def get_all_primitives() -> List[AttackPrimitive]:
    """Return all 6 registered primitives."""
    return list(PRIMITIVE_REGISTRY.values())


def get_primitives_by_category(category: str) -> List[AttackPrimitive]:
    """Return primitives matching a category."""
    return [p for p in PRIMITIVE_REGISTRY.values() if p.category == category]


def get_primitive_for_rule(rule_id: str) -> Optional[AttackPrimitive]:
    """Reverse-lookup: find which primitive a T-rule belongs to."""
    for primitive in PRIMITIVE_REGISTRY.values():
        if rule_id in primitive.constituent_rules:
            return primitive
    return None


# ============================================================================
# Combo Attack Presets
# ============================================================================

PRIMITIVE_COMBO_PRESETS: Dict[str, Dict[str, Any]] = {
    # High-coverage, always applicable (100% applicability)
    'doc_rename': {
        'primitives': ['P6', 'P5'],
        'params': {
            'P6': {'style_change': 'comment'},
            'P5': {'corruption_strategy': 'adversarial'},
        },
        'description': 'Misleading comment + adversarial renaming (visual+semantic dual attack)',
    },
    # Maximum cognitive overload
    'full_camouflage': {
        'primitives': ['P6', 'P5', 'P4'],
        'params': {
            'P6': {'style_change': 'all'},
            'P5': {'corruption_strategy': 'auto'},
            'P4': {'phantom_type': 'auto', 'complexity': 3},
        },
        'description': 'Full camouflage: comments + renaming + phantom injection',
    },
    # Logic-focused structural attack
    'logic_overload': {
        'primitives': ['P1', 'P2'],
        'params': {
            'P1': {'complexity_level': 4, 'transformation_type': 'demorgan'},
            'P2': {'fragmentation_depth': 5, 'reorder_pattern': 'reverse'},
        },
        'description': 'Logic expression rewrite + topology fragmentation',
    },
    # FSM-targeted attack
    'fsm_chaos': {
        'primitives': ['P3', 'P5'],
        'params': {
            'P3': {'restructure_type': 'encode'},
            'P5': {'corruption_strategy': 'fsm_specific'},
        },
        'description': 'FSM state encoding substitution + FSM variable poisoning',
    },
    # Maximum strength, all high-coverage primitives
    'max_attack': {
        'primitives': ['P6', 'P5', 'P4', 'P1'],
        'params': {
            'P6': {'style_change': 'comment'},
            'P5': {'corruption_strategy': 'adversarial'},
            'P4': {'phantom_type': 'loop', 'complexity': 4},
            'P1': {'complexity_level': 5, 'transformation_type': 'auto'},
        },
        'description': 'Maximum attack: all high-coverage primitives at max strength',
    },
    # Minimal but empirically effective (based on T20+T34 experiment results)
    'minimal_effective': {
        'primitives': ['P6', 'P5'],
        'params': {
            'P6': {'style_change': 'comment'},
            'P5': {'corruption_strategy': 'generic'},
        },
        'description': 'Minimal effective: misleading comment + generic rename (100% applicability)',
    },
}
