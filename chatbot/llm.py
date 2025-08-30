import json, time
from typing import List, Dict, Any
from openai import OpenAI
from .config import OPENAI_API_KEY

SYSTEM_PROMPT = (
    "Eres un orquestador MCP. Cuando el usuario pida IO en Filesystem o GitHub, "
    "emite líneas con comandos tipo:\n"
    "!fs {\"tool\":\"list_directory\",\"args\":{\"path\":\"D:/...\",\"recursive\":false}}\n"
    "!gh {\"tool\":\"list_commits\",\"args\":{\"owner\":\"...\",\"repo\":\"...\",\"sha\":\"main\"}}\n"
    "!local {\"tool\":\"json_validate\", ...}\n"
    "!invest {\"tool\":\"price_quote\",\"args\":{\"symbols\":[\"BTC\",\"ETH\",\"SPY\",\"GLD\"],\"useLive\":true}}\n"
    "!invest {\"tool\":\"risk_metrics\",\"args\":{\"symbols\":[\"SPY\",\"QQQ\",\"GLD\",\"BTC\"],\"riskFree\":0.02,\"lookbackDays\":252,\"useLive\":true}}\n"
    "!invest {\"tool\":\"build_portfolio\",\"args\":{\"capital\":10000,\"riskLevel\":3,\"allowedSymbols\":[\"SPY\",\"QQQ\",\"GLD\",\"BTC\",\"ETH\"],\"useLive\":true}}\n"
    "No inventes parámetros. Si faltan, pídelo."
)

class LLM:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model

    def chat(self, history, user_msg: str) -> str:
        messages = [{"role":"system","content":SYSTEM_PROMPT}, *history, {"role":"user","content":user_msg}]
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=0.2
        )
        return resp.choices[0].message.content.strip()