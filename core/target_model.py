import logging
import math
import re
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import requests

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.prompts import JUDGE_SYSTEM_PROMPT, JUDGE_SYSTEM_PROMPT_COT

logger = logging.getLogger(__name__)


class TargetModelClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        max_retries: int = 3,
        use_local_transformers: bool = False,
        max_new_tokens: int = 512,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or "EMPTY"
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_local_transformers = use_local_transformers
        self.max_new_tokens = max_new_tokens
        # 从config/prompts.py导入判题提示词
        self.system_prompt = JUDGE_SYSTEM_PROMPT
        self.system_prompt_cot = JUDGE_SYSTEM_PROMPT_COT

    def judge(self, spec: str, rtl: str, use_cot: bool = False) -> Optional[Dict]:
        if self.use_local_transformers:
            return self._judge_local(spec, rtl, use_cot=use_cot)

        for attempt in range(self.max_retries):
            try:
                return self._judge_http(spec, rtl, use_cot=use_cot)
            except Exception as e:
                logger.warning(
                    "Target model HTTP judge failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt + 1 >= self.max_retries:
                    return None
        return None

    def judge_batch(
        self,
        spec: str,
        rtls: List[str],
        use_cot: bool = False,
        max_workers: int = 8,
    ) -> List[Optional[Dict]]:
        if not rtls:
            return []

        unique_rtls: List[str] = []
        seen = set()
        for rtl in rtls:
            if rtl in seen:
                continue
            seen.add(rtl)
            unique_rtls.append(rtl)

        unique_results: Dict[str, Optional[Dict]] = {}
        workers = 1 if self.use_local_transformers else max(1, int(max_workers))

        if workers == 1:
            for rtl in unique_rtls:
                unique_results[rtl] = self.judge(spec, rtl, use_cot=use_cot)
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                fut_to_rtl = {
                    ex.submit(self.judge, spec, rtl, use_cot): rtl
                    for rtl in unique_rtls
                }
                for fut in as_completed(fut_to_rtl):
                    rtl = fut_to_rtl[fut]
                    try:
                        unique_results[rtl] = fut.result()
                    except Exception as e:
                        logger.warning("judge_batch item failed: %s", e)
                        unique_results[rtl] = None

        return [unique_results.get(rtl) for rtl in rtls]

    def _build_user_message(self, spec: str, rtl: str, use_cot: bool = False) -> str:
        if use_cot:
            tail = "Please verify step by step. The last line must be: FINAL_ANSWER: yes or FINAL_ANSWER: no"
        else:
            tail = "Only answer yes or no, nothing else."

        return (
            f"[Functional Specification]\\n{spec}\\n\\n"
            f"[RTL Code]\\n```verilog\\n{rtl}\\n```\\n\\n"
            f"Question: Does this RTL code correctly implement the functional specification?\\n{tail}"
        )

    def _judge_http(self, spec: str, rtl: str, use_cot: bool = False) -> Optional[Dict]:
        user_message = self._build_user_message(spec, rtl, use_cot=use_cot)
        system_prompt = self.system_prompt_cot if use_cot else self.system_prompt
        # COT模式需要更多tokens来生成推理过程
        if use_cot:
            # 动态计算max_tokens，确保不超过context限制
            max_context = 4096
            # 估算输入tokens（粗略估算：字符数/4）
            input_chars = len(system_prompt) + len(user_message)
            estimated_input_tokens = input_chars // 4
            # 保留至少300 tokens给CoT输出
            max_tokens = max(300, max_context - estimated_input_tokens - 100)
            max_tokens = min(max_tokens, 1024)  # 最大不超过1024
        else:
            max_tokens = 64
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "logprobs": True,
            "top_logprobs": 20,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        choice = (data.get("choices") or [None])[0]
        if not choice:
            return None

        content = ((choice.get("message") or {}).get("content") or "").strip()
        parsed = self._extract_yes_no(content)
        if parsed is None:
            return None

        p_yes, p_no = None, None
        logprobs = choice.get("logprobs") or {}
        lp_content = logprobs.get("content") if isinstance(logprobs, dict) else None
        logit_yes, logit_no = None, None
        if lp_content:
            p_yes, p_no, logit_yes, logit_no = self._extract_yes_no_signals(lp_content)
        else:
            p_yes, p_no = None, None

        # confidence = p_yes（verifier认为代码正确的概率）
        if p_yes is not None:
            confidence = round(float(p_yes), 4)
        else:
            confidence = 1.0 if parsed else 0.0

        result = {
            "is_correct": parsed,
            "confidence": confidence,  # = p_yes
            "raw_output": content,
        }
        if p_yes is not None:
            result["p_yes"]    = round(float(p_yes), 4)
            result["p_no"]     = round(float(p_no),  4)
            # margin = logit_no - logit_yes（正值表示倾向no，负值表示倾向yes）
            # 用归一化概率的log-odds近似：log(p_no/p_yes)
            if p_yes > 0 and p_no > 0:
                import math as _math
                result["margin"] = round(_math.log(p_no / p_yes), 4)
        if logit_yes is not None:
            result["logit_yes"] = round(float(logit_yes), 4)
            result["logit_no"]  = round(float(logit_no),  4)
        return result

    def _judge_local(self, spec: str, rtl: str, use_cot: bool = False) -> Optional[Dict]:
        logger.warning("use_local_transformers=True is not supported in this build")
        return None

    @staticmethod
    def _extract_yes_no(text: str) -> Optional[bool]:
        if not text:
            return None
        low = text.strip().lower()

        # 优先匹配 FINAL_ANSWER: yes/no 格式
        m = re.search(r"final_answer\s*:\s*(yes|no)", low)
        if m:
            return m.group(1) == "yes"

        # 兼容原格式
        if low in {"yes", "yes.", "yes!"}:
            return True
        if low in {"no", "no.", "no!"}:
            return False

        m = re.search(r"\b(yes|no)\b", low)
        if not m:
            return None
        return m.group(1) == "yes"

    @staticmethod
    def _extract_yes_no_signals(logprobs_content: list) -> tuple:
        """返回 (p_yes, p_no, logit_yes, logit_no)。
        p_yes/p_no 是归一化到 yes+no=1 的概率。
        logit_yes/logit_no 是第一个输出token位置的原始logprob（未归一化）。
        失败返回 (None, None, None, None)。
        """
        raw_lp_yes, raw_lp_no = None, None  # 第一个token位置的原始logprob
        prob_yes, prob_no = 0.0, 0.0

        for block in (logprobs_content or []):
            top = block.get("top_logprobs") if isinstance(block, dict) else None
            if not top:
                continue
            for entry in top:
                if not isinstance(entry, dict):
                    continue
                token = (entry.get("token") or "").strip().lower()
                lp = entry.get("logprob")
                if lp is None:
                    continue
                try:
                    prob = math.exp(float(lp))
                except Exception:
                    continue
                if token == "yes":
                    prob_yes += prob
                    if raw_lp_yes is None:
                        raw_lp_yes = float(lp)
                elif token == "no":
                    prob_no += prob
                    if raw_lp_no is None:
                        raw_lp_no = float(lp)

        total = prob_yes + prob_no
        if total <= 0:
            return None, None, None, None
        return prob_yes / total, prob_no / total, raw_lp_yes, raw_lp_no

    @staticmethod
    def _p_yes_no_from_logprobs_content(logprobs_content: list) -> tuple:
        """兼容旧调用；返回 (p_yes, p_no) 归一化概率"""
        p_yes, p_no, _, _ = TargetModelClient._extract_yes_no_signals(logprobs_content)
        return p_yes, p_no

    @staticmethod
    def _confidence_from_logprobs_content(logprobs_content: list) -> Optional[float]:
        """兼容旧调用；返回 p_yes（即 verifier 认为代码正确的概率）"""
        p_yes, _ = TargetModelClient._p_yes_no_from_logprobs_content(logprobs_content)
        return p_yes
