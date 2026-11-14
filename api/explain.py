"""The LSTM owns the numbers. The LLM (Qwen via ChatGroq) only narrates them.
Guardrail: if the text contains a number that is not in the facts, we discard it
and return a plain template sentence instead."""
import json
import os
import re

SYSTEM = (
    "You explain air quality forecasts in plain language for a general reader. "
    "Use ONLY the numbers in the JSON provided. Never invent, change or add numbers. "
    "If the data does not explain something, say so. Maximum 70 words, no markdown.")


def allowed_numbers(facts: dict) -> set[str]:
    ok = {"1", "24"}
    for v in facts.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            ok |= {str(v), str(round(v)), str(round(v, 1))}
    return ok


def numbers_ok(text: str, facts: dict) -> bool:
    return all(n in allowed_numbers(facts) for n in re.findall(r"\d+(?:\.\d+)?", text))


def template(f: dict) -> str:
    return (f"{f['city']}: the model expects AQI around {f['aqi_p50']} ({f['category']}) "
            f"{f['when']}, likely between {f['aqi_p10']} and {f['aqi_p90']}. "
            f"Trend: {f['trend']}.")


def narrate(facts: dict) -> dict:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=os.getenv("GROQ_MODEL", "qwen/qwen3-32b"), temperature=0.2,
                       max_tokens=1200, timeout=20, max_retries=1)
        msg = llm.invoke([SystemMessage(content=SYSTEM),
                          HumanMessage(content=json.dumps(facts) + "\n/no_think")])
        text = re.sub(r"<think>.*?</think>", "", str(msg.content), flags=re.S).strip()
        if text and numbers_ok(text, facts):
            return {"text": text, "source": "llm"}
    except Exception as e:  # missing key, quota, timeout...
        print("explain fallback:", e)
    return {"text": template(facts), "source": "template"}
