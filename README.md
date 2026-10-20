# Dictador

Aplicación de escritorio para Windows 10/11 para **dictar por voz a un documento**, todo en local y sin conexión
(salvo la descarga inicial de modelos). Parakeet TDT 0.6B v3 transcribe frase a frase en la CPU y un LLM pequeño
corrige los párrafos ya cerrados mientras sigues hablando. La idea completa está en [SPEC.md](SPEC.md) y, como
antecedente, en [dictador.md](dictador.md).

Está pensado para una **persona mayor**: una hoja blanca como la de Word, letra grande, un botón grande para hablar
y nada más a la vista. Lo avanzado (ajustes, glosario, ver correcciones…) está en el botón **«Más»**.

## Instalación

Se reparte un único **`Instalar Dictador.exe`** (~64 MB): instala para el usuario sin pedir permisos de
administrador, pone el icono en el escritorio y en el menú Inicio y hace que los documentos `.dictador` se abran con
doble clic. Al abrir el programa por primera vez, un **asistente** con letra grande:

1. da la bienvenida;
2. descarga lo necesario (voz y corrector, ~2 GB) con una sola barra de progreso;
3. prueba el micrófono («Diga: Hoy hace un día precioso»);
4. explica el uso en tres pasos.

Se puede volver a ver la explicación en «Más › Ver la explicación otra vez» (o `F1`).

## Cómo funciona

```
Micrófono → Silero VAD → frases (pausa corta) → Parakeet → editor
                       → párrafo (pausa larga) → cola → LLM → salvaguarda → editor
```

- **Texto en vivo:** mientras hablas, lo que dices aparece en cursiva gris al final del documento (se re-transcribe
  la frase en curso cada ~0,4 s). No hace falta esperar a ninguna pausa para verlo.
- **Pausa corta** (0,8 s): cierra la frase, que queda fija en el párrafo.
- **Pausa larga** (2,5 s), «punto y aparte» o `Ctrl+Intro`: cierra el párrafo y lo manda al corrector. La marca del
  margen cambia de color: azul = corrigiendo, verde = corregido, naranja = corrección descartada, morado = editado.
- **Poesía:** pausas propias, más cortas: 0,35 s cierra el verso (cada uno en su línea) y 1,3 s la estrofa. Si dos
  versos llegan juntos, se separan por la puntuación que pone Parakeet.
- Cada párrafo guarda el **texto original y el corregido**. Clic en la marca del margen (o botón derecho):
  ver cambios, revertir al original, volver a corregir.
- Si editas un párrafo a mano, el corrector ya no lo toca.
- **Modos:** Prosa, Poesía, Notas/Lista y Sin corrección.
- **Comandos de voz:** «punto y aparte», «nuevo párrafo», «nueva estrofa», «borra la última frase», «título …».
- **Glosario** general (Ajustes) y por documento (Documento › Glosario) para nombres propios y vocabulario raro.

## El corrector

En **Herramientas › Ajustes › Corrector** se elige:

- **Integrado:** Qwen3.5 2B con llama-server, en la **CPU** (RAM) o en la **GPU** (Vulkan). Los dos se descargan desde
  **Herramientas › Modelos** (≈1,3 GB) y Dictador arranca y para el servidor solo. Medido en un Ryzen 7 7800X3D:
  un párrafo de 63 palabras en ~2 s en CPU.
- **Servidor externo:** cualquier endpoint compatible con OpenAI (Ollama, llama-swap, llama-server, LM Studio),
  local o en otro equipo, con URL, modelo y clave. Ver [docs/LLM.md](docs/LLM.md).

**Titubeos:** al dictar uno se corrige sobre la marcha («dejaban su paso a su paso», «a las ocho, no, a las nueve»).
Lo que vale es lo último que se dijo. Los casos claros (repeticiones sin coma, autocorrecciones con otra forma de la
palabra, correcciones con «no», «eh», «digo»… en medio, muletillas sueltas) se arreglan por reglas antes de llamar al
corrector, porque los modelos pequeños suelen borrar la versión buena en vez de la descartada. Las repeticiones
idénticas con coma («que no, que no») pueden ser expresivas y se dejan a juicio del corrector. En poesía no se toca
nada de esto. El texto original de Parakeet se guarda siempre: «Revertir» lo recupera.

Una **salvaguarda** rechaza las correcciones que cambian demasiado el texto (distancia de edición, longitud, número de
versos) y limpia los preámbulos típicos («Aquí tienes…»). Si el corrector falla o no responde, el dictado sigue y el
párrafo se queda con el texto de Parakeet; Documento › Reintentar lo vuelve a intentar.

## ¿Y los párrafos sin pausas?

Se probó a que el corrector decidiera dónde empieza cada párrafo (frase a frase, con el inicio del Quijote y sus
párrafos reales). Qwen3.5 2B no separó ninguno; Qwen3.5 4B, uno de tres; y la probabilidad que dan a «párrafo nuevo»
no distingue los saltos reales del resto. Con modelos pequeños no es fiable, así que los párrafos salen de la voz:
pausa larga (ajustable), «punto y aparte» o `Ctrl+Intro`.

## Diagnóstico

Ajustes › Dictado › «Guardar el audio de cada sesión» graba el audio y la probabilidad de voz de cada trama en
`%LOCALAPPDATA%\Dictador\diagnostico`. Con `dictador --transcribe sesion.wav` se puede repetir el corte y la
transcripción sin micrófono.

## Archivos

- Documento `.dictador` (JSON): todos los párrafos con original, corrección y estado. Al reabrirlo, el dictado sigue al
  final.
- Exportar a `.docx`, `.md` y `.txt`; importar `.txt` y `.md`.
- Autoguardado de recuperación cada 60 s.
- Modelos en `%LOCALAPPDATA%\Dictador\models`; ajustes en `%APPDATA%\Dictador\config.json`.

## Atajos

| Atajo | Acción |
|---|---|
| `F9` | Empezar / parar de hablar |
| `Ctrl+Intro` | Nuevo párrafo |
| `Ctrl+N` / `Ctrl+O` / `Ctrl+S` | Nuevo / abrir / guardar |
| `Ctrl+E` | Guardar como documento de Word |
| `Ctrl+P` | Imprimir |
| `Ctrl++` / `Ctrl+-` | Letra más grande / más pequeña |
| `F1` | Ver la explicación otra vez |
| `Ctrl+,` | Ajustes |

## Desarrollo

```sh
uv sync
uv run dictador                          # la app
uv run dictador --fake-asr --fake-llm    # sin micrófono, modelos ni LLM
uv run dictador --transcribe audio.wav   # diagnóstico: VAD + Parakeet sobre un .wav de 16 kHz mono
uv run pytest                           # tests
```

## Generar el instalador

```sh
uv run python installer/build.py
```

Hace `dist/Dictador/` con PyInstaller (sin modelos) y lo empaqueta con Inno Setup 6
(`winget install JRSoftware.InnoSetup`) en `dist/Instalar Dictador.exe`. El script del instalador está en
[installer/dictador.iss](installer/dictador.iss).

## Licencias de los modelos

Parakeet TDT 0.6B v3 (NVIDIA, CC-BY-4.0, versión ONNX de istupakov), Silero VAD (MIT), Qwen3.5 2B (Apache-2.0,
GGUF de unsloth), llama.cpp (MIT).
