"""Слой приложения модуля беклога: сценарии порождения и установки, контракты чтения.

Сценариев здесь два: порождение беклога названной операции над названным предметом
и установка состава поставки в дерево целевого проекта.
Операции, знающие свои значения и свои предусловия, живут снаружи — они собирают вызов
и передают сценарию готовые значения, потому что вид значения во фронтматтере есть
свойство носителя, а не сценария.
"""

from .contracts import (
    BacklogLookup,
    DeliverySource,
    ManifestStore,
    ProjectTree,
    TemplateSource,
)
from .generate_backlog import (
    ALREADY_GENERATED,
    GENERATED,
    GenerateBacklogInput,
    GenerateBacklogOutput,
    GenerateBacklogUseCase,
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
    "TemplateSource",
    "GenerateBacklogInput",
    "GenerateBacklogOutput",
    "GenerateBacklogUseCase",
    "GENERATED",
    "ALREADY_GENERATED",
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
