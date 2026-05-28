"""
UI Streamlit para el agente validador de SQL.

Manejo del ciclo de vida del grafo con interrupt:
  1. Usuario envía query -> se corre el grafo hasta el primer interrupt
  2. Se muestra la sugerencia del LLM
  3. Usuario acepta / edita / skip -> se resume el grafo con Command(resume=...)
  4. El grafo corre hasta el siguiente interrupt o hasta END
"""

import uuid

import streamlit as st
from langgraph.types import Command

from graph import GRAPH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS_COLOR = "#2ecc71"
FAIL_COLOR = "#e74c3c"


def render_results(results: list[dict]) -> None:
    for r in results:
        icon = "OK" if r["passed"] else "FAIL"
        color = PASS_COLOR if r["passed"] else FAIL_COLOR
        st.markdown(
            f"<span style='color:{color}; font-weight:bold'>[{icon}]</span> "
            f"**{r['rule_name']}** — {r['message']}",
            unsafe_allow_html=True,
        )


def get_thread_id() -> str:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    return st.session_state.thread_id


def reset_session() -> None:
    for key in ["thread_id", "interrupted", "interrupt_payload", "last_results", "log"]:
        st.session_state.pop(key, None)


def append_log(msg: str) -> None:
    if "log" not in st.session_state:
        st.session_state.log = []
    st.session_state.log.append(msg)


def run_graph_until_interrupt_or_end(input_data: dict | Command, config: dict) -> dict | None:
    """
    Corre el grafo hasta que haga interrupt o llegue a END.
    Retorna el snapshot si hay interrupt, None si terminó.
    """
    if isinstance(input_data, Command):
        events = list(GRAPH.stream(input_data, config=config, stream_mode="updates"))
    else:
        events = list(GRAPH.stream(input_data, config=config, stream_mode="updates"))

    # Actualizar log con cada nodo ejecutado
    for event in events:
        for node_name in event:
            append_log(f"Nodo ejecutado: **{node_name}**")

    # Verificar si hay interrupt pendiente
    state = GRAPH.get_state(config)
    if state.next and "__interrupt__" in str(state.next):
        return state
    if state.tasks:
        # Hay interrupt si alguna task tiene interrupts
        for task in state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                return state
    return None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="SQL Validator Agent", layout="wide")
st.title("SQL Validator Agent")
st.caption("LangGraph + Gemini + Streamlit — Human in the Loop")

config = {"configurable": {"thread_id": get_thread_id()}}

# Sidebar: log de ejecución
with st.sidebar:
    st.subheader("Log de ejecución")
    if "log" in st.session_state:
        for entry in st.session_state.log:
            st.markdown(f"- {entry}")
    else:
        st.caption("El log aparecerá aquí durante la ejecución.")

    st.divider()
    if st.button("Nueva sesión"):
        reset_session()
        st.rerun()

# ---------------------------------------------------------------------------
# Panel principal
# ---------------------------------------------------------------------------

col_input, col_output = st.columns([1, 1], gap="large")

with col_input:
    st.subheader("Query SQL")

    default_query = (
        "SELECT * FROM orders o, customers c\n"
        "WHERE o.customer_id = c.id\n"
        "AND o.status = 'active'"
    )

    query_input = st.text_area(
        "Ingresa tu query:",
        value=st.session_state.get("current_query", default_query),
        height=200,
        key="query_input",
    )

    run_btn = st.button("Validar", type="primary", disabled=st.session_state.get("interrupted", False))

with col_output:
    st.subheader("Resultados")

    # -----------------------------------------------------------------------
    # Ejecución inicial
    # -----------------------------------------------------------------------
    if run_btn:
        reset_session()
        config = {"configurable": {"thread_id": get_thread_id()}}
        st.session_state.current_query = query_input
        append_log(f"Iniciando con thread `{config['configurable']['thread_id'][:8]}...`")

        initial_state = {
            "query": query_input,
            "original_query": query_input,
            "results": [],
            "violations": [],
            "suggestion": "",
            "iteration": 0,
            "all_passed": False,
        }

        state_snapshot = run_graph_until_interrupt_or_end(initial_state, config)

        current_state = GRAPH.get_state(config)
        st.session_state.last_results = current_state.values.get("results", [])

        if state_snapshot is not None:
            # Hay un interrupt — extraer el payload
            for task in current_state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    st.session_state.interrupted = True
                    st.session_state.interrupt_payload = task.interrupts[0].value
                    break
        else:
            st.session_state.interrupted = False

        st.rerun()

    # -----------------------------------------------------------------------
    # Mostrar resultados de validación
    # -----------------------------------------------------------------------
    if "last_results" in st.session_state:
        render_results(st.session_state.last_results)

    # -----------------------------------------------------------------------
    # Panel de interrupt (sugerencia del LLM)
    # -----------------------------------------------------------------------
    if st.session_state.get("interrupted") and st.session_state.get("interrupt_payload"):
        payload = st.session_state.interrupt_payload
        iteration = payload.get("iteration", 0)

        st.divider()
        st.subheader(f"Sugerencia del agente (iteracion {iteration + 1})")

        violations = payload.get("violations", [])
        if violations:
            st.markdown("**Violaciones detectadas:**")
            for v in violations:
                st.markdown(f"- [{v['rule_name']}] {v['message']}")

        st.markdown("**Query sugerida:**")
        edited_query = st.text_area(
            "Podés editar la query antes de aceptar:",
            value=payload.get("suggestion", ""),
            height=180,
            key="suggestion_editor",
        )

        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            if st.button("Aceptar sugerencia", type="primary"):
                append_log("Usuario acepto la sugerencia del LLM.")
                st.session_state.current_query = payload.get("suggestion", "")
                state_snapshot = run_graph_until_interrupt_or_end(
                    Command(resume="accept"), config
                )
                current_state = GRAPH.get_state(config)
                st.session_state.last_results = current_state.values.get("results", [])

                st.session_state.interrupted = False
                st.session_state.interrupt_payload = None

                for task in current_state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        st.session_state.interrupted = True
                        st.session_state.interrupt_payload = task.interrupts[0].value
                        break

                st.rerun()

        with btn_col2:
            if st.button("Usar mi version"):
                append_log(f"Usuario envio su propia version (iter {iteration + 1}).")
                st.session_state.current_query = edited_query
                state_snapshot = run_graph_until_interrupt_or_end(
                    Command(resume=edited_query), config
                )
                current_state = GRAPH.get_state(config)
                st.session_state.last_results = current_state.values.get("results", [])

                st.session_state.interrupted = False
                st.session_state.interrupt_payload = None

                for task in current_state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        st.session_state.interrupted = True
                        st.session_state.interrupt_payload = task.interrupts[0].value
                        break

                st.rerun()

        with btn_col3:
            if st.button("Ignorar y terminar"):
                append_log("Usuario eligio terminar sin corregir.")
                run_graph_until_interrupt_or_end(Command(resume="skip"), config)
                st.session_state.interrupted = False
                st.session_state.interrupt_payload = None
                st.rerun()

    # -----------------------------------------------------------------------
    # Estado final: todo OK
    # -----------------------------------------------------------------------
    if "last_results" in st.session_state and not st.session_state.get("interrupted"):
        all_passed = all(r["passed"] for r in st.session_state.last_results)
        if all_passed and st.session_state.last_results:
            st.success("Todas las reglas pasaron. La query es valida.")
        elif st.session_state.last_results:
            current_state = GRAPH.get_state(config)
            iteration = current_state.values.get("iteration", 0)
            if iteration >= 5:
                st.warning("Limite de iteraciones alcanzado. Revisar la query manualmente.")