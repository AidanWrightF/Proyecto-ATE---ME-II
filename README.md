# Test Executive — RIGOL DS1202Z-E + DG1022Z

Aplicación de test automatizado para Medidas Electrónicas II (UTN FRN).
Ejecuta programas de test (TP) escritos en CSV, controla un osciloscopio RIGOL DS1202Z-E y un
generador de funciones RIGOL DG1022Z vía VISA (cada uno por su propio cable USB) y entrega los
resultados en un reporte de texto listo para imprimir.

La interfaz del operario es deliberadamente mínima: un **selector de Test Program**, el botón
**START** y una **barra de progreso** que termina **verde (PASS)** o **roja (FAIL)**. El operario no
pausa ni reinicia la secuencia: eso lo decide el propio TP (p. ej. con `END`). Los mensajes y
errores van a la **consola**; el detalle de cada paso queda en el **reporte**, que se abre solo al terminar.

## Requisitos

- **Python 3.10+** con `tkinter` (en Linux: `sudo apt install python3-tk`)
- **Backend VISA** (uno de los dos):
  - NI-VISA: drivers de National Instruments (no se instala con pip)
  - `pyvisa-py`: backend en Python puro, incluido en `requirements.txt`

```bash
pip install -r requirements.txt
```

## Uso

```bash
# Desde la carpeta Code_TE/
python -m ate
```

Elegir un TP del desplegable y presionar **START**. Al finalizar se abre el reporte `.txt`
(guardado en `reportes/`) con el resultado y el detalle de cada paso. Las capturas de pantalla
que tome el TP (`OSC_SCREENSHOT`) se guardan como `.png` en la misma carpeta y se listan en el reporte.

Programas incluidos en `programas_tp/`:

- `tp_generador_1khz.csv`: verificación del generador DG1022Z según su manual. Configura por VISA
  una cuadrada de 1 kHz, 3 Vpp y 1,5 V de offset, la mide con el osciloscopio (cable BNC–BNC al CH1,
  sin sonda) y aprueba si frecuencia, ciclo de trabajo, amplitud, offset, flancos y sobrepico están
  dentro de la especificación del manual más la incertidumbre del osciloscopio.
- `tp_rigol_ch1_comp.csv`: prueba rápida con la señal de compensación del osciloscopio.
- `tp_oscilador_1khz.csv`: caracterización completa de un oscilador de onda cuadrada de 1 kHz
  (frecuencia, estabilidad, ciclo de trabajo, niveles, amplitud, sobrepico y flancos). Para otro
  oscilador alcanza con cambiar `F_NOM`, `V_NOM` y `T_FLANCO_MAX` en las primeras líneas.

## Configuración

En `ate/config.py` se ajustan los recursos VISA de los instrumentos, la identificación de la
estación y el tiempo que se acumula estadística en `OSC_MEASURE_STAT`:

```python
RECURSO_OSCILOSCOPIO = "USB0::0x1AB1::0x0517::DS1ZE243207925::INSTR"
RECURSO_GENERADOR = ""   # vacío: el primer DG1000Z (VID 0x1AB1, PID 0x0642) conectado por USB
ESTACION = "ATE-UNI-01"
SEGUNDOS_ESTADISTICA = 3
```

El generador se abre sólo si el TP usa alguna instrucción `GEN_`; los TP que no lo usan funcionan
con el generador apagado o desconectado. Al terminar cualquier prueba (PASS, FAIL o ABORTADO) el TE
apaga las dos salidas del generador.

## Formato del Test Program (CSV)

Los TP se guardan en `programas_tp/`. Primero van los metadatos (renglones que empiezan con `#`)
y después la tabla de pasos:

```
# TP_NAME: Nombre del test
# TP_VERSION: 1.0
line,name,command,arg1,arg2,arg3,arg4,low,high,unit
10,Reset inicial,RESET,,,,,,,
20,Autoscale,OSC_AUTOSCALE,,,,,,,
30,Medir VPP,OSC_MEASURE,VPP,CHAN1,REG_VPP,,0.5,5.0,V
40,Fin,END,,,,,,,
```

Los pasos se ejecutan en orden de `line`. Si un paso devuelve un valor (mediciones y cálculos)
y tiene `low`/`high`, el valor se compara con esos límites: fuera de rango, la prueba termina en FAIL.
Los argumentos y límites pueden ser números o nombres de registro. Si se omite el canal, se usa CH1.

### Comandos

**Registros y cálculos**

| Comando | Descripción | arg1 | arg2 | arg3 | arg4 |
|---|---|---|---|---|---|
| `RESET` | Reinicia el osciloscopio (y el generador, si el TP lo usa) y borra los registros | — | — | — | — |
| `LOAD` | Guarda un valor en un registro | registro | valor | — | — |
| `SUM` | Suma (op1 + op2) | op1 | op2 | destino | — |
| `COMP` | Resta (op1 − op2) | op1 | op2 | destino | — |
| `MUL` | Multiplica (op1 × op2) | op1 | op2 | destino | — |
| `DIV` | Divide (op1 ÷ op2); dividir por cero da FAIL | op1 | op2 | destino | — |

**Control del programa**

| Comando | Descripción | arg1 | arg2 | arg3 | arg4 |
|---|---|---|---|---|---|
| `IF` | Salta si se cumple la condición | op1 | operador | op2 | línea destino |
| `JMP` | Salto incondicional | línea destino | — | — | — |
| `TXT` | Pide una confirmación al operario (Cancelar → ABORTADO) | mensaje | — | — | — |
| `WAIT` | Espera | segundos | — | — | — |
| `LOG` | Escribe un mensaje en la consola | mensaje | — | — | — |
| `END` | Termina el programa | — | — | — | — |

**Osciloscopio: configuración**

| Comando | Descripción | arg1 | arg2 |
|---|---|---|---|
| `OSC_AUTOSCALE` | Autoscale | — | — |
| `OSC_PROBE` | Atenuación de la sonda configurada en el canal | canal | 1, 10, 100… |
| `OSC_COUPLING` | Acoplamiento | canal | `DC`, `AC` o `GND` |
| `OSC_BWLIMIT` | Límite de banda de 20 MHz | canal | `ON` u `OFF` |
| `OSC_VSCALE` | Escala vertical | canal | V/div |
| `OSC_VOFFSET` | Offset vertical | canal | V |
| `OSC_TIMESCALE` | Base de tiempo | s/div | — |
| `OSC_TIMEOFFSET` | Posición horizontal del disparo | s | — |
| `OSC_TRIG_SOURCE` | Fuente del disparo por flanco | canal | — |
| `OSC_TRIG_LEVEL` | Nivel de disparo | V | — |
| `OSC_SLOPE` | Flanco de disparo: `POS`, `NEG` o `RFAL` | flanco | — |
| `OSC_ACQUIRE` | Tipo de adquisición: `NORMAL`, `AVERAGE`, `PEAK` o `HRES` | tipo | promedios (2, 4… 1024) |

**Osciloscopio: adquisición, mediciones y diagnóstico**

| Comando | Descripción | arg1 | arg2 | arg3 | arg4 |
|---|---|---|---|---|---|
| `OSC_RUN` / `OSC_STOP` | Inicia / congela la adquisición | — | — | — | — |
| `OSC_SINGLE` | Captura una sola adquisición | — | — | — | — |
| `OSC_MEASURE` | Mide y guarda el valor en un registro | tipo | canal | registro | — |
| `OSC_MEASURE_STAT` | Estadístico de una medición durante `SEGUNDOS_ESTADISTICA` (requiere `OSC_RUN`) | tipo | canal | registro | `AVG`, `DEV`, `MIN`, `MAX` o `CUR` |
| `OSC_CHECK_ERRORS` | Lee la cola de errores (`:SYSTem:ERRor?`); si el equipo rechazó algún comando, da FAIL | — | — | — | — |
| `OSC_SCREENSHOT` | Guarda una captura PNG de la pantalla en `reportes/` | — | — | — | — |

**Generador de funciones** (canal: `CH1` o `CH2`; vacío = `CH1`)

| Comando | Descripción | arg1 | arg2 | arg3 | arg4 |
|---|---|---|---|---|---|
| `GEN_APPLY` | Forma, frecuencia, amplitud y offset del CH1 en un solo paso (`:SOURce1:APPLy`) | `SIN`, `SQU`, `RAMP`, `PULSE`, `NOISE` o `DC` | Hz | Vpp | offset en V (def. 0) |
| `GEN_FUNC` | Cambia sólo la forma de onda | canal | forma | — | — |
| `GEN_FREQ` | Cambia sólo la frecuencia | canal | Hz | — | — |
| `GEN_AMPL` | Cambia sólo la amplitud | canal | Vpp | — | — |
| `GEN_OFFSET` | Cambia sólo el offset | canal | V | — | — |
| `GEN_DUTY` | Ciclo de trabajo de la cuadrada | canal | % | — | — |
| `GEN_LOAD` | Carga que supone el generador: `INF` (alta impedancia, def.) o 1 a 10000 Ω | canal | carga | — | — |
| `GEN_OUTPUT` | Enciende o apaga la salida | canal | `ON` u `OFF` | — | — |
| `GEN_READ` | Lee cómo quedó configurado el canal (el equipo recorta sin error lo que está fuera de rango); admite `low`/`high` | canal | `FREQ`, `AMPL`, `OFFSET` o `DUTY` | registro (def. `GEN_`*param*) | — |
| `GEN_CHECK_ERRORS` | Lee la cola de errores del generador; si rechazó algún comando, da FAIL | — | — | — | — |

Con el osciloscopio (entrada de 1 MΩ) usar `GEN_LOAD CH1 INF`: con la carga de fábrica (50 Ω) la
tensión medida es casi el doble de la programada.

**Operadores** (`IF`): `==`, `!=`, `>`, `<`, `>=`, `<=`

### Mediciones (`OSC_MEASURE`)

| Tipo | Qué mide |
|---|---|
| `VPP` | Tensión pico a pico |
| `VMAX` / `VMIN` | Tensión máxima / mínima |
| `VTOP` / `VBASE` | Nivel alto / bajo estable de la señal (ignora sobrepicos) |
| `VAMP` | Amplitud = `VTOP` − `VBASE`; más correcta que `VPP` en señales rectangulares |
| `VAVG` / `VRMS` | Valor medio / valor eficaz |
| `OVERSHOOT` / `PRESHOOT` | Sobrepico / presubida en los flancos |
| `FREQ` | Frecuencia calculada sobre la forma de onda en pantalla |
| `FREQ_CNT` | Frecuencia medida con el contador por hardware (más precisa; no admite estadística) |
| `PERIOD` | Período |
| `PWIDTH` | Ancho del pulso positivo |
| `PDUTY` | Ciclo de trabajo positivo |
| `RISE` / `FALL` | Tiempo de subida / bajada (10 % – 90 %) |

Los comandos SCPI del osciloscopio corresponden a la *DS1000Z Programming Guide* de RIGOL (serie del
DS1202Z-E), y los del generador a la *DG1000Z Programming Guide* (serie del DG1022Z; la guía del
DG1022 sin Z es de otra serie y usa otra sintaxis).
`PDUTY`, `OVERSHOOT` y `PRESHOOT` se registran tal como los devuelve el osciloscopio; antes de
ponerles límites conviene verificar en el equipo si los expresa como fracción (0,5) o en % (50).

## Cómo funciona

```
interfaz.py        el operario elige el TP y presiona START
   │
programa.py        cargar_programa() lee el CSV y lo convierte en una lista de Paso
   │
motor.py           Motor.ejecutar() conecta el osciloscopio (y el generador si el TP usa GEN_)
   │                 y recorre los pasos (registros, saltos IF/JMP, verificación de límites)
comandos.py        COMANDOS["OSC_MEASURE"] → medir(motor, paso), etc.
   │
osciloscopio.py    traducen cada acción a comandos SCPI; los dos heredan de
generador.py       instrumento.py (*IDN?, *OPC?, *RST y cola de errores), que habla por VISA
   │
reporte.py         guardar_reporte() escribe el .txt; la barra se pinta verde o roja
```

La prueba corre en un hilo aparte para que la ventana no se congele. Como tkinter no es
thread-safe, ese hilo no toca la ventana: deja funciones en una cola que la interfaz
ejecuta cada 100 ms.

## Estructura del proyecto

```
Code_TE/
├── ate/
│   ├── __main__.py      # Punto de entrada (python -m ate)
│   ├── config.py        # Rutas, estación y recursos VISA
│   ├── interfaz.py      # Ventana del operario
│   ├── programa.py      # Lectura del CSV
│   ├── motor.py         # Ejecución del TP
│   ├── comandos.py      # Una función por comando del TP
│   ├── instrumento.py   # Base común de los drivers (VISA + SCPI)
│   ├── osciloscopio.py  # Driver del RIGOL DS1202Z-E
│   ├── generador.py     # Driver del RIGOL DG1022Z
│   ├── reporte.py       # Reporte de texto
│   └── logo.png
├── programas_tp/        # Test Programs (.csv)
├── reportes/            # Reportes generados (ignorado por git)
└── requirements.txt
```
