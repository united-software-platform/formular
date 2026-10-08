"""Слой приложения модуля беклога: сценарий порождения и контракты чтения.

Сценарий здесь один: порождение беклога названной операции над названным предметом.
Операции, знающие свои значения и свои предусловия, живут снаружи — они собирают вызов
и передают сценарию готовые значения, потому что вид значения во фронтматтере есть
свойство носителя, а не сценария.
"""

from .contracts import BacklogLookup, TemplateSource
from .generate_backlog import (
    ALREADY_GENERATED,
    GENERATED,
    GenerateBacklogInput,
    GenerateBacklogOutput,
    GenerateBacklogUseCase,
)

__all__ = [
    "BacklogLookup",
    "TemplateSource",
    "GenerateBacklogInput",
    "GenerateBacklogOutput",
    "GenerateBacklogUseCase",
    "GENERATED",
    "ALREADY_GENERATED",
]
