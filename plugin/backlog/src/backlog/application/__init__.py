"""Слой приложения модуля беклога: сценарии порождения и проверки, контракты чтения.

Сценариев здесь четыре: порождение беклога названной операции над названным предметом,
приёмка шаблона операции по всем сочетаниям признаков, структурная проверка лежащего беклога
и проверка полноты его исполнения.
Операции, знающие свои значения и свои предусловия, живут снаружи — они собирают вызов
и передают сценарию готовые значения, потому что вид значения во фронтматтере есть
свойство носителя, а не сценария.
"""

from .contracts import (
    BacklogLookup,
    BacklogSource,
    DocumentParser,
    TemplateSource,
)
from .generate_backlog import (
    ALREADY_GENERATED,
    GENERATED,
    REJECTED,
    GenerateBacklogInput,
    GenerateBacklogOutput,
    GenerateBacklogUseCase,
)
from .check_template import (
    ACCEPTED,
    DEFECTIVE,
    MAX_FLAGS,
    TOO_MANY_FLAGS,
    CheckTemplateInput,
    CheckTemplateOutput,
    CheckTemplateUseCase,
    VariantFinding,
)
from .lint_backlog import (
    CLEAN,
    FOUND,
    LintBacklogInput,
    LintBacklogOutput,
    LintBacklogUseCase,
)
from .verify_backlog import (
    EXECUTED,
    INCOMPLETE,
    VerifyBacklogInput,
    VerifyBacklogOutput,
    VerifyBacklogUseCase,
)
__all__ = [
    "BacklogLookup",
    "BacklogSource",
    "DocumentParser",
    "TemplateSource",
    "GenerateBacklogInput",
    "GenerateBacklogOutput",
    "GenerateBacklogUseCase",
    "GENERATED",
    "ALREADY_GENERATED",
    "REJECTED",
    "CheckTemplateInput",
    "CheckTemplateOutput",
    "CheckTemplateUseCase",
    "VariantFinding",
    "ACCEPTED",
    "DEFECTIVE",
    "TOO_MANY_FLAGS",
    "MAX_FLAGS",
    "LintBacklogInput",
    "LintBacklogOutput",
    "LintBacklogUseCase",
    "CLEAN",
    "FOUND",
    "VerifyBacklogInput",
    "VerifyBacklogOutput",
    "VerifyBacklogUseCase",
    "EXECUTED",
    "INCOMPLETE",
]
