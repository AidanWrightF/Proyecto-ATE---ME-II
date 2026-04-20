# Test Executive — RIGOL DS1202Z-E

Aplicación de test automatizado para Medidas Electrónicas II.  
Ejecuta programas de test definidos en CSV, controla un osciloscopio RIGOL DS1202Z-E vía VISA y muestra los resultados en tiempo real.

## Requisitos

- **Python 3.10+** con `tkinter` incluido (en Linux: `sudo apt install python3-tk`)
- **Backend VISA** (elegir uno):
  - NI-VISA: drivers del sistema de National Instruments (no se instala con pip)
  - `pyvisa-py`: backend puro-Python incluido en `requirements.txt`

```bash
pip install -r requirements.txt
```

## Uso

```bash
# Desde el directorio Code_TE/
python -m ate
```

O, si el paquete está instalado:

```bash
ate
```

## Configuración del instrumento

Editar `ate/config.py` para ajustar el recurso VISA del osciloscopio:

```python
RIGOL_SCOPE_RESOURCE = "USB0::0x1AB1::0x0517::DS1ZE243207925::INSTR"
```

## Formato del Test Program (CSV)

Los archivos CSV se guardan en `programs_tp/examples/`.  
Cada archivo puede tener encabezados de metadatos (líneas que comienzan con `#`) y luego las columnas de la secuencia:

```
# TP_NAME: Nombre del test
# TP_VERSION: 1.0
line,name,command,arg1,arg2,arg3,arg4,low,high,unit
10,Reset inicial,RESET,,,,,,,
20,Autoscale,OSC_AUTOSCALE,,,,,,,
30,Medir VPP,OSC_MEASURE,VPP,CHAN1,VPP_REG,,0.5,5.0,V
40,Fin,END,,,,,,,
```

### Comandos disponibles

| Comando | Descripción | arg1 | arg2 | arg3 | arg4 |
|---|---|---|---|---|---|
| `RESET` | Reinicia osciloscopio y registros | — | — | — | — |
| `LOAD` | Carga valor en registro | registro | valor | — | — |
| `SUM` | Suma dos valores → registro | op1 | op2 | dest | — |
| `COMP` | Resta dos valores → registro | op1 | op2 | dest | — |
| `IF` | Salto condicional | op1 | operador | op2 | línea destino |
| `JMP` | Salto incondicional | línea destino | — | — | — |
| `TXT` | Confirmación manual del operario | mensaje | — | — | — |
| `WAIT` | Espera en segundos | segundos | — | — | — |
| `OSC_AUTOSCALE` | Autoscale del osciloscopio | — | — | — | — |
| `OSC_MEASURE` | Medición del osciloscopio | tipo | canal | registro | — |
| `LOG` | Imprime mensaje en la consola | mensaje | — | — | — |
| `END` | Finaliza el programa | — | — | — | — |

**Tipos de medición** (`OSC_MEASURE`): `VPP`, `FREQ`, `RISE`, `FALL`, `PWIDTH`, `PERIOD`, `VMAX`, `VMIN`  
**Operadores** (`IF`): `==`, `!=`, `>`, `<`, `>=`, `<=`

## Estructura del proyecto

```
Code_TE/
├── ate/
│   ├── config.py          # Constantes de hardware y PROJECT_ROOT
│   ├── main.py            # Punto de entrada
│   ├── ui/
│   │   └── operator_app.py
│   ├── engine/
│   │   ├── models.py      # Clases de datos y excepciones
│   │   ├── loader.py      # Parser de CSV
│   │   ├── runtime.py     # Motor de ejecución
│   │   └── commands.py    # Implementación de comandos
│   └── instruments/
│       ├── visa.py        # Comunicación VISA
│       ├── rigol_scope.py # Driver del osciloscopio
│       └── factory.py     # Inicialización de instrumentos
└── programs_tp/
    └── examples/          # Programas de test de ejemplo
```
