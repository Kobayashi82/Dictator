"""Cliente para cualquier endpoint compatible con OpenAI (llama-swap, llama-server, Ollama, LM Studio…)."""

from __future__ import annotations

import re
import time

# Desactivar el razonamiento: Ollama entiende `reasoning_effort`, llama-server la plantilla de chat.
_NO_THINK = {"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 60.0,
        temperature: float = 0.1,
        disable_thinking: bool = True,
    ):
        from openai import OpenAI

        self.model = model
        self.temperature = temperature
        self.disable_thinking = disable_thinking
        self._extra_ok = True  # se pone a False si el servidor rechaza los campos extra
        self._client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key or "sin-clave", timeout=timeout, max_retries=0)

    def list_models(self) -> list[str]:
        try:
            return sorted(m.id for m in self._client.models.list().data)
        except Exception as e:  # noqa: BLE001
            raise LLMError(_describe(e)) from e

    def complete(self, messages: list[dict], max_tokens: int) -> str:
        import openai

        extra = _NO_THINK if self.disable_thinking and self._extra_ok else None
        try:
            response = self._create(messages, max_tokens, extra)
        except openai.BadRequestError as e:
            if not extra:
                raise LLMError(_describe(e)) from e
            self._extra_ok = False  # p. ej. un servidor que no admite `reasoning_effort: none`
            try:
                response = self._create(messages, max_tokens, None)
            except Exception as e2:  # noqa: BLE001
                raise LLMError(_describe(e2)) from e2
        except Exception as e:  # noqa: BLE001
            raise LLMError(_describe(e)) from e
        if not response.choices:
            raise LLMError("Respuesta vacía del servidor.")
        content = response.choices[0].message.content or ""
        if not content.strip() and response.choices[0].finish_reason == "length":
            raise LLMError("El modelo agotó los tokens razonando: desactiva el razonamiento o usa otro modelo.")
        return content

    def _create(self, messages, max_tokens, extra):
        messages = list(messages)
        if self.disable_thinking and not self._extra_ok:
            # Último recurso para Qwen3 en servidores sin los campos extra.
            messages[0] = {**messages[0], "content": messages[0]["content"] + "\n/no_think"}
        return self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens,
            extra_body=extra,
        )


def _describe(e: Exception) -> str:
    import openai

    if isinstance(e, openai.APITimeoutError):
        return "Tiempo de espera agotado."
    if isinstance(e, openai.APIConnectionError):
        return "No se puede conectar con el servidor."
    if isinstance(e, openai.AuthenticationError):
        return "Clave API no válida."
    if isinstance(e, openai.NotFoundError):
        return "El servidor no encuentra ese modelo o esa ruta (¿falta /v1 en la URL?)."
    if isinstance(e, openai.APIStatusError):
        return f"Error del servidor ({e.status_code}): {e.message}"
    return str(e) or e.__class__.__name__


_FAKE_FIXES = {
    "esperava": "esperaba",
    "salian": "salían",
    "dia": "día",
    "atrevio": "atrevió",
    "habia": "había",
    "tambien": "también",
    "mas": "más",
}


class FakeLLMClient:
    """--fake-llm: «corrige» unas cuantas palabras, pone mayúscula y punto final, con un retraso simulado."""

    model = "falso"

    def __init__(self, *_args, delay: float = 1.0, **_kwargs):
        self.delay = delay

    def list_models(self) -> list[str]:
        return ["falso"]

    def complete(self, messages: list[dict], max_tokens: int) -> str:
        time.sleep(self.delay)
        text = messages[-1]["content"].split("Texto a corregir:\n", 1)[-1]
        lines = []
        for line in text.split("\n"):
            line = re.sub(r"\w+", lambda m: _FAKE_FIXES.get(m.group(0), m.group(0)), line).strip()
            if line:
                line = line[0].upper() + line[1:]
            lines.append(line)
        out = "\n".join(lines)
        if out and out[-1] not in ".!?…" and "\n" not in out:
            out += "."
        return out
