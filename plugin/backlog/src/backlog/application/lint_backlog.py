"""Сценарий структурной проверки беклога.

Проверка отвечает на один вопрос: цела ли грамматика порождённого беклога. Состояния,
которое беклог исполняет, она не видит и не читает — грамматика есть свойство файла.

Найденное сценарий называет и не правит: отметку поставить ему нечем, потому что признак
«выполнено ранее» описан прозой, а отметка по домыслу утверждает исполнение, которого
проверка не наблюдала.
"""

import dataclasses

from ..domain import structure_findings

# Исходы сценария.
CLEAN = "clean"
FOUND = "found"


@dataclasses.dataclass(frozen=True)
class LintBacklogInput:
    """Входной контракт проверки: путь к файлу проверяемого беклога.

    Неизменяем и логики не содержит. Путь приходит значением вызова: адрес проверка
    не складывает, и ни корня следа, ни имени операции ей не нужно.
    """

    path: str


@dataclasses.dataclass(frozen=True)
class LintBacklogOutput:
    """Выходной контракт проверки: исход и перечень расхождений структуры."""

    outcome: str
    findings: tuple = ()


class LintBacklogUseCase:
    """Структурная проверка беклога: единственная публичная операция execute."""

    def __init__(self, backlogs, parser):
        self._backlogs = backlogs
        self._parser = parser

    def execute(self, request):
        """Проверяет грамматику беклога, лежащего по названному пути."""
        document = self._parser.parse(self._backlogs.read(request.path))
        findings = structure_findings(document)
        return LintBacklogOutput(
            outcome=FOUND if findings else CLEAN,
            findings=findings,
        )
