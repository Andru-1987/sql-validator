"""
Reglas de validación SQL.
Cada regla es una función que recibe la query y retorna (passed: bool, message: str).
"""

import re
from typing import Callable

Rule = Callable[[str], tuple[bool, str]]


def rule_no_select_star(query: str) -> tuple[bool, str]:
    """SELECT * está prohibido. Siempre especificar columnas."""
    if re.search(r"SELECT\s+\*", query, re.IGNORECASE):
        return False, "No usar SELECT *. Especificar las columnas necesarias."
    return True, "No contiene SELECT *."


def rule_has_where_on_delete_update(query: str) -> tuple[bool, str]:
    """DELETE y UPDATE deben tener clausula WHERE."""
    is_delete = re.search(r"^\s*DELETE", query, re.IGNORECASE)
    is_update = re.search(r"^\s*UPDATE", query, re.IGNORECASE)

    if is_delete or is_update:
        if not re.search(r"\bWHERE\b", query, re.IGNORECASE):
            op = "DELETE" if is_delete else "UPDATE"
            return False, f"{op} sin WHERE afecta todas las filas. Agregar condicion."
    return True, "WHERE presente (o no aplica)."


def rule_no_implicit_join(query: str) -> tuple[bool, str]:
    """Evitar JOINs implícitos (FROM a, b WHERE a.id = b.id)."""
    from_clause = re.search(r"\bFROM\b(.+?)(?:\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|$)",
                            query, re.IGNORECASE | re.DOTALL)
    if from_clause:
        tables_part = from_clause.group(1)
        # Más de una tabla separada por coma = join implícito
        tables = [t.strip() for t in tables_part.split(",") if t.strip()]
        if len(tables) > 1:
            return False, "JOIN implícito detectado. Usar JOIN ... ON explícito."
    return True, "Sin JOINs implícitos."


def rule_aliases_are_meaningful(query: str) -> tuple[bool, str]:
    """Los alias de una sola letra (excepto subconsultas comunes) son poco descriptivos."""
    aliases = re.findall(r"\bAS\s+([a-zA-Z])\b", query, re.IGNORECASE)
    if aliases:
        return False, f"Alias de una letra encontrados: {aliases}. Usar nombres descriptivos."
    return True, "Aliases descriptivos (o sin aliases)."


def rule_no_or_in_join(query: str) -> tuple[bool, str]:
    """OR en condición de JOIN puede causar productos cartesianos no deseados."""
    join_conditions = re.findall(r"\bON\b(.+?)(?:\bJOIN\b|\bWHERE\b|\bGROUP\b|$)",
                                 query, re.IGNORECASE | re.DOTALL)
    for condition in join_conditions:
        if re.search(r"\bOR\b", condition, re.IGNORECASE):
            return False, "OR en condicion de JOIN detectado. Revisar la logica del join."
    return True, "Sin OR en condiciones de JOIN."


ALL_RULES: list[tuple[str, Rule]] = [
    ("No SELECT *", rule_no_select_star),
    ("WHERE en DELETE/UPDATE", rule_has_where_on_delete_update),
    ("Sin JOINs implícitos", rule_no_implicit_join),
    ("Aliases descriptivos", rule_aliases_are_meaningful),
    ("Sin OR en JOIN", rule_no_or_in_join),
]