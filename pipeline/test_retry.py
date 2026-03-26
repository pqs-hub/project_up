#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试重试机制
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
from pipeline.filter_cot_correct_parallel import filter_cot_correct_samples_parallel

# 测试重试机制
print("🧪 测试重试机制（5个样本）")
print()

filter_cot_correct_samples_parallel(
    input_file="data/qualified_dataset.json",
    output_file="data/test_retry.json",
    judge_base_url="http://localhost:8001/v1",
    judge_model="qwen25_coder",
    max_samples=5,
    num_workers=2  # 减少并发避免排队
)
