import json
import logging
import sys
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple
from tqdm import tqdm
import yaml
import requests

# 配置日志：INFO 写文件，终端只显示 WARNING/ERROR，方便 tqdm 进度条不被刷掉
Path("logs").mkdir(exist_ok=True)
_fh = logging.FileHandler("logs/filter_qualified.log", encoding="utf-8")
_fh.setLevel(logging.INFO)
_fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
_ch = logging.StreamHandler(sys.stdout)
_ch.setLevel(logging.WARNING)
_ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_fh, _ch])
logger = logging.getLogger(__name__)

_HF_TOKENIZER = None
_HF_MODEL = None
_MODEL_LOCK = threading.Lock()


def _load_local_model(model_path: str):
    """
    使用 transformers 从本地路径懒加载模型，供无服务模式使用。
    """
    global _HF_TOKENIZER, _HF_MODEL
    if _HF_MODEL is not None and _HF_TOKENIZER is not None:
        return _HF_TOKENIZER, _HF_MODEL

    with _MODEL_LOCK:
        if _HF_MODEL is not None and _HF_TOKENIZER is not None:
            return _HF_TOKENIZER, _HF_MODEL
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch  # noqa: F401  # 仅用于加载模型和推理设备
        except ImportError as e:
            logger.error(f"加载本地模型依赖失败，请安装 transformers 和 torch: {e}")
            raise

        logger.info(f"正在从本地路径加载模型: {model_path}")
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True,
            local_files_only=True
        )
        hf_model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
            local_files_only=True,
        )
        hf_model.eval()
        _HF_TOKENIZER, _HF_MODEL = tokenizer, hf_model
        logger.info("本地模型加载完成。")
        return tokenizer, hf_model


def _confidence_from_logprobs_content(logprobs_content: list) -> Optional[Tuple[bool, float]]:
    """
    从 OpenAI 兼容 API 的 choices[0].logprobs.content 中计算 P(yes)/P(no)，返回 (is_correct, confidence)。
    遍历每个 token 的 top_logprobs，累加 yes/no 对应 token 的概率并归一化；若无则返回 None（回退到 1.0）。
    """
    import math
    # token 字符串归一化后匹配：与本地 _get_yes_no_token_ids 对应（yes/Yes/YES、no/No/NO 及带前导空格）
    def is_yes(t: str) -> bool:
        s = (t or "").strip().lower()
        return s == "yes"
    def is_no(t: str) -> bool:
        s = (t or "").strip().lower()
        return s == "no"

    p_yes, p_no = 0.0, 0.0
    for block in (logprobs_content or []):
        top = block.get("top_logprobs")
        if top:
            for entry in top:
                if not isinstance(entry, dict):
                    continue
                token = entry.get("token") or ""
                lp = entry.get("logprob")
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
            token = (block.get("token") or "").strip().lower()
            lp = block.get("logprob")
            if lp is not None:
                try:
                    p = math.exp(float(lp))
                    if is_yes(token):
                        p_yes += p
                    elif is_no(token):
                        p_no += p
                except (TypeError, ValueError):
                    pass
    total = p_yes + p_no
    if total <= 0:
        return None
    p_yes, p_no = p_yes / total, p_no / total
    return (p_yes >= p_no, max(p_yes, p_no))


def _get_yes_no_token_ids(tokenizer):
    """获取 tokenizer 中表示 yes/no 的 token id（可能多写法，取单 token）。"""
    yes_ids, no_ids = set(), set()
    for word in ("yes", "Yes", "YES", " no", "no", "No", "NO"):
        ids = tokenizer.encode(word, add_special_tokens=False)
        if len(ids) == 1:
            (yes_ids if "y" in word.lower() else no_ids).add(ids[0])
    return list(yes_ids), list(no_ids)


def _local_judge_yesno_with_logits(
    system_prompt: str, user_message: str, model_path: str
) -> tuple[bool, float]:
    """
    本地模型：只做一次前向，用下一个 token 的 logits 计算 P(yes)/P(no)，返回 (is_correct, confidence)。
    """
    import torch

    tokenizer, hf_model = _load_local_model(model_path)
    from transformers import PreTrainedTokenizerBase

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    if isinstance(tokenizer, PreTrainedTokenizerBase) and hasattr(tokenizer, "apply_chat_template"):
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        text = system_prompt + "\n\n" + user_message

    inputs = tokenizer(text, return_tensors="pt").to(hf_model.device)
    yes_ids, no_ids = _get_yes_no_token_ids(tokenizer)
    if not yes_ids or not no_ids:
        # 回退：用生成并解析
        return _local_judge_yesno_fallback(system_prompt, user_message, model_path)

    with torch.inference_mode():
        out = hf_model(**inputs)
        logits = out.logits[0, -1, :].float()  # 下一个 token 的 logits
    logits = logits - logits.max()
    probs = torch.exp(logits) / torch.exp(logits).sum()
    p_yes = probs[list(yes_ids)].sum().item()
    p_no = probs[list(no_ids)].sum().item()
    total = p_yes + p_no
    if total <= 0:
        return _local_judge_yesno_fallback(system_prompt, user_message, model_path)
    p_yes, p_no = p_yes / total, p_no / total
    is_correct = p_yes >= p_no
    confidence = max(p_yes, p_no)
    return is_correct, confidence


def _local_judge_yesno_fallback(
    system_prompt: str, user_message: str, model_path: str
) -> tuple[bool, float]:
    """回退：生成短序列并解析 yes/no，置信度置为 1.0。"""
    tokenizer, hf_model = _load_local_model(model_path)
    from transformers import PreTrainedTokenizerBase
    import torch

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    if isinstance(tokenizer, PreTrainedTokenizerBase) and hasattr(tokenizer, "apply_chat_template"):
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        text = system_prompt + "\n\n" + user_message
    inputs = tokenizer(text, return_tensors="pt").to(hf_model.device)
    pad_id = getattr(tokenizer, "pad_token_id", None) or tokenizer.eos_token_id
    with torch.inference_mode():
        out = hf_model.generate(
            **inputs, max_new_tokens=8, do_sample=False, pad_token_id=pad_id
        )
    output_ids = out[0][inputs["input_ids"].shape[1] :]
    resp = tokenizer.decode(output_ids, skip_special_tokens=True).strip().lower()
    if "yes" in resp and "no" not in resp:
        return True, 1.0
    if "no" in resp:
        return False, 1.0
    return False, 0.0

class FilterClient:
    def __init__(self, config):
        self.base_url = config['target_model']['base_url'].rstrip('/')
        self.api_key = config['target_model']['api_key']
        self.model = config['target_model']['model']
        self.timeout = config['target_model']['timeout']
        self.system_prompt = "你是 Verilog 代码验证专家。判断给定代码是否正确实现了功能规范。只回答 yes 或 no，不要其他内容。"
        self.use_local_transformers = config['target_model'].get('use_local_transformers', True)
        self.max_new_tokens = config['target_model'].get('max_new_tokens', 256)

    def judge(self, sample):
        user_message = (
            f"**功能规范**：\n{sample['spec']}\n\n**代码**：\n```verilog\n{sample['rtl']}\n```\n\n"
            "请判断代码是否正确实现了功能规范。只回答 yes 或 no，不要其他内容。"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.0,
        }

        # 本地模型：用 next-token logits 得到 yes/no 与置信度
        if self.use_local_transformers:
            try:
                is_correct, confidence = _local_judge_yesno_with_logits(
                    self.system_prompt, user_message, self.model
                )
                verdict = {"is_correct": is_correct, "confidence": round(confidence, 4)}
                if is_correct:
                    return sample, verdict
            except Exception as e:
                logger.error(f"样本 {sample.get('id')} 本地模型推理失败: {e}")
            return None, None

        # HTTP 接口：请求 logprobs 以计算置信度，若无则回退为 1.0
        payload["logprobs"] = True
        payload["top_logprobs"] = 20
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return None, None
            data = response.json()
            choice = (data.get("choices") or [None])[0]
            if not choice:
                return None, None
            content = (choice.get("message") or {}).get("content") or ""
            content_lower = content.strip().lower()
            if "no" in content_lower:
                return None, None
            if "yes" not in content_lower:
                return None, None
            # 判对：从 logprobs 计算置信度
            confidence = 1.0
            logprobs = choice.get("logprobs")
            if logprobs:
                content_blocks = logprobs.get("content")
                if content_blocks:
                    parsed = _confidence_from_logprobs_content(content_blocks)
                    if parsed is not None:
                        _, confidence = parsed
            verdict = {"is_correct": True, "confidence": round(confidence, 4)}
            return sample, verdict
        except Exception as e:
            logger.error(f"样本 {sample.get('id')} HTTP 请求失败: {e}")
            return None, None

def _sample_id(sample: dict, index: int) -> str:
    """稳定 id，用于断点续跑去重。"""
    return sample.get("task_id") or sample.get("id") or str(index)


def _run_judge(args):
    """供线程池调用：(config, index, sample) -> (index, sample, (sample_or_none, verdict))."""
    cfg, idx, s = args
    sample, verdict = FilterClient(cfg).judge(s)
    return (idx, s, (sample, verdict))


def main():
    # 1. 加载配置
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # 2. 加载数据
    input_path = Path(config['data']['input_path'])
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            samples = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        logger.error(f"文件: {input_path.absolute()}")
        logger.error(f"错误位置: 第 {e.lineno} 行, 第 {e.colno} 列 (字符 {e.pos})")
        with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        n = len(lines)
        start = max(0, e.lineno - 3)
        end = min(n, e.lineno + 2)
        logger.error("出错处附近内容:")
        for i in range(start, end):
            marker = " >>> " if i == e.lineno - 1 else "     "
            logger.error(f"{marker}{i+1:6d}: {lines[i].rstrip()[:120]}")
        raise SystemExit(1)

    if not isinstance(samples, list):
        samples = [samples] if isinstance(samples, dict) else []
    indexed = list(enumerate(samples))

    # 断点：若存在 checkpoint 则跳过已完成的样本
    checkpoint_path = Path("data/qualified_filter_checkpoint.json")
    done_ids = set()
    qualified_samples = []
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                ck = json.load(f)
            done_ids = set(ck.get("done_ids", []))
            qualified_samples = ck.get("qualified", [])
            logger.info(f"断点续跑：已完成 {len(done_ids)} 条，合格 {len(qualified_samples)} 条")
            print(f"断点续跑：已完成 {len(done_ids)} 条，合格 {len(qualified_samples)} 条；继续筛选中…")
        except Exception as e:
            logger.warning(f"读取 checkpoint 失败，从头开始: {e}")

    todo = [(i, s) for i, s in indexed if _sample_id(s, i) not in done_ids]
    if not todo:
        print("所有样本已处理完毕（断点已覆盖全部）。")
        output_path = Path("data/qualified_samples.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(qualified_samples, f, indent=2, ensure_ascii=False)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        return

    logger.info(f"读取到 {len(samples)} 个原始样本，待处理 {len(todo)} 条。")
    print(f"共 {len(samples)} 个样本，待处理 {len(todo)} 条（进度见下方，详细日志见 logs/filter_qualified.log）…")

    use_local = config['target_model'].get('use_local_transformers', True)
    num_workers = 1 if use_local else config['parallelism']['num_workers']
    save_every = 200  # 每完成 N 条写一次 checkpoint

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(_run_judge, (config, i, s)): (i, s) for i, s in todo}
        done_count = 0
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="筛选中",
            unit="样本",
            mininterval=1.0,
            dynamic_ncols=True,
        ):
            idx, s, (sample, verdict) = future.result()
            sid = _sample_id(s, idx)
            done_ids.add(sid)
            if sample:
                sample['original_verdict'] = verdict
                qualified_samples.append(sample)
            done_count += 1
            if done_count % save_every == 0:
                with open(checkpoint_path, 'w', encoding='utf-8') as f:
                    json.dump({"done_ids": list(done_ids), "qualified": qualified_samples}, f, indent=2, ensure_ascii=False)
                logger.info(f"已保存断点：完成 {len(done_ids)} 条，合格 {len(qualified_samples)} 条")

    # 4. 保存最终结果并删除 checkpoint
    output_path = Path("data/qualified_samples.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(qualified_samples, f, indent=2, ensure_ascii=False)
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    logger.info(f"筛选完成！原始 {len(samples)}，合格 {len(qualified_samples)}，合格率 {len(qualified_samples)/len(samples)*100:.2f}%")
    print("\n筛选完成！")
    print(f"  原始总数: {len(samples)}")
    print(f"  合格样本: {len(qualified_samples)}")
    print(f"  合格率: {len(qualified_samples)/len(samples)*100:.2f}%")
    print(f"  结果已保存至: {output_path}")

if __name__ == "__main__":
    main()
