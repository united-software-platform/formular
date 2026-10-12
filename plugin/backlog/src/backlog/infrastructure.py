"""Файл беклога и файлы поставки: шаблон, рендер, каталог беклогов, состав установки.

Адаптер знает всё, чего не знает домен: маркер версии первой строкой шаблона, грамматику
условных блоков и подстановок, вид значения во фронтматтере, путь файла в каталоге беклогов.

Версия шаблона живёт в самом шаблоне, а не в константе читающего его прогона: иначе версия
носителя хранилась бы вне носителя, и два ответа на вопрос «какая версия у шаблона»
расходились бы при первой же правке. Маркер служебный — он снимается перед рендером
и в порождённый беклог не попадает: он отвечает прогону, каким составом задач беклог
порождён, а не читателю беклога.

Здесь же адаптеры установки: состав поставки, дерево целевого проекта и манифест
установленного. Слепок считается от текста, а не от байтов файла: состав поставки —
документы, и перенос их строк не должен выглядеть правкой потребителя.
"""

import dataclasses
import hashlib
import json
import pathlib
import re

from .application import (
    DeliverySource,
    DocumentParser,
    Installed,
    ManifestStore,
    ProjectTree,
)
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


# Имя манифеста установленного в дереве целевого проекта.
MANIFEST_NAME = ".backlog-manifest.json"


def digest(text):
    """Слепок текста: им сверяется лежащий файл с источником и с записью манифеста."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class DeliveryItem:
    """Файл состава поставки: путь в проекте, текст и слепок."""

    path: str
    text: str

    @property
    def digest(self):
        return digest(self.text)


@dataclasses.dataclass(frozen=True)
class ImportLine:
    """Строка подключения: файл проекта, текст строки и строка, после которой дописывать."""

    path: str
    text: str
    after: str = ""


class FileDelivery(DeliverySource):
    """Состав поставки, лежащий в каталоге поставки.

    Каталог состава повторяет раскладку целевого проекта, поэтому относительные ссылки
    между файлами состава разрешаются и в поставке, и после установки — одним и тем же
    путём, без правки текста при копировании.
    """

    def __init__(self, directory, extra=(), fail=None):
        self._directory = directory
        self._extra = tuple(extra)
        self._fail = fail or (lambda message: None)

    def items(self):
        """Состав поставки: файлы каталога состава и названные отдельно."""
        found = []
        for path in sorted(self._directory.rglob("*")):
            if path.is_file():
                found.append((str(path.relative_to(self._directory)), path))
        found.extend(self._extra)

        collected = []
        for relative, source in found:
            try:
                collected.append(DeliveryItem(path=relative, text=source.read_text(encoding="utf-8")))
            except OSError as error:
                self._fail(f"состав поставки не читается: {source}: {error}")
        return tuple(collected)


class FileProject(ProjectTree):
    """Дерево целевого проекта: слепки лежащих файлов, запись и строки подключения."""

    def __init__(self, root, fail):
        self._root = root
        self._fail = fail

    def path_of(self, path):
        """Путь файла в дереве проекта."""
        return self._root / path

    def digest_of(self, path):
        """Слепок лежащего файла либо None, если файла нет."""
        target = self.path_of(path)
        if not target.exists():
            return None
        try:
            return digest(target.read_text(encoding="utf-8"))
        except OSError as error:
            self._fail(f"файл проекта не читается: {target}: {error}")

    def write(self, path, text):
        """Пишет файл проекта, заводя каталоги по пути."""
        target = self.path_of(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        except OSError as error:
            self._fail(f"файл проекта не записывается: {target}: {error}")

    def has_line(self, path, text):
        """Есть ли в файле проекта названная строка: повторное дописывание её не удваивает."""
        target = self.path_of(path)
        if not target.exists():
            return False
        try:
            return text in target.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            self._fail(f"файл проекта не читается: {target}: {error}")

    def add_line(self, path, text, after):
        """Дописывает строку — после названной строки, а без неё в конец файла."""
        target = self.path_of(path)
        try:
            lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
            if after and after in lines:
                lines.insert(lines.index(after) + 1, text)
            else:
                lines.append(text)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as error:
            self._fail(f"строка подключения не дописывается: {target}: {error}")


class FileManifest(ManifestStore):
    """Манифест установленного в дереве целевого проекта.

    Манифест — единственный источник ответа на вопрос «что и какой версией установлено»:
    без него повторный прогон не отличает файл, положенный поставкой, от файла, который
    написал потребитель.
    """

    def __init__(self, root, fail):
        self._path = root / MANIFEST_NAME
        self._fail = fail

    @property
    def path(self):
        return self._path

    def read(self):
        """Установленное прежде. Манифеста нет — установки не было."""
        if not self._path.exists():
            return Installed()
        try:
            stored = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            self._fail(f"манифест установленного не читается: {self._path}: {error}")
            return Installed()
        return Installed(
            version=stored.get("delivery_version", ""),
            files={
                item["path"]: item.get("sha256", "")
                for item in stored.get("files", ())
                if isinstance(item, dict) and "path" in item
            },
        )

    def write(self, version, installed_at, files):
        """Записывает манифест установленного."""
        document = {
            "delivery_version": version,
            "installed_at": installed_at,
            "files": [
                {"path": path, "sha256": files[path]} for path in sorted(files)
            ],
        }
        try:
            self._path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as error:
            self._fail(f"манифест установленного не записывается: {self._path}: {error}")
