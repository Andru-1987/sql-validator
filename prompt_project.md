Quiero que construyas un proyecto Python llamado **sql-validator** compuesto por tres archivos: `rules.py`, `graph.py` y `app.py`, más `requirements.txt`.

**Contexto y objetivo**
Es un agente que valida queries SQL contra un conjunto de reglas predefinidas y, cuando encuentra violaciones, llama a un LLM para sugerir una versión corregida. El usuario puede aceptar la sugerencia, editarla manualmente, o ignorarla. El ciclo puede repetirse hasta 5 veces.

**Stack**
- LangGraph como framework del agente, con `MemorySaver` como checkpointer
- `ChatCohere` con modelo `command-r-plus` como LLM, usando `langchain-cohere`
- `python-dotenv` para leer `COHERE_API_KEY` desde un archivo `.env`
- Streamlit como interfaz de usuario

---

**`rules.py`**
Cinco reglas de validación SQL, cada una como función pura con firma `(query: str) -> tuple[bool, str]`. Las reglas son: no usar `SELECT *`, exigir `WHERE` en `DELETE` y `UPDATE`, prohibir JOINs implícitos (dos tablas separadas por coma en el `FROM`), prohibir aliases de una sola letra, y prohibir `OR` en condiciones de `JOIN`. Todas se registran en una lista `ALL_RULES` de tuplas `(nombre, función)`.

**`graph.py`**
Un `StateGraph` de LangGraph con dos nodos y estado tipado con `TypedDict`.

El estado contiene: `query` (SQL actual), `original_query`, `results` (lista de resultados por regla), `violations` (solo las que fallaron), `suggestion` (texto del LLM), `iteration` (contador), `all_passed` (bool).

Nodo `validate_sql`: recorre `ALL_RULES` y popula `results`, `violations` y `all_passed`.

Nodo `suggest_fix`: arma un prompt con las violaciones y la query, llama a `ChatCohere`, y luego llama a `interrupt()` de LangGraph pasando un dict con `suggestion`, `violations` e `iteration`. Según el valor que retorne el `interrupt` (`"accept"`, `"skip"`, o un string con SQL editado), actualiza `query` y `all_passed`.

Edges condicionales: después de `validate_sql` va a `suggest_fix` o `END` según `all_passed`. Después de `suggest_fix` va a `validate_sql` o `END` según `all_passed` o si `iteration >= 5`.

El grafo se compila con el checkpointer y se exporta como `GRAPH`. `load_dotenv()` se llama al inicio del módulo. `cohere_api_key` se pasa explícitamente al constructor de `ChatCohere` leyéndolo de `os.environ`.

**`app.py`**
Interfaz Streamlit con layout de dos columnas: izquierda para input, derecha para resultados.

Manejo de estado en `st.session_state`: `thread_id` (UUID que persiste por sesión), `interrupted` (bool), `interrupt_payload` (dict del interrupt), `last_results`, `log` (lista de strings), `current_query`.

Flujo: al presionar "Validar" se resetea la sesión, se corre el grafo con `GRAPH.stream()` en modo `updates`, y se inspecciona `GRAPH.get_state(config)` para detectar si hay interrupt pendiente chequeando `task.interrupts` en `current_state.tasks`.

Si hay interrupt, se muestra la query sugerida en un `st.text_area` editable y tres botones: "Aceptar sugerencia" (resume con `"accept"`), "Usar mi version" (resume con el contenido del text area), "Ignorar y terminar" (resume con `"skip"`). Cada botón llama a `GRAPH.stream(Command(resume=valor), config)` y vuelve a inspeccionar el estado para detectar un nuevo interrupt o el fin.

Sidebar con log de nodos ejecutados y botón "Nueva sesión" que limpia el estado.

La query de ejemplo por defecto debe ser una con dos violaciones visibles: `SELECT *` y JOIN implícito.

**`requirements.txt`**
`langgraph>=0.2.0`, `langchain-cohere>=0.3.0`, `streamlit>=1.40.0`, `python-dotenv>=1.0.0`

---

**Restricciones de estilo**
Sin emojis. Sin over-engineering. Nombres descriptivos en snake_case. Sin clases innecesarias. Cada archivo con una sola responsabilidad.