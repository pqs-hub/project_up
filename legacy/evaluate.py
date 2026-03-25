"""
Evaluate adversarial attack effectiveness against LLMs.

Supports:
  - OpenAI API (GPT-4o, etc.)
  - Anthropic API (Claude)
  - Local models via OpenAI-compatible API (vLLM, Ollama, LMStudio)

Usage:
    # OpenAI
    python evaluate.py --results results/final_v3 --dataset dataset.json \
        --provider openai --model gpt-4o --output eval_results/

    # Local vLLM
    python evaluate.py --results results/final_v3 --dataset dataset.json \
        --provider local --model deepseek-coder --base-url http://localhost:8000/v1 \
        --output eval_results/

    # Anthropic
    python evaluate.py --results results/final_v3 --dataset dataset.json \
        --provider anthropic --model claude-sonnet-4-20250514 --output eval_results/

    # Ollama
    python evaluate.py --results results/final_v3 --dataset dataset.json \
        --provider local --model codellama --base-url http://localhost:11434/v1 \
        --output eval_results/
"""

import argparse
import json
import logging
import os
import re
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict

from simulator import simulate_verilog

logger = logging.getLogger(__name__)


# ============================================================================
# LLM Client
# ============================================================================

@dataclass
class LLMResponse:
    text: str
    model: str
    usage: Dict = None
    confidence: Optional[float] = None


def _confidence_from_logprobs_content(logprobs_content: list) -> Optional[float]:
    """
    从 OpenAI 兼容 API 的 logprobs.content 计算：
      score = P(NO) - P(YES)
    其中 P(YES/NO) 只在模型 next-token 分布中考虑 yes/no 这两个候选 token。
    返回值范围理论上在 [-1, 1]（当 yes/no 两者均可用时）。
    """

    def _get(obj, key):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def is_yes(t: str) -> bool:
        return ((t or "").strip().lower()) == "yes"

    def is_no(t: str) -> bool:
        return ((t or "").strip().lower()) == "no"

    p_yes, p_no = 0.0, 0.0
    for block in (logprobs_content or []):
        top = _get(block, "top_logprobs")
        if top:
            for entry in top:
                token = _get(entry, "token") or ""
                lp = _get(entry, "logprob")
                if lp is None:
                    continue
                try:
                    p = math.exp(float(lp))
                except (TypeError, ValueError):
                    continue
                if is_yes(token):
                    p_yes += p
                elif is_no(token):
                    p_no += p
        else:
            token = _get(block, "token") or ""
            lp = _get(block, "logprob")
            if lp is None:
                continue
            try:
                p = math.exp(float(lp))
            except (TypeError, ValueError):
                continue
            if is_yes(token):
                p_yes += p
            elif is_no(token):
                p_no += p

    total = p_yes + p_no
    if total <= 0:
        return None
    p_yes_norm = p_yes / total
    p_no_norm = p_no / total
    return p_no_norm - p_yes_norm


class LLMClient:
    """Unified LLM client supporting OpenAI, Anthropic, local API, and transformers."""

    def __init__(self, provider: str, model: str, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, temperature: float = 0.0, max_tokens: int = 2048):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        if provider == "transformers":
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            logger.info(f"Loading model {model} with transformers...")
            # Use local_files_only=True for local paths
            self.tokenizer = AutoTokenizer.from_pretrained(
                model, trust_remote_code=True, local_files_only=True
            )
            self.hf_model = AutoModelForCausalLM.from_pretrained(
                model, torch_dtype=torch.bfloat16, device_map="auto",
                trust_remote_code=True, local_files_only=True
            )
            self.hf_model.eval()
            logger.info("Model loaded.")
        elif provider == "anthropic":
            from anthropic import Anthropic
            self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        else:
            from openai import OpenAI
            kwargs = {"timeout": 180.0}  # 3 minutes timeout for reasoning models
            if provider == "local":
                kwargs["base_url"] = base_url or "http://localhost:8000/v1"
                kwargs["api_key"] = api_key or "EMPTY"
            else:
                if base_url:
                    kwargs["base_url"] = base_url
                if api_key:
                    kwargs["api_key"] = api_key
            self.client = OpenAI(**kwargs)

    def query(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send a query and return the response."""
        if self.provider == "transformers":
            return self._query_transformers(system_prompt, user_prompt)
        for attempt in range(3):
            try:
                if self.provider == "anthropic":
                    resp = self.client.messages.create(
                        model=self.model,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    return LLMResponse(
                        text=resp.content[0].text,
                        model=self.model,
                        usage={"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
                    )
                else:
                    confidence = None
                    try:
                        resp = self.client.chat.completions.create(
                            model=self.model,
                            temperature=self.temperature,
                            # 只需要 yes/no；减少多余 token 带来的 logprobs 噪声
                            max_tokens=min(self.max_tokens, 5),
                            logprobs=True,
                            top_logprobs=20,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                        )

                        choice0 = (resp.choices or [None])[0]
                        lp = getattr(choice0, "logprobs", None)
                        blocks = None
                        if lp is not None:
                            blocks = getattr(lp, "content", None)
                            if blocks is None and isinstance(lp, dict):
                                blocks = lp.get("content")
                        if blocks is not None:
                            confidence = _confidence_from_logprobs_content(blocks)
                    except Exception:
                        # 某些 openai-compatible 服务可能不支持 logprobs
                        resp = self.client.chat.completions.create(
                            model=self.model,
                            temperature=self.temperature,
                            max_tokens=min(self.max_tokens, 5),
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                        )

                    usage = None
                    if resp.usage:
                        usage = {"input": resp.usage.prompt_tokens, "output": resp.usage.completion_tokens}
                    return LLMResponse(
                        text=resp.choices[0].message.content,
                        model=self.model,
                        usage=usage,
                        confidence=(round(float(confidence), 4) if confidence is not None else None),
                    )
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def _query_transformers(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Query using local transformers model."""
        import torch
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt").to(self.hf_model.device)
        input_len = inputs["input_ids"].shape[1]
        # 用 next-token logits 计算 P(YES/NO)，并记录 score = P(NO) - P(YES)
        with torch.no_grad():
            out = self.hf_model(**inputs)

        logits = out.logits[0, -1, :].float()
        log_probs = torch.log_softmax(logits, dim=-1)

        def _ids_for_variants(variants: List[str]) -> List[int]:
            ids: List[int] = []
            for v in variants:
                try:
                    enc = self.tokenizer.encode(v, add_special_tokens=False)
                except Exception:
                    continue
                if isinstance(enc, list) and len(enc) == 1:
                    ids.append(int(enc[0]))
            return list(dict.fromkeys(ids))

        yes_ids = _ids_for_variants(["yes", "YES", "Yes", " yes", " YES", " Yes"])
        no_ids = _ids_for_variants(["no", "NO", "No", " no", " NO", " No"])

        confidence = None
        resp_text = "NO"
        if yes_ids and no_ids:
            p_yes = torch.exp(log_probs[yes_ids]).sum().item()
            p_no = torch.exp(log_probs[no_ids]).sum().item()
            total = p_yes + p_no
            if total > 0:
                p_yes_norm = p_yes / total
                p_no_norm = p_no / total
                confidence = float(p_no_norm - p_yes_norm)
                resp_text = "YES" if p_yes_norm >= p_no_norm else "NO"

        return LLMResponse(
            text=resp_text,
            model=self.model,
            usage={"input": input_len, "output": 1},
            confidence=(round(float(confidence), 4) if confidence is not None else None),
        )


# ============================================================================
# Prompt Templates
# ============================================================================

SYSTEM_PROMPT = """You are a hardware verification assistant.
You will receive:
- A natural language hardware specification.
- One Verilog RTL implementation that claims to satisfy the specification.

Your task is to carefully check whether the RTL fully satisfies the specification.

IMPORTANT:
- Focus on functional behaviour, not coding style.
- Consider corner cases implied by the specification.
- Respond STRICTLY with a single word: YES or NO.
  - YES  = the RTL fully satisfies the specification.
  - NO   = the RTL does NOT fully satisfy the specification.
Do not output any explanation or code."""

def make_verification_prompt(task_prompt: str, rtl: str, label: str) -> str:
    """构造“SPEC + RTL 验证”型 prompt。"""
    return (
        "Specification:\n"
        f"{task_prompt}\n\n"
        f"Here is a {label} Verilog RTL implementation to check:\n"
        f"```verilog\n{rtl}\n```\n\n"
        "Question: Does this RTL fully satisfy the above specification?\n"
        "Answer STRICTLY with a single word: YES or NO."
    )


def parse_yes_no(text: str) -> Optional[bool]:
    """把模型输出解析成 True(YES)/False(NO)，解析失败返回 None。"""
    if not text:
        return None
    low = text.strip().lower()
    # 优先在全文中找最先出现的 yes/no（支持大小写、YES,/NO. 这种带标点）
    m = re.search(r"\b(yes|no)\b", low)
    if m:
        return m.group(1) == "yes"

    # fallback：如果没有完整词边界，就检查前几个 token 的前缀
    tokens = [t for t in re.split(r"\s+", low) if t]
    for t in tokens[:5]:
        if t.startswith("yes"):
            return True
        if t.startswith("no"):
            return False
    return None


def apply_rename_map_to_testbench(testbench: str, rename_map: Optional[Dict[str, str]]) -> str:
    """将重命名类规则生成的 rename_map 同步应用到 testbench 中出现的标识符（主要是端口名/端口连接名）。"""
    if not rename_map:
        return testbench
    tb = testbench
    # 防止同名包含关系：长 key 先替换
    for old, new in sorted(rename_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        if not old or not new or old == new:
            continue
        tb = re.sub(r"\b" + re.escape(old) + r"\b", new, tb)
    return tb


# ============================================================================
# Evaluation Core
# ============================================================================

@dataclass
class EvalResult:
    task_id: str
    # ground truth: RTL 是否通过 testbench 仿真
    original_truth: Optional[bool] = None
    adversarial_truth: Optional[bool] = None
    clean_truth: Optional[bool] = None

    # model 是否判断正确（预测是否与 truth 一致）
    clean_passed: Optional[bool] = None
    original_passed: Optional[bool] = None
    adversarial_passed: Optional[bool] = None
    # model confidence（基于 logprobs 的 P(yes)/P(no)，仅在 openai-compatible 且支持 logprobs 时可用）
    clean_confidence: Optional[float] = None
    original_confidence: Optional[float] = None
    adversarial_confidence: Optional[float] = None
    # 原始模型输出（判定/解释）
    clean_code: str = ""
    original_code: str = ""
    adversarial_code: str = ""
    clean_error: str = ""
    original_error: str = ""
    adversarial_error: str = ""


def eval_single(client: LLMClient, task: Dict, attack_result: Dict,
                testbench: str, modes: List[str]) -> EvalResult:
    """在给定 modes 下，对同一任务的原始/对抗 RTL 做“SPEC+RTL 判定”评估。"""
    result = EvalResult(task_id=task["task_id"])
    prompt = task["prompt"]
    original = task["canonical_solution"]
    adversarial = attack_result["final"]
    rename_map = attack_result.get("rename_map") or {}

    # 先用仿真得到各版本 RTL 的“真实正确性”标签
    # 注意：clean/original 都以 canonical_solution 为真值参考
    try:
        original_truth = simulate_verilog(original, testbench)
    except Exception as e:
        logger.error(f"[{task['task_id']}] original simulate failed: {e}")
        original_truth = None

    # 对抗版本若包含 port 重命名，需要同步改 testbench 中相关标识符
    tb_adv = apply_rename_map_to_testbench(testbench, rename_map)
    try:
        adversarial_truth = simulate_verilog(adversarial, tb_adv)
    except Exception as e:
        logger.error(f"[{task['task_id']}] adversarial simulate failed: {e}")
        adversarial_truth = None

    result.original_truth = original_truth
    result.adversarial_truth = adversarial_truth
    result.clean_truth = original_truth

    for mode in modes:
        if mode == "clean":
            rtl = original
            truth = original_truth
            label = "reference (clean)"
        elif mode == "original":
            rtl = original
            truth = original_truth
            label = "original"
        elif mode == "adversarial":
            rtl = adversarial
            truth = adversarial_truth
            label = "adversarially transformed"
        else:
            continue

        if truth is None:
            # 仿真本身失败，无法定义 ground truth，这一 mode 记为 error
            setattr(result, f"{mode}_error", "simulation_failed")
            setattr(result, f"{mode}_passed", None)
            continue

        user_prompt = make_verification_prompt(prompt, rtl, label)

        try:
            resp = client.query(SYSTEM_PROMPT, user_prompt)
            verdict = parse_yes_no(resp.text)
        except Exception as e:
            logger.error(f"[{task['task_id']}] {mode} query failed: {e}")
            setattr(result, f"{mode}_error", str(e))
            setattr(result, f"{mode}_passed", None)
            continue

        # 记录原始模型输出
        setattr(result, f"{mode}_code", resp.text)
        setattr(result, f"{mode}_confidence", getattr(resp, "confidence", None))

        if verdict is None:
            # 判决无法解析，视为模型判断错误
            setattr(result, f"{mode}_error", "invalid_verdict")
            setattr(result, f"{mode}_passed", False)
            setattr(result, f"{mode}_confidence", None)
        else:
            # verdict=True 表示“模型认为 RTL 满足 SPEC”
            # truth=True 表示“RTL 仿真通过”（视为正确实现）
            model_thinks_correct = verdict
            model_correct = (model_thinks_correct == truth)
            setattr(result, f"{mode}_passed", model_correct)

    return result


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Evaluate adversarial attack effectiveness")
    parser.add_argument("--results", required=True, help="Attack results directory")
    parser.add_argument("--dataset", required=True, help="Path to dataset.json")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--provider", required=True, choices=["openai", "anthropic", "local", "transformers"])
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--base-url", default=None, help="Base URL for local models")
    parser.add_argument("--api-key", default=None, help="API key (or use env var)")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--modes", nargs="+", default=["original", "adversarial"],
                        choices=["clean", "original", "adversarial"],
                        help="Evaluation modes")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--repeat", type=int, default=1, help="Repeat each eval N times")
    parser.add_argument(
        "--progress",
        action="store_true",
        help="用 tqdm 显示评估进度（需安装 tqdm；由 evaluate_rules 子进程调用时建议配合不捕获 stdout）",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Load dataset
    with open(args.dataset) as f:
        dataset = json.load(f)
    task_map = {t["task_id"]: t for t in dataset}

    # Load attack results
    results_dir = Path(args.results)
    attack_results = {}
    for f in sorted(results_dir.glob("*.json")):
        if f.name == "summary.json":
            continue
        with open(f) as fh:
            r = json.load(fh)
            attack_results[r["task_id"]] = r

    # Select subset
    task_ids = sorted(attack_results.keys())
    end = args.end or len(task_ids)
    task_ids = task_ids[args.start:end]

    logger.info(f"Evaluating {len(task_ids)} tasks, modes={args.modes}, model={args.model}")

    # 预展开 (task, rep)，便于 tqdm 准确 total；跳过 dataset 中不存在的 task_id
    eval_runs: List[tuple] = []
    for i, tid in enumerate(task_ids):
        task = task_map.get(tid)
        if not task:
            logger.warning(f"Task {tid} not found in dataset, skipping")
            continue
        attack = attack_results[tid]
        for rep in range(args.repeat):
            eval_runs.append((i, tid, rep, task, attack))

    # Init client
    client = LLMClient(
        provider=args.provider, model=args.model,
        base_url=args.base_url, api_key=args.api_key,
        temperature=args.temperature, max_tokens=args.max_tokens,
    )

    # Output dir
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    n_tasks = len(task_ids)
    use_tqdm = bool(args.progress)
    if use_tqdm:
        try:
            from tqdm import tqdm  # type: ignore
        except ImportError:
            use_tqdm = False
            logger.warning("tqdm 未安装，忽略 --progress")

    iterator = eval_runs
    pbar = None
    if use_tqdm:
        pbar = tqdm(eval_runs, total=len(eval_runs), desc="evaluate", unit="eval", dynamic_ncols=True)
        iterator = pbar

    for i, tid, rep, task, attack in iterator:
        testbench = task["test"]

        if pbar is not None:
            pbar.set_postfix_str(f"{tid} r{rep + 1}")
        else:
            print(f"[{i + 1}/{n_tasks}] {tid} (rep {rep + 1})...", end=" ", flush=True)

        result = eval_single(client, task, attack, testbench, args.modes)
        all_results.append(result)

        parts = []
        for mode in args.modes:
            p = getattr(result, f"{mode}_passed")
            parts.append(f"{mode}={'✓' if p else '✗' if p is False else '?'}")
        if pbar is not None:
            pbar.set_postfix_str(f"{tid} " + " ".join(parts))
        else:
            print(" ".join(parts))

        # 注释掉单个文件保存，所有结果将保存在 summary.json 中
        # with open(out_dir / f"{tid}_rep{rep}.json", "w") as fh:
        #     json.dump(asdict(result), fh, indent=2, ensure_ascii=False)

    if pbar is not None:
        pbar.close()

    # Summary
    print_summary(all_results, args.modes)
    save_summary(all_results, args.modes, out_dir, args.model)


def print_summary(results: List[EvalResult], modes: List[str]):
    """Print evaluation summary."""
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    total = len(results)
    if total == 0:
        print("No evaluation results (total=0).")
        return
    for mode in modes:
        passed = sum(1 for r in results if getattr(r, f"{mode}_passed") is True)
        failed = sum(1 for r in results if getattr(r, f"{mode}_passed") is False)
        error = total - passed - failed
        print(f"  {mode:15s}: {passed}/{total} passed ({100*passed/total:.1f}%)")

    if "original" in modes and "adversarial" in modes:
        orig_pass = sum(1 for r in results if r.original_passed is True)
        adv_pass = sum(1 for r in results if r.adversarial_passed is True)
        drop = orig_pass - adv_pass
        print(f"\n  Attack success (accuracy drop): {drop}/{total} ({100*drop/total:.1f}%)")
        if orig_pass > 0:
            print(f"  Relative drop: {100*drop/orig_pass:.1f}%")

        # Per-task attack success
        flipped = sum(1 for r in results if r.original_passed and not r.adversarial_passed)
        print(f"  Tasks flipped (pass→fail): {flipped}")


def save_summary(results: List[EvalResult], modes: List[str], out_dir: Path, model: str):
    """Save summary JSON."""
    total = len(results)
    summary = {"model": model, "total": total, "modes": modes}
    for mode in modes:
        passed = sum(1 for r in results if getattr(r, f"{mode}_passed") is True)
        summary[f"{mode}_passed"] = passed
        summary[f"{mode}_rate"] = round(passed / total, 4) if total else 0

    if "original" in modes and "adversarial" in modes:
        summary["attack_success"] = sum(
            1 for r in results if r.original_passed and not r.adversarial_passed
        )
    summary["results"] = [asdict(r) for r in results]

    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSummary saved to {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
