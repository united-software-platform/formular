"""Сценарий порождения беклога операции.

Механизм порождения один на все операции: прогон читает шаблон названной операции
и подставляет в него значения вызова. Шаблон у каждой операции свой — состав задач
перемещения, извлечения и подъёма различается, — а общие свойства беклога живут здесь,
а не повторяются в каждом шаблоне.

Порождение состояния пространства не меняет: ни реестр, ни словарь, ни каталог миграций,
ни каталоги проектов им не затрагиваются. Единственный результат успешного прогона —
файл беклога.

Порождённое не правится: беклог, уже заведённый для этой операции над этим предметом,
не перезаписывается. Исход «уже порождён» — ответ операции, а не ошибка: обстоятельство,
требующее другого состава задач, правит шаблон, а не состоявшийся файл.
"""

import dataclasses

from ..domain import BACKLOG_EXISTS, Backlog

# Исходы сценария.
GENERATED = "generated"
ALREADY_GENERATED = "already-generated"


@dataclasses.dataclass(frozen=True)
class GenerateBacklogInput:
    """Входной контракт порождения: операция, предмет, значения и признаки условных блоков.

    Неизменяем и логики не содержит. Значения приходят приведёнными к виду, пригодному
    подстановкой: приводит их сборка вызова, потому что вид значения во фронтматтере —
    свойство носителя, а не сценария.
    """

    operation: str
    subject: str
    values: dict
    flags: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class GenerateBacklogOutput:
    """Выходной контракт порождения: исход, версия шаблона и адрес беклога."""

    outcome: str
    template_version: str = ""
    operation: str = ""
    subject: str = ""


class GenerateBacklogUseCase:
    """Порождение беклога операции: единственная публичная операция execute."""

    def __init__(self, templates, backlogs, render):
        self._templates = templates
        self._backlogs = backlogs
        self._render = render

    def execute(self, request):
        """Порождает беклог названной операции над названным предметом."""
        if self._backlogs.exists(request.operation, request.subject):
            return GenerateBacklogOutput(
                outcome=ALREADY_GENERATED,
                operation=request.operation,
                subject=request.subject,
            )

        version, text = self._templates.read(request.operation)
        values = dict(request.values)
        values.setdefault("template_version", version)

        backlog = Backlog(
            operation=request.operation,
            subject=request.subject,
            template_version=version,
            values=values,
        )
        rendered = self._render(text, values, request.flags)

        if self._backlogs.add(backlog, rendered) == BACKLOG_EXISTS:
            return GenerateBacklogOutput(
                outcome=ALREADY_GENERATED,
                template_version=version,
                operation=request.operation,
                subject=request.subject,
            )

        return GenerateBacklogOutput(
            outcome=GENERATED,
            template_version=version,
            operation=request.operation,
            subject=request.subject,
        )
