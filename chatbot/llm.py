import json, time
from typing import List, Dict, Any
from openai import OpenAI
from .config import OPENAI_API_KEY

SYSTEM_PROMPT = (
    "Eres un orquestador MCP. Cuando el usuario pida operaciones de archivos o GitHub, "
    "responde con comandos explícitos que empiecen con !fs o !gh seguidos de un JSON con argumentos. "
    "Ejemplos:\n"
    "!fs {\"tool\":\"list_directory\",\"args\":{\"path\":\"D:/...\",\"recursive\":false}}\n"
    "!gh {\"tool\":\"list_commits\",\"args\":{\"owner\":\"...\",\"repo\":\"...\",\"sha\":\"main\"}}\n"
    "Para dudas, pide parámetros mínimos y no inventes valores."
)

class LLM:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model

    def chat(self, history: List[Dict[str, str]], user_msg: str) -> str:
        messages = [{"role":"system","content":SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role":"user","content":user_msg})
        resp = self.client.chat.completions.create(model=self.model, messages=messages, temperature=0.2)
        return resp.choices[0].message.content.strip()
