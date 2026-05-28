# SQL Validator Agent

Agente LangGraph con interfaz Streamlit para validar queries SQL contra un conjunto de reglas y sugerir correcciones usando Gemini.

## Arquitectura

```
rules.py      — Reglas de validación (funciones puras, testeables)
graph.py      — Grafo LangGraph (nodos + edges + checkpointer)
app.py        — UI Streamlit (maneja el ciclo interrupt/resume)
```

## Flujo del grafo

```
START
  |
  v
validate_sql          <- corre todas las reglas sobre la query
  |
  |-- todas pasaron? --> END
  |
  v
suggest_fix           <- llama a Gemini para sugerir corrección
  |                   <- INTERRUPT: pausa y muestra la sugerencia al usuario
  |
  |-- usuario acepta / edita / skip
  |
  v
validate_sql          <- re-valida la query corregida
  ...                 <- puede iterar hasta 5 veces
```

## Por qué `interrupt()`

`interrupt()` de LangGraph pausa la ejecución del grafo en un nodo y serializa el estado completo en el checkpointer (en este caso `MemorySaver`, en producción sería Redis o Postgres). El grafo se puede retomar desde cualquier punto enviando `Command(resume=valor)`, lo que permite loops human-in-the-loop sin perder contexto.

## Setup

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=tu_clave_aqui
streamlit run app.py
```

## Reglas implementadas

| Regla | Descripción |
|---|---|
| No SELECT * | Obliga a especificar columnas |
| WHERE en DELETE/UPDATE | Evita borrar/actualizar toda la tabla |
| Sin JOINs implícitos | Requiere JOIN ... ON explícito |
| Aliases descriptivos | Prohíbe alias de una sola letra |
| Sin OR en JOIN | Evita productos cartesianos accidentales |

## Extender con nuevas reglas

Agregar una función en `rules.py` con la firma:

```python
def rule_mi_regla(query: str) -> tuple[bool, str]:
    ...
    return passed, message
```

Y registrarla en `ALL_RULES`. El agente la tomará automáticamente.