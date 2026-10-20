# Configurar el corrector (LLM)

Dictador habla con cualquier servidor compatible con la API de OpenAI, en el mismo equipo o en otro de la red.
Se configura en **Herramientas › Ajustes › Corrector (LLM)**: URL base, modelo y clave API (opcional).
«Probar conexión» rellena la lista de modelos desde `/v1/models`.

| Servidor | URL base típica | Modelo |
|---|---|---|
| llama-swap | `http://localhost:8080/v1` | el nombre de la entrada (`corrector-cpu`, `corrector-gpu`) |
| llama-server | `http://localhost:8080/v1` | cualquiera (sirve un solo modelo) |
| Ollama | `http://localhost:11434/v1` | `qwen3.5-4b:latest`, etc. |
| LM Studio | `http://localhost:1234/v1` | el identificador que muestra LM Studio |

Para un servidor en otro equipo basta con cambiar `localhost` por su IP (y abrir el puerto en ese equipo;
Ollama necesita `OLLAMA_HOST=0.0.0.0` para escuchar fuera de localhost).

## Razonamiento («thinking»)

Con «Desactivar el razonamiento» marcado, cada petición lleva `reasoning_effort: "none"` (lo que entiende
Ollama) y `chat_template_kwargs: {"enable_thinking": false}` (llama-server). Si el servidor rechaza esos campos,
Dictador reintenta sin ellos y añade `/no_think` al prompt. Medido con Ollama y `qwen3.5-4b`: sin desactivarlo, el
modelo gasta todos los tokens razonando y no devuelve texto; desactivado, un párrafo de ~60 palabras tarda
menos de un segundo en una RTX 4070 Super.

## Modelos recomendados

- Equipo modesto (CPU o GPU antigua): **Qwen3.5 2B** Q4_K_M; alternativas Gemma 3n E2B / Gemma 3 1B.
- Si hay margen: Qwen3.5 4B.

Los modelos pequeños tienden a «mejorar» el texto por su cuenta; la salvaguarda rechaza las correcciones que
cambian demasiado (umbrales en Ajustes) y el párrafo se queda con el texto de Parakeet.

Ejemplo de llama-swap con una entrada CPU y otra GPU: [llama-swap.yaml](llama-swap.yaml).
