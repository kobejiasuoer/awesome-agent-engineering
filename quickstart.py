"""Dependency-free tour of the RAG data flow.

This script deliberately uses local character n-gram retrieval and a small,
deterministic answerer. It is an orientation tool, not a replacement for the
API-backed implementation in rag-lessons/01_getting_started.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    source: str
    text: str
    search_alias: str


POLICIES = (
    Policy(
        "employee_handbook.md / 年假制度",
        "入职满 1 年享有 5 天带薪年假，满 3 年享有 10 天，满 5 年及以上享有 15 天。",
        "annual leave: 5 days after 1 year, 10 days after 3 years, "
        "15 days after 5 years",
    ),
    Policy(
        "employee_handbook.md / 病假制度",
        "病假需提供三甲医院病假条，期间发放基本工资的 60%。",
        "sick leave requires a hospital note and pays 60 percent of base salary",
    ),
    Policy(
        "employee_handbook.md / 远程办公",
        "经直属上级批准，员工每周可远程办公最多 2 个工作日；试用期员工不适用。",
        "remote work up to 2 days per week with manager approval; "
        "probationary employees are not eligible",
    ),
    Policy(
        "finance_policy.md / 差旅报销",
        "差旅住宿一线城市不超过 500 元每晚，报销单需在费用发生后 30 天内提交。",
        "travel hotel limit 500 yuan per night; submit expenses within 30 days",
    ),
)


def tokens(text: str) -> set[str]:
    """Return ASCII words plus CJK unigrams and bigrams."""
    lowered = text.lower()
    result = set(re.findall(r"[a-z0-9]+", lowered))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    result.update(cjk)
    result.update(cjk[i : i + 2] for i in range(len(cjk) - 1))
    return result


def retrieve(question: str, top_k: int = 2) -> list[tuple[Policy, float]]:
    query_tokens = tokens(question)
    ranked: list[tuple[Policy, float]] = []
    for policy in POLICIES:
        doc_tokens = tokens(f"{policy.text} {policy.search_alias}")
        overlap = query_tokens & doc_tokens
        score = len(overlap) / max(len(query_tokens), 1)
        ranked.append((policy, score))
    return sorted(ranked, key=lambda item: item[1], reverse=True)[:top_k]


def _requested_years(question: str) -> int | None:
    match = re.search(r"(\d+)\s*年", question)
    if not match:
        match = re.search(r"after\s+(\d+)\s+years?", question.lower())
    return int(match.group(1)) if match else None


def answer(question: str, context: Policy) -> str:
    years = _requested_years(question)
    asks_leave = "年假" in question or "annual" in question.lower()
    english = not re.search(r"[\u4e00-\u9fff]", question)

    if asks_leave and years is not None:
        thresholds = [(int(a), int(b)) for a, b in re.findall(
            r"满\s*(\d+)\s*年[^，。]*?(\d+)\s*天", context.text
        )]
        eligible = [days for threshold, days in thresholds if years >= threshold]
        if eligible:
            days = max(eligible)
            if english:
                return f"After {years} years, the policy grants {days} days of paid annual leave. [Source 1]"
            return f"根据制度，入职满 {years} 年可享受 {days} 天带薪年假。【材料1】"

    if english:
        return f"The most relevant policy says: {context.search_alias}. [Source 1]"
    return f"最相关的制度原文是：{context.text}【材料1】"


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or "入职满 4 年有多少天年假？"
    ranked = retrieve(question)
    context = ranked[0][0]

    print("Awesome Agent Engineering / offline RAG tour")
    print("=" * 56)
    print(f"Question: {question}")
    print("\n[1/4] Vectorize locally with character n-grams")
    print(f"      query features: {len(tokens(question))}")
    print("[2/4] Retrieve the most relevant policies")
    for index, (policy, score) in enumerate(ranked, 1):
        print(f"      {index}. score={score:.3f}  {policy.source}")
    print("[3/4] Build grounded context")
    print(f"      [Source 1] {context.text}")
    print("[4/4] Generate a deterministic, cited answer")
    print(f"      {answer(question, context)}")
    print("\nNext: rag-lessons/01_getting_started/README.md")


if __name__ == "__main__":
    main()
