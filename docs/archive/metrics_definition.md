# 指标定义（Coverage / Accuracy / Attack Strength）

本文档对应你当前的评估实现：`scripts/eval/rule_applicator.py` + `scripts/eval/evaluate_rules.py` + `evaluate.py`。

## 1) 术语

- `task`：数据集中的一个样本（`task_id` 唯一）。
- `rule_id`：要评估的单条 T-rule（例如 `T03`）。
- `candidate`：在某个 task 上 engine 给出的可尝试变换位置索引 `k`（即 `target_token=k`）。
- `transform_success(candidate)`：单条变换能生成新代码，且 `analyze(new_code)` 可正常解析（当前以语法/parse 成功作为“成功”，不等价于语义等价）。
- `rtl_orig`：任务数据集里的 `canonical_solution`（原始 RTL）。
- `rtl_adv`：对某个 task 应用规则得到的对抗 RTL（当前 evaluate_rules.py 只取第一个成功 `k` 生成一份 `rtl_adv`）。
- `truth(rtl)`：通过仿真 `simulate_verilog(rtl, testbench)` 得到该 RTL 在测试用例下是否“功能通过”（True/False）。
- `model_pred(rtl)`：模型给出的验证结论（YES/NO）解析为布尔值；并与 `truth(rtl)` 比较得到是否“模型判断正确”。

## 2) 可应用能力（Applicability）

对每条规则 `rule_id`，在全体样本上统计：

- `num_samples`：数据集中该规则评估所覆盖的样本数（evaluate_rules.py 遍历的样本数；可受 `--sample-limit` 影响）。
- `num_applicable_samples`：在这些样本中，至少存在一个 `candidate` 使得 `transform_success(candidate)=True`。
- `coverage = num_applicable_samples / num_samples`

同时也统计候选侧：

- `total_candidates`：所有样本的 `candidate` 总数之和（即所有样本 `num_candidates` 求和）。
- `total_success =` 所有样本 `num_success` 求和（即所有样本的成功候选个数求和）。
- `success_rate = total_success / total_candidates`

## 3) 模型准确率（验证模型的判定能力）

对每条规则 `rule_id`：

- `acc_orig`：模型在 `rtl_orig` 上的验证准确率。
  - 在实现中对应：`evaluate.py` 对 `mode="original"` 的 `original_rate`。
- `acc_adv`：模型在 `rtl_adv` 上的验证准确率。
  - 在实现中对应：`evaluate.py` 对 `mode="adversarial"` 的 `adversarial_rate`。

两者都只在“可写出对抗代码的 task 子集”上评估（因为 `evaluate.py` 只遍历 `--results` 目录中存在的 `task_id`）。

## 4) 攻击强度（Attack Strength）

- `gain = acc_orig - acc_adv`
- `strength = coverage * gain`

其中 `gain` 衡量“对抗扰动导致模型验证准确率下降”的幅度；
`coverage` 衡量“这类扰动在数据集上能覆盖多少样本”。

> 注：当前实现中 `evaluate_rules.py` 里 `asr` 字段为 `null`，原因是它没有在同一次 `evaluate.py` 运行中同时输出 `original_passed` 与 `adversarial_passed` 的 per-task 联动统计（见 `scripts/eval/evaluate_rules.py` 的调用方式）。如需严格 ASR，可把 evaluate.py 调用改成对同一份 results 同时跑 `modes=["original","adversarial"]`，并从 `original_passed && !adversarial_passed` 直接统计。

