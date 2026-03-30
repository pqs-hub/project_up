#!/usr/bin/env python3
"""
evaluate.py — 用 LLM 判题器评估 Verilog RTL（original 或 adversarial 模式）。

被 scripts/eval/evaluate_rules.py 以子进程方式调用，接口：
  --dataset     verilog_eval.json 路径（含 task_id / prompt / canonical_solution / test）
  --provider    local / openai / anthropic（当前只实现 local/openai-compatible）
  --model       模型名称（与 vLLM 提供的名称一致）
  --base-url    vLLM base_url，例如 http://localhost:8001/v1
  --api-key     API key（本地填 EMPTY）
  --temperature 采样温度（0.0 = greedy）
  --max-tokens  最大生成 token 数
  --repeat      对每个 task 重复判题次数
  --results     每个 task 的对抗/原始 RTL 所在目录（{task_id}.json，含 'final' 字段）
  --output      per-task 输出目录，写 {task_id}_rep{n}.json
  --modes       original adversarial（可多值）
  --progress    显示 tqdm 进度条

output per-task JSON 字段（original 模式）：
  task_id, mode, rep, original_truth, original_passed, original_confidence

output per-task JSON 字段（adversarial 模式）：
  task_id, mode, rep, adversarial_passed, adversarial_confidence
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient


def _load_dataset(path: Path) -> dict:
    """返回 task_id -> task dict。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {t["task_id"]: t for t in raw}
    return raw


def _load_rtl(results_dir: Path, task_id: str) -> str | None:
    """从 results_dir/{task_id}.json 读取 'final' 字段。"""
    f = results_dir / f"{task_id}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("final")
    except Exception:
        return None


def _judge_one(client: TargetModelClient, spec: str, rtl: str) -> dict:
    """调用 judge，返回 {passed, confidence}。"""
    verdict = client.judge(spec, rtl, use_cot=False)
    if verdict is None:
        return {"passed": None, "confidence": None}
    return {
        "passed": bool(verdict.get("is_correct")),
        "confidence": verdict.get("confidence"),
    }


def run_original(client, dataset, results_dir, output_dir, repeat, progress):
    """original 模式：用 canonical_solution 判题（或从 results_dir 读取 final）。"""
    tasks = list(dataset.items())
    if progress:
        try:
            from tqdm import tqdm
            tasks = tqdm(tasks, desc="original")
        except ImportError:
            pass

    def _do(task_id, task):
        # 优先用 results_dir 中的 final（保持与 adv 模式一致的 RTL 来源）
        rtl = _load_rtl(results_dir, task_id) if results_dir else None
        if rtl is None:
            rtl = task.get("canonical_solution", "")
        spec = task.get("prompt", "")
        # ground truth：canonical_solution 本身应该是正确的
        original_truth = True
        results = []
        for rep in range(repeat):
            v = _judge_one(client, spec, rtl)
            rec = {
                "task_id": task_id,
                "mode": "original",
                "rep": rep,
                "original_truth": original_truth,
                "original_passed": v["passed"],
                "original_confidence": v["confidence"],
            }
            out_file = output_dir / f"{task_id}_rep{rep}.json"
            out_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append(rec)
        return results

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_do, tid, t): tid for tid, t in (dataset.items() if not progress else dataset)}
        # tasks 上面可能是 tqdm 包装的，这里直接 iterate dataset
        if progress:
            futs = {ex.submit(_do, tid, t): tid for tid, t in dataset.items()}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                print(f"[warn] task {futs[fut]}: {e}", file=sys.stderr)


def run_adversarial(client, dataset, results_dir, output_dir, repeat, progress):
    """adversarial 模式：从 results_dir 读取对抗 RTL 并判题。"""
    if results_dir is None:
        print("[error] adversarial 模式需要 --results 目录", file=sys.stderr)
        sys.exit(1)

    adv_files = list(results_dir.glob("*.json"))
    if progress:
        try:
            from tqdm import tqdm
            adv_files = tqdm(adv_files, desc="adversarial")
        except ImportError:
            pass

    def _do(f):
        try:
            rec_in = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return
        task_id = rec_in.get("task_id", f.stem)
        rtl = rec_in.get("final")
        if not rtl:
            return
        task = dataset.get(task_id)
        if task is None:
            return
        spec = task.get("prompt", "")
        for rep in range(repeat):
            v = _judge_one(client, spec, rtl)
            rec_out = {
                "task_id": task_id,
                "mode": "adversarial",
                "rep": rep,
                "adversarial_passed": v["passed"],
                "adversarial_confidence": v["confidence"],
            }
            out_file = output_dir / f"{task_id}_rep{rep}.json"
            out_file.write_text(json.dumps(rec_out, ensure_ascii=False, indent=2), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_do, f) for f in (adv_files if not progress else list(results_dir.glob("*.json")))]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                print(f"[warn] {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="LLM 判题器：评估 original/adversarial RTL")
    parser.add_argument("--dataset", required=True, help="verilog_eval.json 路径")
    parser.add_argument("--provider", default="local", help="local / openai / anthropic")
    parser.add_argument("--model", required=True, help="模型名称")
    parser.add_argument("--base-url", default="http://localhost:8001/v1", help="vLLM base URL")
    parser.add_argument("--api-key", default="EMPTY", help="API key")
    parser.add_argument("--temperature", type=float, default=0.0, help="采样温度")
    parser.add_argument("--max-tokens", type=int, default=2048, help="最大 token 数")
    parser.add_argument("--repeat", type=int, default=1, help="每个 task 重复判题次数")
    parser.add_argument("--results", default=None, help="per-task RTL 结果目录")
    parser.add_argument("--output", required=True, help="per-task 输出目录")
    parser.add_argument("--modes", nargs="+", default=["original"], choices=["original", "adversarial"],
                        help="评估模式")
    parser.add_argument("--progress", action="store_true", help="显示 tqdm 进度条")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    results_dir = Path(args.results) if args.results else None
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = _load_dataset(dataset_path)

    client = TargetModelClient(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        max_new_tokens=args.max_tokens,
    )

    for mode in args.modes:
        if mode == "original":
            run_original(client, dataset, results_dir, output_dir, args.repeat, args.progress)
        elif mode == "adversarial":
            run_adversarial(client, dataset, results_dir, output_dir, args.repeat, args.progress)


if __name__ == "__main__":
    main()
