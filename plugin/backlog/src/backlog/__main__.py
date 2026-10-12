"""Вход командной строки: порождение беклога операции и проверка лежащего беклога.

Вход операций не знает. Он принимает имя операции, предмет, значения подстановок и признаки
условных блоков — и тем же составом вызывается для любой операции, у которой есть шаблон.
Операция, знающая свои предусловия и свои значения, собирает вызов снаружи: иначе вход
пришлось бы править при заведении каждой новой операции.

Признаки условных блоков называются вызовом полностью — и взведённые, и снятые: признак,
не названный вовсе, оставляет маркер блока в тексте и прекращает порождение.

Проверок две. `lint` отвечает на вопрос, цела ли грамматика лежащего беклога; `verify` —
на вопрос, исполнен ли он, и включает структурную проверку: вердикт о полноте отметок осмыслен
только на файле, грамматика которого цела. Структурную проверку прогоняет и само порождение —
до записи файла, потому что лежащий беклог правке не подлежит.

Коды возврата: 0 — беклог порождён либо уже лежал, проверка расхождений не нашла; 1 — ввод
не позволяет породить, либо проверка нашла расхождения; 2 — ошибка вызова или окружения.
Исход «уже порождён» ошибкой не является: порождённое задним числом не правится, и повторный
вызов отвечает путём лежащего файла, оставляя его неизменным.
"""

import argparse
import datetime
import os
import pathlib
import sys

import json

from . import (
    FileBacklog,
    FileBacklogs,
    FileDelivery,
    FileManifest,
    FileProject,
    FileTemplates,
    ImportLine,
    MarkdownBacklog,
    render,
    scalar,
)
from .application import (
    ALREADY_GENERATED,
    CONFLICT,
    GenerateBacklogInput,
    GenerateBacklogUseCase,
    InstallRulesInput,
    InstallRulesUseCase,
    LINE_ADDED,
    LintBacklogInput,
    LintBacklogUseCase,
    REJECTED,
    VerifyBacklogInput,
    VerifyBacklogUseCase,
)

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_ENVIRONMENT = 2

STAMP_FORMAT = "%Y%m%d%H%M%S"
DATE_FORMAT = "%Y-%m-%d"

# Маркеры корня целевого проекта, в порядке убывания определённости: манифест установки
# кладёт сама поставка, каталог системы контроля версий есть у любого проекта.
PROJECT_MARKERS = (".backlog-manifest.json", ".git")

# Умолчания имён каталогов внутри проекта: корень следа и каталог шаблонов.
ROOT_NAME = "backlog"
TEMPLATES_NAME = "templates"

# Адрес носителя порядка исполнения при плагинной поставке. Вход поставки называет свой
# способ переменной BACKLOG_RUNNER; значение по умолчанию отвечает поставке плагином.
RUNNER_DEFAULT = "/backlog:backlog-run"

# Файл норм беклога в дереве целевого проекта: от него считается ссылка, которую несёт
# порождённый беклог.
RULES_NAME = "rules/operation-backlog-rules.md"

# Каталог поставки: корень, под которым лежат состав установки и образцовый шаблон.
# Считается от места пакета, а не из переменной: переменные каталога поставки прогонам
# инструмента не достаются, а место пакета внутри поставки известно.
DELIVERY_ROOT = pathlib.Path(__file__).resolve().parents[2]
DELIVERY_SHARE = "share"
DELIVERY_SAMPLE = "templates/sample-operation.md"
DELIVERY_PLUGIN_MANIFEST = ".claude-plugin/plugin.json"

STAMP_ISO = "%Y-%m-%dT%H:%M:%SZ"

# Строки подключения, которые установка дописывает в точки подключения проекта.
# Подключение относительное: `@`-импорт за пределы рабочего каталога требует отдельного
# одобрения владельца и обновление поставки не переживает.
IMPORT_LINES = (
    ImportLine(path="CLAUDE.md", text="@" + RULES_NAME, after="@rules/docker.md"),
    ImportLine(path="CLAUDE.md", text="@docs/glossary.md"),
)

# Строки перечня игнорируемых путей: порождённые беклоги принадлежат прогону, а описание
# адреса остаётся исключением — оно отвечает на вопрос об адресе.
IGNORE_LINES = (
    ImportLine(path=".gitignore", text="backlog/*"),
    ImportLine(path=".gitignore", text="!backlog/README.md"),
)


def _blocked(message):
    """Отказ по вводу: вызов составлен так, что порождать нечем."""
    print(f"Отказ: {message}", file=sys.stderr)
    raise SystemExit(EXIT_BLOCKED)


def _environment(message):
    """Отказ по окружению: дефект шаблона или каталога обнаружен до исполнения операции."""
    print(f"Ошибка окружения: {message}", file=sys.stderr)
    raise SystemExit(EXIT_ENVIRONMENT)


def _project_root():
    """Корень целевого проекта: от него считаются умолчания каталогов.

    Платформа корень прогонам инструмента не сообщает, поэтому он ищется маркером вверх
    по дереву от рабочего каталога. Назвать его переменной окружения можно и напрямую:
    так корень задаётся там, где маркера нет.
    """
    named = os.environ.get("CLAUDE_PROJECT_DIR")
    if named:
        return pathlib.Path(named)

    start = pathlib.Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    return pathlib.Path.cwd()


def _default_dir(variable, name):
    """Умолчание каталога: переменная механизма, иначе каталог в корне проекта.

    От рабочего каталога умолчание не считается: прогон из подкаталога завёл бы второй
    каталог следа, и ответ на вопрос «где лежит беклог этой операции» зависел бы от того,
    откуда вызвали вход.
    """
    named = os.environ.get(variable)
    if named:
        return pathlib.Path(named)
    return _project_root() / name


def _rules_link(backlog_dir):
    """Ссылка на нормы беклога от каталога порождаемого файла.

    Беклог лежит тремя уровнями ниже корня проекта, поэтому ссылка, записанная в шаблоне
    относительной, в порождённом файле указывает в пустоту. Значение считается порождением:
    шаблон описывает состав задач, а не раскладку проекта.
    """
    target = _project_root() / RULES_NAME
    return os.path.relpath(target, backlog_dir)


def _pairs(given):
    """Разбирает значения вида `ключ=значение`.

    Каждому значению заводится и подстановка `ключ_scalar` — тот же текст в виде, пригодном
    значением фронтматтера. Вызывающему не приходится знать, когда значение нужно взять
    в кавычки: вид значения во фронтматтере есть свойство носителя, а не вызова.
    """
    values = {}
    for item in given or ():
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            _blocked(f"значение задаётся парой «ключ=значение»: {item}")
        key = key.strip()
        if key in values:
            _blocked(f"значение названо дважды: {key}")
        values[key] = value
        values[f"{key}_scalar"] = scalar(value)
    return values


def _flags(raised, lowered):
    """Собирает признаки условных блоков: взведённые и снятые.

    Снятый признак называется вызовом наравне со взведённым, а не опускается: признак,
    не названный вовсе, оставляет маркер блока в тексте и прекращает порождение ошибкой
    окружения. Так дефект вызова обнаруживается порождением, а не исполнителем беклога,
    который прочёл бы маркер как задачу.
    """
    flags = {}
    for name in raised or ():
        flags[name] = True
    for name in lowered or ():
        if name in flags:
            _blocked(f"признак назван и взведённым, и снятым: {name}")
        flags[name] = False
    return flags


def _parse(argv):
    """Разбирает вызов: порождение, две проверки и установка норм."""
    parser = argparse.ArgumentParser(
        prog="backlog",
        description="Порождение беклога операции по её шаблону и проверка лежащего беклога.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate", help="Породить беклог операции")
    generate.add_argument("--operation", required=True, help="Имя операции: оно же имя шаблона")
    generate.add_argument(
        "--subject",
        default=None,
        help="Предмет беклога; без него предметом становится штамп прогона YYYYMMDDHHMMSS",
    )
    generate.add_argument(
        "--value",
        action="append",
        metavar="КЛЮЧ=ЗНАЧЕНИЕ",
        help="Значение подстановки шаблона; повторяется по значению",
    )
    generate.add_argument(
        "--flag",
        action="append",
        metavar="ИМЯ",
        help="Признак условного блока шаблона взведён; повторяется по признаку",
    )
    generate.add_argument(
        "--no-flag",
        action="append",
        metavar="ИМЯ",
        dest="no_flag",
        help="Признак условного блока шаблона снят: группа задач не порождается, "
        "а решение о её отсутствии остаётся в беклоге названным",
    )
    generate.add_argument(
        "--root",
        default=None,
        help="Корень каталога следа; умолчание — каталог backlog в корне проекта "
        "либо значение переменной BACKLOG_ROOT",
    )
    generate.add_argument(
        "--templates",
        default=None,
        help="Каталог шаблонов операций; умолчание — каталог templates в корне проекта "
        "либо значение переменной BACKLOG_TEMPLATES",
    )
    lint = sub.add_parser(
        "lint", help="Проверить структуру лежащего беклога"
    )
    lint.add_argument("path", help="Путь к файлу беклога")

    verify = sub.add_parser(
        "verify",
        help="Проверить полноту исполнения беклога: структура и отметки",
    )
    verify.add_argument("path", help="Путь к файлу беклога")

    install = sub.add_parser(
        "install", help="Установить нормы беклога в дерево целевого проекта"
    )
    install.add_argument(
        "--project",
        default=None,
        help="Дерево целевого проекта; умолчание — корень проекта, найденный от рабочего каталога",
    )
    return parser.parse_args(argv)


def _segment(name, what):
    """Сверяет, что имя пригодно сегментом пути: по паре имён беклог и находится."""
    if not name or "/" in name or name in (".", "..") or name != name.strip():
        _blocked(f"{what} непригоден сегментом пути: {name!r}")
    return name


def generate(arguments):
    """Порождает беклог названной операции над названным предметом."""
    stamp = datetime.datetime.now().strftime(STAMP_FORMAT)
    operation = _segment(arguments.operation, "имя операции")
    subject = _segment(arguments.subject or stamp, "предмет беклога")

    root = (
        pathlib.Path(arguments.root)
        if arguments.root is not None
        else _default_dir("BACKLOG_ROOT", ROOT_NAME)
    )
    templates_dir = (
        pathlib.Path(arguments.templates)
        if arguments.templates is not None
        else _default_dir("BACKLOG_TEMPLATES", TEMPLATES_NAME)
    )

    values = {
        "date": datetime.datetime.now().strftime(DATE_FORMAT),
        "run_stamp": stamp,
        "operation": operation,
        "subject": subject,
        # Носитель порядка исполнения и ссылка на нормы — значения порождения, а не текст
        # шаблона: способ поставки и раскладка проекта шаблону не принадлежат.
        "runner": os.environ.get("BACKLOG_RUNNER") or RUNNER_DEFAULT,
        "rules": _rules_link(root / operation / subject),
    }
    values.update(_pairs(arguments.value))
    flags = _flags(arguments.flag, arguments.no_flag)

    templates = FileTemplates(templates_dir, _environment)
    backlogs = FileBacklogs(root, _environment)
    use_case = GenerateBacklogUseCase(
        templates=templates,
        backlogs=backlogs,
        render=render,
        parser=MarkdownBacklog(),
    )

    result = use_case.execute(
        GenerateBacklogInput(
            operation=operation,
            subject=subject,
            values=values,
            flags=flags,
        )
    )
    path = backlogs.path_of(result.operation, result.subject)

    if result.outcome == REJECTED:
        print(
            "Ошибка окружения: порождённый беклог не отвечает структуре, и файл не заведён:",
            file=sys.stderr,
        )
        for finding in result.findings:
            print(f"  - строка {finding.line}: {finding.message}", file=sys.stderr)
        print(
            f"Шаблон операции {operation} версии {result.template_version} правится, "
            "а не порождённый файл",
            file=sys.stderr,
        )
        return EXIT_ENVIRONMENT

    if result.outcome == ALREADY_GENERATED:
        print(
            f"Предупреждение: беклог операции {operation} над предметом {subject} уже порождён; "
            "порождённое задним числом не правится"
        )
        print(f"Беклог: {path}")
        return EXIT_OK

    print(f"Беклог порождён шаблоном версии {result.template_version}")
    print(f"Беклог: {path}")
    return EXIT_OK


def _report(findings, subject):
    """Печатает перечень расхождений и вердикт последней строкой.

    Место в файле называется у каждого расхождения: читателю вывода не нужно открывать беклог,
    чтобы понять, где нарушение. Вердикт стоит последней строкой — её и читают, когда перечень
    длинный.
    """
    for finding in findings:
        print(f"  - строка {finding.line}: {finding.message}", file=sys.stderr)
    if findings:
        print(f"{subject}: расхождений {len(findings)}", file=sys.stderr)
        return EXIT_BLOCKED
    print(f"{subject}: расхождений нет")
    return EXIT_OK


def _checks():
    """Собирает носители проверки: чтение файла по пути и разбор его текста."""
    return FileBacklog(_environment), MarkdownBacklog()


def lint(arguments):
    """Проверяет структуру беклога, лежащего по названному пути."""
    backlogs, parser = _checks()
    use_case = LintBacklogUseCase(backlogs=backlogs, parser=parser)
    result = use_case.execute(LintBacklogInput(path=arguments.path))
    return _report(result.findings, "Структура беклога")


def verify(arguments):
    """Проверяет структуру и полноту исполнения беклога по названному пути."""
    backlogs, parser = _checks()
    use_case = VerifyBacklogUseCase(backlogs=backlogs, parser=parser)
    result = use_case.execute(VerifyBacklogInput(path=arguments.path))

    for finding in result.structure:
        print(f"  - строка {finding.line}: {finding.message}", file=sys.stderr)
    for finding in result.execution:
        print(f"  - строка {finding.line}: {finding.message}", file=sys.stderr)

    if result.findings:
        print(
            f"Исполнение беклога: расхождений {len(result.findings)} "
            f"(структура {len(result.structure)}, отметки и подтверждения "
            f"{len(result.execution)})",
            file=sys.stderr,
        )
        return EXIT_BLOCKED
    print("Исполнение беклога: расхождений нет, беклог исполнен")
    return EXIT_OK


def _delivery_version():
    """Версия поставки: из манифеста плагина либо из переменной окружения.

    Версия принадлежит поставке, а не установщику: без неё манифест установленного
    не отвечает на вопрос, какой версией установлен состав.
    """
    named = os.environ.get("BACKLOG_VERSION")
    if named:
        return named

    manifest = DELIVERY_ROOT / DELIVERY_PLUGIN_MANIFEST
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        _environment(
            f"версия поставки не определяется: ни BACKLOG_VERSION, ни {manifest}"
        )


def install(arguments):
    """Устанавливает нормы, определения, образцовый шаблон и описание каталога следа."""
    project = (
        pathlib.Path(arguments.project)
        if arguments.project is not None
        else _project_root()
    )
    share = DELIVERY_ROOT / DELIVERY_SHARE
    if not share.is_dir():
        _environment(f"состав поставки не найден: {share}")

    sample = DELIVERY_ROOT / DELIVERY_SAMPLE
    extra = ((DELIVERY_SAMPLE, sample),) if sample.is_file() else ()

    tree = FileProject(project, _environment)
    manifest = FileManifest(project, _environment)
    use_case = InstallRulesUseCase(
        delivery=FileDelivery(share, extra=extra, fail=_environment),
        project=tree,
        manifest=manifest,
    )

    result = use_case.execute(
        InstallRulesInput(
            delivery_version=_delivery_version(),
            installed_at=datetime.datetime.now(datetime.timezone.utc).strftime(STAMP_ISO),
            lines=IMPORT_LINES + IGNORE_LINES,
        )
    )

    for item in result.files:
        print(f"{item.outcome}: {item.path}")
    for item in result.lines:
        if item.outcome == LINE_ADDED:
            print(f"строка подключения дописана в {item.path}: {item.line}")
    print(f"Манифест установленного: {manifest.path}")

    conflicts = result.conflicts
    if conflicts:
        print(
            "Расхождение со слепком манифеста — файлы правил потребитель, и перезаписаны "
            "они не были:",
            file=sys.stderr,
        )
        for item in conflicts:
            print(f"  - {item.path}", file=sys.stderr)
        print("Решение остаётся владельцу: править состав поставки или свой файл.", file=sys.stderr)
        return EXIT_BLOCKED
    return EXIT_OK


def main(argv=None):
    """Разбирает вызов и исполняет подкоманду."""
    arguments = _parse(sys.argv[1:] if argv is None else argv)
    commands = {
        "install": install,
        "lint": lint,
        "verify": verify,
        "generate": generate,
    }
    return commands[arguments.command](arguments)


if __name__ == "__main__":
    raise SystemExit(main())
