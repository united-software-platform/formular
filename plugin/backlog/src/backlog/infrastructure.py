"""Файл беклога и файлы поставки: шаблон, рендер, каталог беклогов, нормы поставки.

Адаптер знает всё, чего не знает домен: маркер версии первой строкой шаблона, грамматику
условных блоков и подстановок, вид значения во фронтматтере, путь файла в каталоге беклогов.

Версия шаблона живёт в самом шаблоне, а не в константе читающего его прогона: иначе версия
носителя хранилась бы вне носителя, и два ответа на вопрос «какая версия у шаблона»
расходились бы при первой же правке. Маркер служебный — он снимается перед рендером
и в порождённый беклог не попадает: он отвечает прогону, каким составом задач беклог
порождён, а не читателю беклога.

Здесь же чтение норм, глоссария и образца из каталога поставки: они существуют в одном
экземпляре — в поставке, — и вход выдаёт их текстом в контекст вызова, а не копирует
в дерево проекта.
"""

import dataclasses
import pathlib
import re

from .application import DocumentParser
from .domain import (
    BACKLOG_EXISTS,
    BACKLOG_WRITTEN,
    BacklogDocument,
    BacklogRepository,
    BacklogTask,
    Leftover,
)

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

# Грамматика порождённого беклога: та же разметка, которой он записан.
FRONTMATTER_FENCE = "---"
TASK_PATTERN = r"^- \[(?P<mark>[ xX])\]\s+(?P<rest>.*)$"
TASK_NUMBER_PATTERN = r"^(?P<number>[0-9]+(?:\.[0-9]+)*)"
CHECK_PREFIX = "- Проверка:"
COMPLETION_PREFIX = "- Выполнено ранее:"
STOP_SIGN_MARK = "Стоп-знак"
CONFIRMATION_PATTERN = r"confirmed\.[A-Za-z0-9_.]+"
VERSION_TABLE_HEADING = "## Версионирование"
RUNNER_KEY = "runner"
RULE_CODE_PATTERN = r"\bBKL-[0-9]{3}\b"
TEMPLATE_VERSION_KEY = "template_version"


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


def render(template_text, values, flags):
    """Рендерит шаблон: условные блоки по признакам и подстановки значений.

    Условный блок оставляет в беклоге либо группу задач, либо названное решение о её
    отсутствии: пропуск группы должен быть виден читателю беклога, а не подразумеваться
    её отсутствием.

    Остатка подстановки рендер не проверяет: остаток — нарушение структуры порождённого
    беклога, и называет его структурная проверка перед записью файла. Два носителя одного
    правила разошлись бы при первой правке.
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
    return text


@dataclasses.dataclass(frozen=True)
class TemplateGrammar:
    """Грамматика шаблона: имена подстановок и признаки условных блоков, в порядке появления."""

    substitutions: tuple = ()
    flags: tuple = ()


def template_grammar(template_text):
    """Перечень подстановок и признаков условных блоков шаблона.

    Знание о `{{x}}`, `{{#x}}` и `{{^x}}` живёт здесь, рядом с рендером: домен грамматики
    шаблона не знает, а сценарий приёмки получает перечень готовым, как получает рендер.
    """
    substitutions = []
    flags = []
    for match in re.finditer(r"\{\{(?P<sigil>[#^/]?)(?P<name>[^}]+)\}\}", template_text):
        sigil, name = match.group("sigil"), match.group("name").strip()
        if sigil == "/":
            continue
        target = flags if sigil in ("#", "^") else substitutions
        if name not in target:
            target.append(name)
    return TemplateGrammar(substitutions=tuple(substitutions), flags=tuple(flags))


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


def _frontmatter(lines):
    """Разбирает фронтматтер беклога: значения верхнего уровня и один уровень вложенности.

    Вложенность глубже одного уровня не разбирается намеренно: фронтматтер несёт значения
    исполнения, а не дерево настроек, и вложенный ключ записывается точкой — `confirmed.шаг`,
    тем же видом, каким его называет текст задачи.

    Возвращает пару (разобран ли фронтматтер, значения точечными ключами). Отсутствие
    фронтматтера от пустого фронтматтера отличается первым значением пары: первое есть
    нарушение, второе возможно у операции без значений.
    """
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return False, {}

    values = {}
    parent = ""
    for line in lines[1:]:
        if line.strip() == FRONTMATTER_FENCE:
            return True, values
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        nested = key.startswith((" ", "\t"))
        name = key.strip()
        value = value.strip().strip('"').strip("'")
        if nested and parent:
            values[f"{parent}.{name}"] = value
            continue
        parent = name if not value else ""
        values[name] = value
    return False, values


def _tasks(lines):
    """Собирает задачи беклога: отметка, номер, строки проверки и признака, стоп-знак.

    Задача кончается там, где начинается следующая задача либо заголовок раздела: строки
    между ними принадлежат ей — перенос текста, строка проверки, строка признака.

    Поле подтверждения, которое задача записывает во фронтматтер, берётся из её же текста:
    задача называет его сама, и второго носителя этого знания — перечня полей в прогоне —
    заводить незачем.
    """
    collected = []
    current = None
    body = []

    def close(task, text):
        if task is None:
            return None
        confirmation = re.search(CONFIRMATION_PATTERN, text)
        return dataclasses.replace(
            task,
            has_check=any(line.strip().startswith(CHECK_PREFIX) for line in body),
            has_completion_marker=any(
                line.strip().startswith(COMPLETION_PREFIX) for line in body
            ),
            stop_sign=STOP_SIGN_MARK in text,
            confirmation=confirmation.group(0) if confirmation else "",
            text=re.sub(TASK_PATTERN, r"\g<rest>", text, count=1, flags=re.M),
        )

    for number, line in enumerate(lines, start=1):
        match = re.match(TASK_PATTERN, line)
        if match is None and not line.startswith("#"):
            if current is not None:
                body.append(line)
            continue

        closed = close(current, "\n".join(body))
        if closed is not None:
            collected.append(closed)
        current = None
        body = []

        if match is None:
            continue

        rest = match.group("rest")
        numbered = re.match(TASK_NUMBER_PATTERN, rest)
        current = BacklogTask(
            number=numbered.group("number") if numbered else rest[:20],
            line=number,
            marked=match.group("mark") in ("x", "X"),
            has_check=False,
            has_completion_marker=False,
        )
        body = [line]

    closed = close(current, "\n".join(body))
    if closed is not None:
        collected.append(closed)
    return tuple(collected)


def _leftovers(lines):
    """Остатки грамматики шаблона в тексте беклога, с местом каждого."""
    found = []
    for number, line in enumerate(lines, start=1):
        for match in re.finditer(SUBSTITUTION_PATTERN, line):
            found.append(Leftover(line=number, text=match.group(0)))
    return tuple(found)


def _rule_codes(lines):
    """Коды правил, названные в тексте: текстом ссылки прежнего вида либо рядом с вызовом."""
    found = []
    for line in lines:
        for match in re.finditer(RULE_CODE_PATTERN, line):
            if match.group(0) not in found:
                found.append(match.group(0))
    return tuple(found)


def _version_table(lines):
    """Завершается ли беклог таблицей версий: заголовок и хотя бы одна строка таблицы."""
    for number, line in enumerate(lines):
        if line.strip() != VERSION_TABLE_HEADING:
            continue
        if any(rest.strip().startswith("|") for rest in lines[number + 1 :]):
            return True
    return False


class MarkdownBacklog(DocumentParser):
    """Разбор порождённого беклога в структуру домена.

    Реализует контракт разбора. Здесь живёт всё, чего не знает домен: заголовок фронтматтера,
    синтаксис отметки, вид строки проверки и строки признака, заголовок таблицы версий.
    Правила над разобранным — что беклог обязан нести — остаются доменом.
    """

    def parse(self, text):
        """Возвращает разобранный беклог структурой домена."""
        lines = text.splitlines()
        parsed, values = _frontmatter(lines)
        return BacklogDocument(
            frontmatter_parsed=parsed,
            frontmatter=values,
            template_version=values.get(TEMPLATE_VERSION_KEY, ""),
            tasks=_tasks(lines),
            runner_pointer=bool(values.get(RUNNER_KEY, "")),
            version_table=_version_table(lines),
            leftovers=_leftovers(lines),
            rule_codes=_rule_codes(lines),
        )


class FileBacklog:
    """Проверяемый беклог: текст файла по названному пути.

    Реализует контракт чтения проверяемого беклога. Адрес не складывается из операции
    и предмета: проверка читает лежащий файл, и корень следа ей не нужен.

    Отсутствие файла и нечитаемый файл — ошибка вызова: проверка о беклоге в таком случае
    ничего не говорит, и вердикта у неё нет.
    """

    def __init__(self, fail):
        self._fail = fail

    def read(self, path):
        """Возвращает текст беклога, лежащего по названному пути."""
        target = pathlib.Path(path)
        if not target.is_file():
            self._fail(f"беклог не найден: {target}")
        try:
            return target.read_text(encoding="utf-8")
        except OSError as error:
            self._fail(f"беклог не читается: {target}: {error}")
        return ""


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


# Состав поставки, который вход выдаёт текстом: пути от корня поставки.
NORMS_PATH = "share/rules/operation-backlog-rules.md"
GLOSSARY_PATH = "share/docs/glossary.md"
SAMPLE_PATH = "templates/sample-operation.md"

# Разбор норм по правилу: заголовок раздела и абзац, открытый кодом правила.
HEADING_PATTERN = r"^(?P<level>#+)\s"
RULE_OPENING = "**[%s]**"


def rule_section(text, code):
    """Раздел норм, несущий правило с названным кодом, либо None.

    Правило ищется по коду `**[BKL-NNN]**` в начале абзаца, а раздел — от заголовка,
    его содержащего, до следующего заголовка того же или старшего уровня. Код, упомянутый
    в тексте другого правила, раздела не открывает: упоминание — ссылка, а не правило.
    """
    lines = text.splitlines()
    opening = RULE_OPENING % code
    at = next(
        (number for number, line in enumerate(lines) if line.startswith(opening)), None
    )
    if at is None:
        return None

    start = 0
    level = 1
    for number in range(at, -1, -1):
        match = re.match(HEADING_PATTERN, lines[number])
        if match:
            start, level = number, len(match.group("level"))
            break

    end = len(lines)
    for number in range(at + 1, len(lines)):
        match = re.match(HEADING_PATTERN, lines[number])
        if match and len(match.group("level")) <= level:
            end = number
            break

    section = lines[start:end]
    while section and section[-1].strip() in ("", "---"):
        section.pop()
    return "\n".join(section) + "\n"


class DeliveryFiles:
    """Нормы, глоссарий и образцовый шаблон, лежащие в каталоге поставки.

    Корень поставки приходит значением: вход находит его сам от места пакета, потому что
    переменные каталога поставки прогонам инструмента не достаются.
    """

    def __init__(self, root, fail):
        self._root = root
        self._fail = fail

    def _read(self, relative):
        path = self._root / relative
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            self._fail(f"файл поставки не читается: {path}: {error}")
        return ""

    def norms(self):
        """Нормы беклога, за ними глоссарий: без глоссария понятия норм не определены."""
        return self._read(NORMS_PATH).rstrip("\n") + "\n\n" + self._read(GLOSSARY_PATH)

    def rule(self, code):
        """Раздел норм с названным правилом либо None, если такого кода в нормах нет."""
        return rule_section(self._read(NORMS_PATH), code)

    def sample(self):
        """Образцовый шаблон операции — текстом, пригодным к записи в каталог шаблонов."""
        return self._read(SAMPLE_PATH)
