# 代码库清理总结

## 清理日期
2026-03-28

## 清理目标
删除与主框架无关的冗余代码，保持项目简洁

## 已删除内容

### 1. 与主框架无关的目录

#### `AI_talk/` 目录
- **内容**: 仅包含讨论文档 `Bio-Inspired Chinese Jailbreak.md`
- **原因**: 与核心功能无关的讨论材料
- **状态**: ✅ 已删除

#### `baseline/` 目录（24个文件）
- **内容**: 基线实验代码
  - AutoBench/
  - Branch_Exchanging/
  - If-condition_Rewriting/
  - Illusory_Complexity_Bias/
  - Misleading_Task_Bias/
  - Reverse_Authority_Bias/
  - Self-Declared_Incorrectness_Bias/
  - Variable_Change_Bias/
  - iverilog_rtl_judge.py
- **原因**: 基线对比实验代码，与主攻击框架无关
- **状态**: ✅ 已删除

#### `docs/archive/` 目录（34个文件）
- **内容**: 归档的旧文档，包括多个空文件
  - ACCURATE_METRICS_REPORT.md
  - ALL_RULES_FINAL_REPORT.md (空)
  - FINAL_REPORT.md (空)
  - FIXES_APPLIED.md (空)
  - 等共34个markdown文件
- **原因**: 过期文档和空文件
- **状态**: ✅ 已删除

### 2. 空目录和缓存

#### Python缓存
- `__pycache__/` 目录（根目录）
- 所有子目录下的 `__pycache__/` 
- 所有 `.pyc` 文件
- **状态**: ✅ 已删除

#### 空目录
- `logs/` - 日志目录（空）
- `results/` - 结果目录（空）
- `saves/` - 保存目录（空）
- **状态**: ✅ 已删除

### 3. 独立脚本和临时文件

#### 根目录下的脚本
- `generate_dataset.py` - 数据集生成（功能已在pipeline/中）
- `setup_reverse_tunnel.sh` - 临时隧道脚本
- **状态**: ✅ 已删除

#### test/目录下的调试文件
- `debug_beam_search.py`
- `debug_single_attack.py`
- `debug_testbench.py`
- `manual_testbench_tb.v`
- `manual_testbench_test.v`
- `run_t19_fixed.sh`
- `run_t19_test.sh`
- `redundancy_analysis.json` (1.17MB)
- **状态**: ✅ 已删除

### 4. 文档整理

#### 移动到doc/目录
- `BEAM_SEARCH_使用说明.md` → `doc/BEAM_SEARCH_使用说明.md`
- `CLAUDE.md` → `doc/CLAUDE.md`
- `EVAL_GUIDE.md` → `doc/EVAL_GUIDE.md`
- **状态**: ✅ 已移动

## 保留的结构

### 核心目录
- ✅ `core/` - 核心功能模块
- ✅ `config/` - 配置模块
- ✅ `pipeline/` - 数据处理流程
- ✅ `scripts/` - 辅助脚本
- ✅ `utils/` - 工具模块
- ✅ `doc/` - 文档（整理后）
- ✅ `docs/` - 文档（保留必要文件）

### 数据和模型
- ✅ `data/` - 数据文件
- ✅ `eval_data/` - 评估数据
- ✅ `models/` - 模型文件
- ✅ `configs/` - 配置文件

### 测试
- ✅ `test/` - 测试代码（删除调试文件后保留）

### 根目录文件
- ✅ `main.py` - 统一入口
- ✅ `config.yaml` - 主配置
- ✅ `README.md` - 项目说明
- ✅ `requirements.txt` - 依赖
- ✅ `environment.yml` - Conda环境
- ✅ `Testbench_valid.py` - Testbench验证
- ✅ `ast_transforms_loader.py` - 转发导入（被多处使用）

## 清理统计

- **删除目录**: 8个（AI_talk/, baseline/, docs/archive/, __pycache__/, logs/, results/, saves/, 及test/下的部分文件）
- **删除文件**: 约100+个
- **移动文件**: 3个文档
- **项目更简洁**: 是

## 影响评估

### 无影响
所有删除的内容都是：
1. 与主框架无关的实验代码
2. 过期或归档的文档
3. 临时调试文件
4. 空目录和缓存

### 主框架功能
- ✅ 核心混淆引擎：无影响
- ✅ 攻击数据生成：无影响
- ✅ 模型训练评估：无影响
- ✅ Pipeline流程：无影响

## 建议

### 进一步整理
如果需要进一步简化，可以考虑：
1. 合并 `doc/` 和 `docs/` 两个文档目录
2. 检查 `test/` 目录中的测试文件是否都必要
3. 清理 `data/` 目录中的临时数据（如有）

### 维护建议
1. 定期清理 `__pycache__/` 和 `.pyc` 文件
2. 归档旧的实验数据和结果
3. 将临时脚本放在 `test/` 目录而非根目录
