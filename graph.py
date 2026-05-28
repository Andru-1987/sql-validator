"""
Agente LangGraph para validación de SQL.

Flujo del grafo:
  validate_sql -> (falló alguna regla?) -> suggest_fix -> [INTERRUPT: human review] -> validate_sql
                                        -> (todo ok?)   -> END
"""

import os
from typing import TypedDict

from dotenv import load_dotenv
from langchain_cohere import ChatCohere
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from rules import ALL_RULES

load_dotenv()  # carga .env antes de cualquier instanciación

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ValidationResult(TypedDict):
    rule_name: str
    passed: bool
    message: str


class AgentState(TypedDict):
    query: str                 # SQL actual (puede ser reemplazado)
    original_query: str        # SQL original del usuario
    results: list[ValidationResult]
    violations: list[ValidationResult]
    suggestion: str
    iteration: int
    all_passed: bool


# ---------------------------------------------------------------------------
# Nodos
# ---------------------------------------------------------------------------

def validate_sql(state: AgentState) -> AgentState:
    """Corre todas las reglas sobre la query actual."""
    query = state["query"]
    results: list[ValidationResult] = []

    for rule_name, rule_fn in ALL_RULES:
        passed, message = rule_fn(query)
        results.append(ValidationResult(rule_name=rule_name, passed=passed, message=message))

    violations = [r for r in results if not r["passed"]]

    return {
        **state,
        "results": results,
        "violations": violations,
        "all_passed": len(violations) == 0,
    }


def suggest_fix(state: AgentState) -> AgentState:
    """
    Llama al LLM para sugerir una versión corregida del SQL.
    Luego hace INTERRUPT para que el humano decida si acepta la sugerencia.
    """
    query = state["query"]
    violations = state["violations"]

    violation_text = "\n".join(
        f"- [{v['rule_name']}] {v['message']}" for v in violations
    )

    prompt = f"""Eres un experto en SQL. La siguiente query viola estas reglas:
{violation_text}

Query original:
```sql
{query}
```

Devuelve SOLO la query corregida en SQL, sin explicaciones, sin markdown, sin backticks.
"""

    llm = ChatCohere(
        model=os.environ["COHERE_MODEL"],
        cohere_api_key=os.environ["COHERE_API_KEY"],
    )
    response = llm.invoke(prompt)
    suggestion = response.content.strip()

    user_decision = interrupt({
        "suggestion": suggestion,
        "violations": violations,
        "iteration": state["iteration"],
    })

    if user_decision == "accept":
        new_query = suggestion
    elif user_decision == "skip":
        new_query = query
    else:
        new_query = user_decision

    return {
        **state,
        "query": new_query,
        "suggestion": suggestion,
        "iteration": state["iteration"] + 1,
        "all_passed": user_decision == "skip",
    }


# ---------------------------------------------------------------------------
# Edges (condicionales)
# ---------------------------------------------------------------------------

def route_after_validation(state: AgentState) -> str:
    if state["all_passed"]:
        return END
    return "suggest_fix"


def route_after_suggestion(state: AgentState) -> str:
    if state["all_passed"]:
        return END
    if state["iteration"] >= 5:
        return END
    return "validate_sql"


# ---------------------------------------------------------------------------
# Construcción del grafo
# ---------------------------------------------------------------------------

def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("validate_sql", validate_sql)
    builder.add_node("suggest_fix", suggest_fix)

    builder.add_edge(START, "validate_sql")
    builder.add_conditional_edges("validate_sql", route_after_validation)
    builder.add_conditional_edges("suggest_fix", route_after_suggestion)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


GRAPH = build_graph()