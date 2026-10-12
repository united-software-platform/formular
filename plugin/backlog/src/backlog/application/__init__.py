"""Слой приложения модуля беклога: сценарии порождения, проверки и установки, контракты чтения.

Сценариев здесь четыре: порождение беклога названной операции над названным предметом,
структурная проверка лежащего беклога, проверка полноты его исполнения и установка состава
поставки в дерево целевого проекта.
Операции, знающие свои значения и свои предусловия, живут снаружи — они собирают вызов
и передают сценарию готовые значения, потому что вид значения во фронтматтере есть
свойство носителя, а не сценария.
"""

from .contracts import (
    BacklogLookup,
    BacklogSource,
    DeliverySource,
    DocumentParser,
    ManifestStore,
    ProjectTree,
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
from .install_rules import (
    ALREADY_INSTALLED,
    CONFLICT,
    INSTALLED,
    LINE_ADDED,
    LINE_PRESENT,
    UPDATED,
    Installed,
    InstallRulesInput,
    InstallRulesOutput,
    InstallRulesUseCase,
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
    "DeliverySource",
    "ProjectTree",
    "ManifestStore",
    "Installed",
    "InstallRulesInput",
    "InstallRulesOutput",
    "InstallRulesUseCase",
    "INSTALLED",
    "ALREADY_INSTALLED",
    "UPDATED",
    "CONFLICT",
    "LINE_ADDED",
    "LINE_PRESENT",
]
