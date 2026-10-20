# Dictado — Especificación del proyecto

Aplicación de escritorio para Windows 10/11 que permite **dictar por voz a un documento**. Parakeet transcribe en local, el texto aparece en el editor y un LLM local pequeño **corrige y formatea los párrafos ya cerrados** mientras el usuario sigue hablando. El documento se guarda y se puede reabrir para continuar.

Todo funciona en local y sin conexión (salvo la descarga inicial de modelos). Debe ir bien en un **PC de gama media con varios años y GPU antigua**.

---

## 1. Objetivos

- Documento en blanco o existente → pulsar "Dictar" → el texto aparece frase a frase.
- Cada párrafo cerrado pasa por el LLM, que corrige errores de transcripción, ortografía y formato **sin reescribir el contenido**.
- Modos de corrección: **Prosa**, **Poesía**, **Notas/Lista** y **Sin corrección**.
- Guardar, abrir y continuar dictando donde se dejó.
- LLM intercambiable: cualquier endpoint compatible con OpenAI (llama-swap, llama-server, Ollama, LM Studio), con opción CPU o GPU.

## 2. No objetivos (por ahora)

- Streaming palabra a palabra (Parakeet TDT no es streaming; basta con frase a frase).
- Edición colaborativa, sincronización en la nube.
- Diarización (varios hablantes).

---

## 3. Stack

| Pieza | Elección | Notas |
|---|---|---|
| Lenguaje / entorno | Python 3.12 + **uv** | `uv run dictado` para desarrollo |
| UI | **PySide6** (Qt) | `QTextEdit` / `QTextDocument` para texto enriquecido |
| Audio | `sounddevice` | 16 kHz mono, float32 |
| VAD | **Silero VAD** (ONNX) | Corta por pausas |
| ASR | **Parakeet TDT 0.6B v3** vía `onnx-asr` (onnxruntime, CPU) | Multilingüe, incluye español, ya da puntuación y mayúsculas. Verificar la API exacta de `onnx-asr` al implementar. |
| LLM | Cliente `openai` (o `httpx`) contra endpoint configurable | Sin dependencia de un backend concreto |
| Empaquetado | **PyInstaller** (o Nuitka) → `.exe` | Los modelos NO van dentro del exe |

Modelos LLM recomendados para el equipo objetivo (GGUF, Q4_K_M):
- Por defecto: **Qwen3.5 2B** (thinking desactivado).
- Alternativas: Gemma 3n E2B / Gemma 3 1B; Qwen3.5 4B si el equipo lo permite.
- En GPU antigua: build **Vulkan** de llama.cpp, con descarga parcial de capas (`-ngl`).

---

## 4. Arquitectura

```
Micrófono ─► AudioCapture ─► VAD (segmenta por pausas)
                                   │ segmento de audio
                                   ▼
                              ASRWorker (Parakeet)
                                   │ frase transcrita
                                   ▼
                          DocumentModel  ◄────────► EditorView (Qt)
                                   │ párrafo cerrado
                                   ▼
                          CorrectionQueue ─► LLMClient (OpenAI API)
                                   │ corrección validada
                                   ▼
                          DocumentModel (aplica si procede)
```

- **Hilos:** la captura, el ASR y la corrección van fuera del hilo de UI (`QThread` o `concurrent.futures` + señales Qt). La UI nunca se bloquea.
- **Cola de corrección:** FIFO y un párrafo cada vez. Si llegan varios, se procesan en orden.

### Módulos sugeridos

```
dictado/
  app.py              # arranque, QApplication
  ui/main_window.py   # ventana, barra de herramientas, estado
  ui/editor.py        # editor, resaltado de cambios, revertir
  ui/settings.py      # diálogo de ajustes
  audio/capture.py    # sounddevice
  audio/vad.py        # Silero, lógica de pausas
  asr/parakeet.py     # carga y transcripción
  llm/client.py       # cliente OpenAI-compatible
  llm/prompts.py      # presets por modo
  llm/guard.py        # validación de la salida del LLM
  doc/model.py        # párrafos, estados, historial
  doc/storage.py      # guardar/abrir proyecto, exportar
  models/download.py  # descarga de modelos en primer arranque
  config.py           # ajustes persistentes (JSON en %APPDATA%)
```

---

## 5. Segmentación y párrafos

- **Pausa corta** (≈0,6–1 s, configurable): cierra una **frase** → se transcribe y se añade al párrafo actual.
- **Pausa larga** (≈2–3 s, configurable): cierra el **párrafo** → pasa a la cola de corrección.
- **Botón / atajo "Nuevo párrafo"** como alternativa manual.
- **Modo Poesía:** cada frase es un **verso** (salto de línea); la pausa larga cierra la **estrofa**.
- Comandos de voz (fase 3): "punto y aparte", "nueva estrofa", "borra la última frase", "título …". Se detectan con reglas antes de enviar texto al LLM.

---

## 6. Modelo de documento

Cada párrafo guarda:

```json
{
  "id": "uuid",
  "raw": "texto tal como lo dio Parakeet",
  "corrected": "texto corregido o null",
  "status": "dictating | pending | correcting | corrected | rejected | edited",
  "mode": "prosa | poesia | notas | ninguno",
  "user_edited": false
}
```

Reglas:
- El editor muestra `corrected` si existe y es aceptado; si no, `raw`.
- Si el usuario **edita a mano** un párrafo, `user_edited = true` y el LLM ya no lo toca. Si la edición ocurre mientras se corrige, la corrección se **descarta**.
- Cada párrafo corregido se puede **revertir** al original con un clic, y ver la diferencia (resaltado suave de lo cambiado).

---

## 7. Corrección con LLM

### Contexto enviado
- Prompt de sistema del modo activo.
- Uno o dos párrafos anteriores **solo como contexto** (marcados como "no modificar").
- El párrafo objetivo.
- Glosario del usuario (nombres propios, términos técnicos), editable en Ajustes.

### Parámetros
- `temperature` 0–0,2, `max_tokens` ≈ 1,5× la longitud del párrafo.
- Thinking desactivado (p. ej. `/no_think` o el flag de la plantilla, según el modelo).
- Timeout configurable; si vence, el párrafo queda en `raw` y se puede reintentar.

### Presets de prompt (borrador, en `llm/prompts.py`)
- **Prosa:** corrige ortografía, tildes, puntuación, concordancia y palabras mal transcritas por el contexto. No cambies el estilo, el vocabulario ni el orden. No añadas ni quites ideas. Devuelve solo el texto corregido.
- **Poesía:** respeta exactamente los saltos de línea y el número de versos. Corrige solo ortografía, tildes y palabras claramente mal transcritas. No toques ritmo, métrica ni puntuación expresiva.
- **Notas/Lista:** convierte enumeraciones habladas en listas Markdown; corrige errores; no resumas.
- **Ninguno:** no se llama al LLM.

### Salvaguarda (`llm/guard.py`) — imprescindible con modelos pequeños
Rechazar la corrección (estado `rejected`, se conserva `raw`) si:
- La distancia de edición normalizada entre `raw` y `corrected` supera un umbral (por defecto 0,2; configurable).
- La longitud cambia más de ±25 %.
- En modo Poesía, cambia el número de líneas.
- La salida contiene preámbulos ("Aquí tienes…"), comillas envolventes o etiquetas: limpiarlos primero y, si no se puede, rechazar.

---

## 8. Configuración del LLM

Ajustes:
- **URL base** (p. ej. `http://localhost:8080/v1`) y **nombre de modelo**.
- Clave API opcional (algunos servidores la piden).
- Botón **"Probar conexión"** (lista modelos con `/v1/models`).
- Con **llama-swap**: el desplegable de modelos se rellena desde `/v1/models`, y cambiar el modelo en caliente es simplemente cambiar el nombre en la petición. CPU/GPU se resuelve con dos entradas del mismo modelo en la config de llama-swap (`-ngl 0` y `-ngl 99`).
- Fase 4 (opcional): modo "gestionado", en el que la app arranca su propio `llama-server.exe` (build CPU o Vulkan) si no hay endpoint configurado.

Ejemplo orientativo de config de llama-swap (incluir en `docs/`):

```yaml
models:
  "corrector-cpu":
    cmd: llama-server --port ${PORT} -m qwen3.5-2b-q4_k_m.gguf -ngl 0 -c 4096
  "corrector-gpu":
    cmd: llama-server --port ${PORT} -m qwen3.5-2b-q4_k_m.gguf -ngl 99 -c 4096
```

---

## 9. Guardar y abrir

- **Formato nativo:** `.dictado` (JSON) con metadatos (versión, modo, glosario del documento) y la lista de párrafos completa (raw + corrected + estado). Permite deshacer y volver a corregir con otro modelo.
- **Exportar:** `.md`, `.txt` y `.docx` (`python-docx`), usando el texto visible.
- **Importar:** `.txt` y `.md` (cada párrafo entra como `raw` con `user_edited = true`).
- Autoguardado cada N segundos en un archivo de recuperación.
- Al reabrir, el dictado continúa al final y el contexto del LLM usa los últimos párrafos.

---

## 10. UI

- Barra superior: **Dictar / Pausa**, selector de **modo**, **Nuevo párrafo**, indicador de nivel de micrófono, estado del LLM (conectado / corrigiendo / error).
- Editor central con fuente legible; el párrafo en dictado aparece en un tono más tenue hasta cerrarse.
- Párrafos corregidos con un indicador discreto; al pasar el ratón o hacer clic: ver cambios / revertir / volver a corregir.
- Atajos: `F9` dictar/pausa, `Ctrl+Enter` nuevo párrafo, `Ctrl+S`, `Ctrl+O`.
- Selector de micrófono en Ajustes.
- Tema claro/oscuro según el sistema.

---

## 11. Modelos y primer arranque

- Carpeta de modelos en `%LOCALAPPDATA%\Dictado\models` (configurable).
- Primer arranque: asistente que descarga Parakeet v3 (ONNX int8) y Silero VAD con barra de progreso y verificación de integridad.
- El GGUF del LLM no se descarga por defecto (se asume llama-swap/Ollama); en el modo gestionado sí se ofrece la descarga.

---

## 12. Fases

1. **Núcleo de dictado:** captura + VAD + Parakeet → texto en el editor. Guardar/abrir `.dictado`. Sin LLM.
2. **Corrección:** cliente LLM, cola, presets de prosa, salvaguarda, revertir/ver cambios, ajustes del endpoint.
3. **Modos y comandos:** poesía y notas, glosario, comandos de voz, exportar a .md/.txt/.docx.
4. **Distribución:** asistente de descarga de modelos, `.exe` con PyInstaller y modo gestionado de llama-server (opcional).

## 13. Criterios de aceptación

- Dictar 5 minutos seguidos sin que la UI se congele ni se pierda audio.
- Latencia de transcripción por frase < 2 s en CPU en el equipo objetivo.
- Corrección de un párrafo de ~80 palabras < 15 s con Qwen3.5 2B en CPU.
- En modo Poesía nunca cambia el número de versos.
- Si el endpoint del LLM cae, el dictado sigue funcionando y los párrafos quedan en `raw`.
- Guardar, cerrar, abrir y continuar conserva el estado de todos los párrafos.

## 14. Instrucciones para Claude Code

- Trabaja por fases y deja cada una funcionando con `uv run dictado` antes de pasar a la siguiente.
- Antes de usar `onnx-asr`, Silero VAD o la API de llama-swap, comprueba su documentación actual; no asumas firmas de funciones.
- Escribe tests (`pytest`) para `guard.py`, `storage.py` y la lógica de segmentación del VAD (con audio sintético o grabado).
- Incluye un modo `--fake-asr` y un `--fake-llm` para probar la UI sin modelos.
- Interfaz y mensajes en español.
