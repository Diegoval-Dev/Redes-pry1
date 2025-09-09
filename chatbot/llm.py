import json, time
from typing import List, Dict, Any
from openai import OpenAI
from .config import OPENAI_API_KEY

SYSTEM_PROMPT = """
Eres un asistente-orquestador MCP en español.

REGLAS:
- Si la petición es de conocimiento general, responde en texto.
- Si la intención es ACCIONABLE, emite UNA o más líneas al FINAL con el formato:

  !mcp {"server":"<opcional>","tool":"<tool_name>","args":{...}}

Notas:
- "server" es opcional si el nombre de la tool es único en la flota. Si hay ambigüedad, pide al usuario que elija o incluye "server".
- No inventes parámetros: respétalos según el schema de la tool (descubierto vía handshake).
- Si faltan datos esenciales, pídelos brevemente y **no** emitas la línea hasta tenerlos.

EJEMPLOS:
Usuario: “Lista mazos de Anki”
Asistente:
!mcp {"tool":"anki_list_decks","args":{}}

Usuario: “Importa esta nota en Anki”
Asistente:
!mcp {"tool":"anki_import","args":{"format":"markdown","payload":"### Deck: Demo\nQ: Hola\nA: Hello\n---\n"}}

- Además de !fs/!gh/!local/!invest/!wfm, puedes usar:
  !mcp {"tool":"__list_tools__"}
  !mcp {"tool":"<name>","args":{...},"server":"fs|gh|invest|wfm|local"}
  
  - Si el usuario pide "¿qué herramientas tienes?" / "lista de herramientas" / "help tools",
  RESPONDE brevemente y EMITE al final:
  !mcp {"tool":"__list_tools__"}

"""

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
