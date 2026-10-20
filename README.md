# Dictado

Aplicación de escritorio para Windows 10/11 para **dictar por voz a un documento**, todo en local y sin conexión
(salvo la descarga inicial de modelos). Parakeet TDT 0.6B v3 transcribe frase a frase en la CPU y un LLM pequeño
corrige los párrafos ya cerrados mientras sigues hablando. La idea completa está en [SPEC.md](SPEC.md) y, como
antecedente, en [dictador.md](dictador.md).

## Cómo funciona

```
Micrófono → Silero VAD → frases (pausa corta) → Parakeet → editor
                       → párrafo (pausa larga) → cola → LLM → salvaguarda → editor
```

- **Pausa corta** (0,8 s): cierra una frase, que se transcribe (~0,1 s) y se añade al párrafo, en gris.
- **Pausa larga** (2,5 s): cierra el párrafo y lo manda al corrector. La marca del margen cambia de color:
  azul = corrigiendo, verde = corregido, naranja = corrección descartada, morado = editado a mano.
- Cada párrafo guarda el **texto original y el corregido**. Clic en la marca del margen (o botón derecho):
  ver cambios, revertir al original, volver a corregir.
- Si editas un párrafo a mano, el corrector ya no lo toca.
- **Modos:** Prosa, Poesía (cada frase es un verso; la pausa larga cierra la estrofa), Notas/Lista y Sin corrección.
- **Comandos de voz:** «punto y aparte», «nuevo párrafo», «nueva estrofa», «borra la última frase», «título …».
- **Glosario** general (Ajustes) y por documento (Documento › Glosario) para nombres propios y vocabulario raro.

## El corrector

En **Herramientas › Ajustes › Corrector** se elige:

- **Integrado:** Qwen3.5 2B con llama-server, en la **CPU** (RAM) o en la **GPU** (Vulkan). Los dos se descargan desde
  **Herramientas › Modelos** (≈1,3 GB) y Dictado arranca y para el servidor solo. Medido en un Ryzen 7 7800X3D:
  un párrafo de 63 palabras en ~2 s en CPU.
- **Servidor externo:** cualquier endpoint compatible con OpenAI (Ollama, llama-swap, llama-server, LM Studio),
  local o en otro equipo, con URL, modelo y clave. Ver [docs/LLM.md](docs/LLM.md).

Una **salvaguarda** rechaza las correcciones que cambian demasiado el texto (distancia de edición, longitud, número de
versos) y limpia los preámbulos típicos («Aquí tienes…»). Si el corrector falla o no responde, el dictado sigue y el
párrafo se queda con el texto de Parakeet; Documento › Reintentar lo vuelve a intentar.

## Archivos

- Proyecto `.dictado` (JSON): todos los párrafos con original, corrección y estado. Al reabrirlo, el dictado sigue al
  final.
- Exportar a `.docx`, `.md` y `.txt`; importar `.txt` y `.md`.
- Autoguardado de recuperación cada 60 s.
- Modelos en `%LOCALAPPDATA%\Dictado\models`; ajustes en `%APPDATA%\Dictado\config.json`.

## Atajos

| Atajo | Acción |
|---|---|
| `F9` | Dictar / pausa |
| `Ctrl+Intro` | Nuevo párrafo |
| `Ctrl+S` / `Ctrl+O` | Guardar / abrir |
| `Ctrl+E` | Exportar |
| `Ctrl+,` | Ajustes |

## Desarrollo

```sh
uv sync
uv run dictado                          # la app
uv run dictado --fake-asr --fake-llm    # sin micrófono, modelos ni LLM
uv run dictado --transcribe audio.wav   # diagnóstico: VAD + Parakeet sobre un .wav de 16 kHz mono
uv run pytest                           # tests
```

## Ejecutable

```sh
uv run pyinstaller dictado.spec --noconfirm
```

Genera `dist/Dictado/Dictado.exe` (~200 MB, sin modelos: se descargan desde la propia app la primera vez).

## Licencias de los modelos

Parakeet TDT 0.6B v3 (NVIDIA, CC-BY-4.0, versión ONNX de istupakov), Silero VAD (MIT), Qwen3.5 2B (Apache-2.0,
GGUF de unsloth), llama.cpp (MIT).
