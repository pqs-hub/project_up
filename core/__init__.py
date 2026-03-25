"""
Core modules for Verilog obfuscation attack framework.
"""
from .transform_loader import create_engine
from .target_model import TargetModelClient

# AdversarialDatasetGenerator has complex dependencies, import when needed
# from .param_generator import AdversarialDatasetGenerator

__all__ = [
    'create_engine',
    'TargetModelClient',
]
