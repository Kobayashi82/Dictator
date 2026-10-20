# Dictador

App de dictado local que muestra el texto **ya arreglado** según se va hablando.

- **Estado:** pendiente de empezar
- **Fecha del diseño:** 07/09/2026
- **Máquina:** PADRE (Ryzen 7 7800X3D · RTX 4070 Super 12 GB · 64 GB DDR5)
- **Relación con Voice Assistant:** proyecto aparte, no una ampliación

---

## 1. Objetivo

Poder leer en voz alta un libro o un cuaderno manuscrito y obtener texto bien
formateado: párrafos, puntuación, comillas de diálogo, nombres propios
correctos y sin titubeos.

El requisito que define la arquitectura: **el texto limpio se ve en vivo**, no
al final.

---

## 2. Principio de diseño: dos pasadas

Lo que separa una transcripción "decente" de una "bien bien hecha" no es el
modelo de ASR. Ningún ASR da párrafos, comillas de diálogo y limpieza de
titubeos por sí solo. Eso lo pone un LLM encima.

```
audio → VAD → ASR (crudo) → LLM (limpieza) → texto final
```

Con la 4070 Super hay margen de sobra para las dos etapas a la vez.

---

## 3. Pasada 1 — ASR

### Candidatos (los tres caben en 12 GB de VRAM)

| Modelo | Idiomas | WER (Open ASR) | Notas |
|---|---|---|---|
| **Parakeet TDT 0.6B v3** | 25 europeos, incl. español | 6,32 % | Puntuación y mayúsculas nativas; RTFx ~3.333x |
| Whisper large-v3 (faster-whisper) | 99 | 7,44 % | Mejor con acentos y vocabulario técnico |
| Qwen3-ASR 1.7B | 52 | ~2-3 % (est.) | Apache 2.0; líder en multilingüe 2026 |

### Elección: Parakeet v3 como principal

Razones:

- Al ser **transducer**, emite blancos en el silencio → prácticamente no
  alucina. Justo el fallo de Whisper cuando haces pausas para pasar página.
- Trae puntuación y mayúsculas de fábrica, lo que aligera el trabajo del LLM.
- Velocidad absurda: a ~3.333x tiempo real, el ASR es esencialmente gratis
  dentro del presupuesto de latencia.
- Licencia CC-BY-4.0, runtime NeMo. Lanzado en agosto de 2025.

Whisper large-v3 queda como **segunda opinión** para fragmentos donde el texto
salga raro. Necesita VAD delante sí o sí (bucles y alucinaciones en silencio).

> ⚠️ **Comprobar la versión instalada.** Parakeet **v2 era solo inglés**;
> la v3 es la que cubre español. Si lo que hay en PADRE es la v2, no sirve
> para esto.

---

## 4. Pasada 2 — Limpieza con LLM

### Prompt base

> Restaura puntuación y párrafos. Respeta el estilo del original. No
> reescribas ni resumas. Corrige solo errores evidentes de transcripción.
> Marca con `[?]` lo que no entiendas.

### Modelo

Qwen 3.5 4B (llama.cpp, 128k contexto) sirve, pero **un 4B tiende a "mejorar"
el texto por su cuenta**, que es exactamente lo que no queremos para prosa de
libro. Decisión pendiente: probar con algo más grande si hay hueco.

### Troceado

Por párrafos, con solape de una o dos frases, para que no pierda el hilo entre
chunks.

---

## 5. UI en vivo: las dos zonas

La restricción física que condiciona todo: **no se puede limpiar una frase que
aún no has terminado de decir**. Solución estándar:

- **Zona caliente** (abajo, gris o cursiva) — salida cruda del ASR en
  streaming, palabra a palabra, sin puntuar. Es el feedback de "te estoy
  oyendo".
- **Zona fría** (arriba, texto normal) — lo ya consolidado y pasado por el
  LLM. Puntuado, con párrafos, con los nombres bien.

El texto sube de una zona a otra con uno o dos segundos de retraso. Ves
aparecer lo que dices al instante y detrás va "cuajando" solo.

### Cuándo disparar la limpieza

El VAD marca el corte: silencio de **~800 ms** cierra un segmento. Pero no se
manda cada segmento suelto al LLM — hay que **acumular dos o tres frases**,
porque para puntuar bien necesita ver dónde acaba la idea. Un segmento de
cinco palabras no se puede puntuar sin contexto.

Al LLM se le manda **el último párrafo ya limpio + el trozo crudo nuevo**, y se
le pide que devuelva solo la parte nueva. Así mantiene coherencia de estilo y
sabe si venías a mitad de frase.

### El problema del parpadeo

Es el detalle que hace que se sienta pulido o cutre. Si el LLM reescribe texto
que ya estás leyendo, la pantalla baila y marea.

**Regla: congelar todo lo que esté a más de un bloque de distancia.** Solo el
último bloque consolidado es reescribible; lo anterior es inmutable. Si el LLM
quiere retocar algo de más atrás, se ignora.

---

## 6. Presupuesto de latencia

- **ASR**: gratis (~3.333x tiempo real).
- **Cuello de botella**: el LLM. Un párrafo de 60 palabras en la 4070 Super
  sale en bastante menos de un segundo.

Trucos:

- Temperatura a 0.
- Streaming de tokens, para que el texto limpio aparezca progresivamente en
  vez de dar un salto.
- System prompt fijo → llama.cpp cachea el prefill.
- **ASR y LLM en colas separadas.** Si el LLM se atasca, el ASR debe seguir
  alimentando la zona caliente sin bloquearse.

---

## 7. Stack

| Capa | Elección |
|---|---|
| Backend | FastAPI + WebSocket |
| VAD | Silero |
| ASR | Parakeet v3 (NeMo) o sherpa-onnx |
| LLM | llama.cpp + Qwen 3.5 4B |
| Frontend | React + Vite (o Tauri si se quiere overlay flotante) |

**Nota sobre sherpa-onnx:** tiene VAD y ASR en una sola librería con bindings
de Python, y ahorra las dependencias de NVIDIA/NeMo.

### Protocolo WebSocket

Audio en chunks hacia dentro, eventos hacia fuera:

| Evento | Contenido |
|---|---|
| `partial` | cola cruda (zona caliente) |
| `commit` | segmento cerrado + id |
| `clean` | id + texto que lo sustituye |

El frontend solo aplica parches por id. Simple y a prueba de desorden.

---

## 8. Decisión que se agradecerá: guardar las dos pistas

Conservar **crudo y limpio** con los ids enlazados. Para transcribir un libro
la fidelidad importa, y si el LLM "arregla" algo que en realidad estaba bien,
hay que poder ver el original con un clic.

- Toggle raw/clean en la UI.
- Exportación que incluya ambos.

Media hora de trabajo extra que salva de desconfiar del resultado.

---

## 9. Orden de arranque

1. **VAD + ASR escupiendo a consola. Sin UI ninguna.** Si esto va fino, el
   resto es fácil.
2. WebSocket + las dos zonas.
3. Limpieza con LLM y parcheo por id.
4. Congelado de bloques y anti-parpadeo.
5. Persistencia de las dos pistas y exportación.

---

## 10. Pendientes

- [ ] Verificar si el Parakeet instalado es v2 (solo inglés) o v3 (español).
- [ ] Decidir el LLM de limpieza — Qwen 3.5 4B puede ser demasiado "creativo".
- [ ] Probar micro decente. Leer a ritmo natural, **sin sobrearticular**: los
      ASR modernos se entrenan con habla natural y empeoran si vocalizas raro.
- [ ] Implementar `initial_prompt` (Whisper) / hotwords (Parakeet) por sesión.

### Truco que más nota se lleva

Antes de empezar cada sesión, meter en el `initial_prompt` / hotwords el
**título del libro, el autor, los nombres de personajes y el vocabulario raro**
que vaya a salir. La diferencia en nombres propios es brutal y cuesta treinta
segundos de preparación.

---

## 11. Referencias

Herramientas ya hechas, por si sirven de referencia de implementación:

- **Handy** — Tauri + Rust, whisper-rs y transcribe-rs (Parakeet), hotkey
  global, VAD integrado. <https://github.com/cjpais/Handy>
- **WhisperWriter** — Python/PyQt5, modo continuo que para al detectar pausa
  larga y vuelve a grabar solo.
- **sherpa-onnx** — <https://github.com/k2-fsa/sherpa-onnx>

---

## Apéndice: ¿y si el libro es impreso?

Leerlo en voz alta es el camino largo. Una foto por página con Qwen 3.5 4B
(tiene visión) da mejor resultado, en menos tiempo y sin errores de homófonos.

La lectura en voz alta merece la pena sobre todo para el **cuaderno
manuscrito**, donde la letra a mano sigue siendo dura hasta para los VLM
buenos. Aun así, conviene probar primero con una foto antes de ponerse a
dictar cincuenta páginas.
