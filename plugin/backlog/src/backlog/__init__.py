"""Модуль беклога: носитель порядка работ и следа исполнения операции.

Беклог нужен операции, у которой есть необратимый шаг либо шаг, выполнимый только
владельцем: он несёт значения исполнения во фронтматтере, задачи с проверкой и выводимым
признаком «выполнено ранее» и стоп-знаки перед необратимыми задачами. Операции, у которой
нет ни того, ни другого, беклог не требуется — носитель порядка для одного вызова
превращается в обёртку.

Общие свойства беклога живут здесь, специфика каждой операции — в её шаблоне: механизм
порождения один на все операции, а состав задач различается, и общий шаблон с ветвлениями
исполнителю пришлось бы читать как инструкцию с условиями.

Слои внутри модуля: `domain` — беклог как агрегат, контракт записи и правила того, чем беклог
обязан быть, `application` — сценарии порождения и проверки с контрактами чтения,
`infrastructure` — шаблон, рендер, разбор порождённого беклога, каталог беклогов и чтение
норм поставки.
"""

from .domain import (
    BACKLOG_EXISTS,
    BACKLOG_WRITTEN,
    Backlog,
    BacklogDocument,
    BacklogRepository,
    BacklogTask,
    Finding,
    Leftover,
    execution_findings,
    structure_findings,
)
from .infrastructure import (
    BACKLOG_NAME,
    TEMPLATE_VERSION_PATTERN,
    DeliveryFiles,
    FileBacklog,
    FileBacklogs,
    FileTemplates,
    MarkdownBacklog,
    TemplateGrammar,
    load_template,
    render,
    rule_section,
    scalar,
    template_grammar,
)

__all__ = [
    "Backlog",
    "BacklogRepository",
    "BacklogDocument",
    "BacklogTask",
    "Finding",
    "Leftover",
    "structure_findings",
    "execution_findings",
    "BACKLOG_WRITTEN",
    "BACKLOG_EXISTS",
    "FileTemplates",
    "FileBacklog",
    "FileBacklogs",
    "MarkdownBacklog",
    "load_template",
    "render",
    "scalar",
    "template_grammar",
    "TemplateGrammar",
    "BACKLOG_NAME",
    "TEMPLATE_VERSION_PATTERN",
    "DeliveryFiles",
    "rule_section",
]
