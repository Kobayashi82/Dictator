# Dictado

Aplicación de escritorio para Windows 10/11 para **dictar por voz a un documento**, todo en local.
Parakeet TDT 0.6B v3 transcribe frase a frase y un LLM local pequeño corrige los párrafos ya cerrados
mientras sigues hablando. La idea completa está en [SPEC.md](SPEC.md) y, como antecedente, en [dictador.md](dictador.md).

## Uso en desarrollo

```sh
uv sync
uv run dictado                 # la app
uv run dictado --fake-asr      # sin micrófono ni modelos: frases de ejemplo
uv run pytest                  # tests
```

Los modelos (Parakeet v3 int8 y Silero VAD) van en `%LOCALAPPDATA%\Dictado\models`.

## Atajos

| Atajo | Acción |
|---|---|
| `F9` | Dictar / pausa |
| `Ctrl+Intro` | Nuevo párrafo |
| `Ctrl+S` / `Ctrl+O` | Guardar / abrir |

## Cómo se corta el dictado

- **Pausa corta** (0,8 s por defecto): cierra una frase, que se transcribe y se añade al párrafo.
- **Pausa larga** (2,5 s por defecto): cierra el párrafo.
