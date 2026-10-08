"""Файл беклога: шаблон, его версия, рендер и каталог порождённых беклогов.

Адаптер знает всё, чего не знает домен: маркер версии первой строкой шаблона, грамматику
условных блоков и подстановок, вид значения во фронтматтере, путь файла в каталоге беклогов.

Версия шаблона живёт в самом шаблоне, а не в константе читающего его прогона: иначе версия
носителя хранилась бы вне носителя, и два ответа на вопрос «какая версия у шаблона»
расходились бы при первой же правке. Маркер служебный — он снимается перед рендером
и в порождённый беклог не попадает: он отвечает прогону, каким составом задач беклог
порождён, а не читателю беклога.
"""

import re

from .domain import BACKLOG_EXISTS, BACKLOG_WRITTEN, BacklogRepository

BACKLOG_NAME = "tasks.md"

# Маркер версии шаблона — первая строка файла шаблона.
TEMPLATE_VERSION_PATTERN = (
    r"^<!--\s*template_version:\s*(?P<version>[0-9]+\.[0-9]+\.[0-9]+)\s*-->\s*$"
)

# Грамматика шаблона: подстановка значения и условный блок по признаку.
SUBSTITUTION_PATTERN = r"\{\{[^}]+\}\}"
BLOCK_OPEN = "{{#%s}}"
BLOCK_NEGATED = "{{^%s}}"
BLOCK_CLOSE = ("{{/%s}}", "{{/^%s}}")


def scalar(value):
    """Записывает значение фронтматтера: кавычки — только там, где без них неоднозначно."""
    if value != value.strip() or re.search(r"[:#\"'\[\]{}]|^[-?&*!|>%@`]", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def load_template(path, fail):
    """Читает шаблон беклога. Возвращает пару (версия шаблона, текст без маркера).

    Отсутствие маркера — ошибка окружения, а не нарушение ввода: дефект шаблона
    обнаруживается до исполнения операции, а не посреди неё, и беклог без названной версии
    шаблона не отвечал бы на вопрос, каким составом задач он порождён.
    """
    if not path.is_file():
        fail(f"шаблон беклога не найден: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"шаблон беклога не читается: {path}: {error}")

    first, _, rest = text.partition("\n")
    match = re.match(TEMPLATE_VERSION_PATTERN, first)
    if match is None:
        fail(
            "первая строка шаблона не несёт маркера версии "
            f"«<!-- template_version: X.Y.Z -->»: {path}"
        )
    return match.group("version"), rest


def render(template_text, values, flags, fail):
    """Рендерит шаблон: условные блоки по признакам и подстановки значений.

    Условный блок оставляет в беклоге либо группу задач, либо названное решение о её
    отсутствии: пропуск группы должен быть виден читателю беклога, а не подразумеваться
    её отсутствием.

    Подстановка, которой нет среди значений, — ошибка окружения: шаблон проверяется целиком,
    и его дефект обнаруживается порождением, а не исполнителем беклога.
    """
    openings = {BLOCK_OPEN % name: name for name in flags}
    negations = {BLOCK_NEGATED % name: name for name in flags}
    closings = {shape % name for name in flags for shape in BLOCK_CLOSE}

    lines = []
    keep = True
    for line in template_text.splitlines():
        marker = line.strip()
        if marker in openings:
            keep = bool(flags[openings[marker]])
            continue
        if marker in negations:
            keep = not flags[negations[marker]]
            continue
        if marker in closings:
            keep = True
            continue
        if keep:
            lines.append(line)

    text = "\n".join(lines) + "\n"
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)

    left = re.search(SUBSTITUTION_PATTERN, text)
    if left:
        fail(f"шаблон содержит подстановку, которой нет среди значений: {left.group(0)}")
    return text


class FileTemplates:
    """Шаблоны операций: файл на операцию в названном каталоге.

    Реализует контракт чтения шаблона. Имя файла выводится из имени операции, потому что
    шаблон у каждой операции свой: общий шаблон с ветвлениями исполнителю пришлось бы читать
    как инструкцию с условиями.
    """

    def __init__(self, directory, fail, suffix=".md"):
        self._directory = directory
        self._fail = fail
        self._suffix = suffix

    def read(self, operation):
        """Возвращает пару (версия шаблона, текст) шаблона названной операции."""
        return load_template(self._directory / f"{operation}{self._suffix}", self._fail)


class FileBacklogs(BacklogRepository):
    """Каталог порождённых беклогов: `<корень следа>/<операция>/<предмет>/tasks.md`.

    Корень следа приходит значением вызова, а не константой модуля: каталог следа
    принадлежит тому, кто продукт применяет, и вшитый путь он бы не выбирал.

    Реализует и контракт записи домена, и контракт чтения наличия: вопрос «порождён ли уже»
    и запись файла отвечают один носитель, и разводить их на два адаптера значило бы дать
    им разойтись в способе складывать путь.
    """

    def __init__(self, directory, fail):
        self._directory = directory
        self._fail = fail

    def path_of(self, operation, subject):
        """Путь файла беклога названной операции над названным предметом."""
        return self._directory / operation / subject / BACKLOG_NAME

    def exists(self, operation, subject):
        """Порождён ли беклог этой операции над этим предметом."""
        return self.path_of(operation, subject).exists()

    def add(self, backlog, text):
        """Заводит беклог. Существующий файл не перезаписывается: порождённое не правится."""
        path = self.path_of(*backlog.address)
        if path.exists():
            return BACKLOG_EXISTS
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as error:
            self._fail(f"беклог не записывается: {path}: {error}")
        return BACKLOG_WRITTEN
