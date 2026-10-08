"""Модуль беклога: носитель порядка работ и следа исполнения операции.

Беклог нужен операции, у которой есть необратимый шаг либо шаг, выполнимый только
владельцем: он несёт значения исполнения во фронтматтере, задачи с проверкой и выводимым
признаком «выполнено ранее» и стоп-знаки перед необратимыми задачами. Операции, у которой
нет ни того, ни другого, беклог не требуется — носитель порядка для одного вызова
превращается в обёртку.

Общие свойства беклога живут здесь, специфика каждой операции — в её шаблоне: механизм
порождения один на все операции, а состав задач различается, и общий шаблон с ветвлениями
исполнителю пришлось бы читать как инструкцию с условиями.

Слои внутри модуля: `domain` — беклог как агрегат и контракт записи, `application` —
сценарий порождения и контракты чтения, `infrastructure` — шаблон, рендер и каталог
порождённых беклогов.
"""

from .domain import BACKLOG_EXISTS, BACKLOG_WRITTEN, Backlog, BacklogRepository
from .infrastructure import (
    BACKLOG_NAME,
    TEMPLATE_VERSION_PATTERN,
    FileBacklogs,
    FileTemplates,
    load_template,
    render,
    scalar,
)

__all__ = [
    "Backlog",
    "BacklogRepository",
    "BACKLOG_WRITTEN",
    "BACKLOG_EXISTS",
    "FileTemplates",
    "FileBacklogs",
    "load_template",
    "render",
    "scalar",
    "BACKLOG_NAME",
    "TEMPLATE_VERSION_PATTERN",
]
