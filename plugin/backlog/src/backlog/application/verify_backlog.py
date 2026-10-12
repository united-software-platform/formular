"""Сценарий проверки полноты исполнения беклога.

Проверка отвечает на вопрос «исполнен ли этот беклог» и включает структурную: вердикт
о полноте отметок осмыслен только на файле, грамматика которого цела — иначе отметки
читать неоткуда. Поэтому расхождения структуры называются первыми.

От сценария структурной проверки этот сценарий не зависит: общее у них — доменные правила,
а не порядок шагов, и зависимость сценария от сценария связала бы два разных вопроса.
"""

import dataclasses

from ..domain import execution_findings, structure_findings

# Исходы сценария.
EXECUTED = "executed"
INCOMPLETE = "incomplete"


@dataclasses.dataclass(frozen=True)
class VerifyBacklogInput:
    """Входной контракт проверки: путь к файлу проверяемого беклога."""

    path: str


@dataclasses.dataclass(frozen=True)
class VerifyBacklogOutput:
    """Выходной контракт: исход и два перечня расхождений — структуры и полноты исполнения.

    Перечни раздельны, потому что отвечают на разные вопросы: первый — цел ли файл,
    второй — исполнен ли он. Слитый перечень заставил бы читателя вывода их различать сам.
    """

    outcome: str
    structure: tuple = ()
    execution: tuple = ()

    @property
    def findings(self):
        """Расхождения целиком, структурные первыми."""
        return self.structure + self.execution


class VerifyBacklogUseCase:
    """Проверка полноты исполнения беклога: единственная публичная операция execute."""

    def __init__(self, backlogs, parser):
        self._backlogs = backlogs
        self._parser = parser

    def execute(self, request):
        """Проверяет структуру и полноту исполнения беклога по названному пути."""
        document = self._parser.parse(self._backlogs.read(request.path))
        structure = structure_findings(document)
        execution = execution_findings(document)
        return VerifyBacklogOutput(
            outcome=INCOMPLETE if structure or execution else EXECUTED,
            structure=structure,
            execution=execution,
        )
