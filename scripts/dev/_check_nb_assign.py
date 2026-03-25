"""分析 always 块内 nonblocking assign 的分布"""
import json, sys, re
sys.path.insert(0, '.')
import ast_transforms_loader
m = sys.modules['ast_transforms_2']
analyze = m.analyze

with open('data/qualified_dataset.json') as f:
    dataset = json.load(f)

has_nb_swappable = 0   # 有 >=2 条可交换的 <= 在同一 always 块
total_with_always = 0

samples = []

for task in dataset:
    code = task.get('canonical_solution', '')
    if not code:
        continue
    vs = analyze(code)
    if not vs.always_blocks:
        continue
    total_with_always += 1

    for blk in vs.always_blocks:
        blk_text = blk.text
        # 提取块内所有 nonblocking assign: lhs <= rhs;
        nb_assigns = re.findall(
            r'(\w[\w\[\]:]*)\s*<=\s*([^;]+);',
            blk_text
        )
        if len(nb_assigns) < 2:
            continue
        # 检查是否有独立对（RHS 不引用对方 LHS）
        found = False
        for i in range(len(nb_assigns)):
            for j in range(i+1, len(nb_assigns)):
                lhs_i, rhs_i = nb_assigns[i][0].strip(), nb_assigns[i][1].strip()
                lhs_j, rhs_j = nb_assigns[j][0].strip(), nb_assigns[j][1].strip()
                # nonblocking 语义上无依赖，但排除 lhs 相同（同一信号多次赋值）
                if lhs_i == lhs_j:
                    continue
                # 排除文本完全相同
                if f'{lhs_i} <= {rhs_i}' == f'{lhs_j} <= {rhs_j}':
                    continue
                found = True
                break
            if found:
                break
        if found:
            has_nb_swappable += 1
            if len(samples) < 3:
                samples.append({
                    'task_id': task.get('task_id'),
                    'nb_assigns': nb_assigns[:6],
                    'blk': blk_text[:300],
                })
            break  # 一个模块算一次

print(f"有 always 块的样本:          {total_with_always}")
print(f"有可交换 <= 对的样本:        {has_nb_swappable}")
print(f"占总数据集比例:              {has_nb_swappable/17581*100:.1f}%")
print()
for s in samples:
    print(f"=== {s['task_id']} ===")
    for lhs, rhs in s['nb_assigns']:
        print(f"  {lhs} <= {rhs.strip()}")
    print()
