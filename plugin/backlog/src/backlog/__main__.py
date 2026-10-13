"""Вход командной строки: порождение беклога, приёмка шаблона и проверка лежащего беклога.

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

Приёмка шаблона — `check-template` — прогоняет шаблон по всем сочетаниям признаков условных
блоков на значениях-заглушках и файла не пишет: она отвечает на вопрос, порождает ли шаблон
цельный беклог в любом варианте, а не заводит беклог.

Нормы, глоссарий и образцовый шаблон вход выдаёт текстом: `norms` — нормы и за ними глоссарий,
`norms --rule BKL-NNN` — раздел одного правила, `sample` — образец. Это канал внешнего вызова:
в дерево проекта поставка ничего не копирует, а навыки читают те же файлы путём от корня
плагина.

Коды возврата: 0 — беклог порождён либо уже лежал, проверка расхождений не нашла, шаблон
принят; 1 — ввод не позволяет породить, либо проверка нашла расхождения; 2 — ошибка вызова
или окружения.
Исход «уже порождён» ошибкой не является: порождённое задним числом не правится, и повторный
вызов отвечает путём лежащего файла, оставляя его неизменным.
"""

import argparse
import datetime
import os
import pathlib
import sys

from . import (
    DeliveryFiles,
    FileBacklog,
    FileBacklogs,
    FileTemplates,
    MarkdownBacklog,
    render,
    scalar,
    template_grammar,
)
from .application import (
    ALREADY_GENERATED,
    GENERATED,
    TOO_MANY_FLAGS,
    CheckTemplateInput,
    CheckTemplateUseCase,
    GenerateBacklogInput,
    GenerateBacklogUseCase,
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

# Маркер корня целевого проекта: каталог системы контроля версий есть у любого проекта,
# а своих файлов поставка в дерево проекта не кладёт.
PROJECT_MARKERS = (".git",)

# Умолчания имён каталогов внутри проекта: корень следа и каталог шаблонов.
ROOT_NAME = "backlog"
TEMPLATES_NAME = "templates"

# Адрес носителя порядка исполнения: имя навыка плагина, разрешаемое платформой. Вход
# поставки передаёт его переменной BACKLOG_RUNNER, она же служит явному переопределению.
RUNNER_DEFAULT = "/backlog:backlog-run"

# Предмет беклога при приёмке шаблона: файла приёмка не пишет, и предмет нужен только
# значением подстановки `subject`.
CHECK_SUBJECT = "check-template"

# Каталог поставки: корень, под которым лежат нормы, глоссарий и образцовый шаблон.
# Считается от места пакета, а не из переменной: переменные каталога поставки прогонам
# инструмента не достаются, а место пакета внутри поставки известно.
DELIVERY_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Рекомендация для перечня игнорируемых путей проекта. Перечень принадлежит проекту,
# поэтому вход строку не дописывает, а называет: закрывающая строка скрыла бы прежнее
# содержимое каталога, если он уже нёс смысл.
IGNORE_ADVICE = (
    "Рекомендация: если порождённые беклоги не коммитятся, добавьте в .gitignore проекта "
    "строку `{line}`; вход перечень игнорируемых путей не правит."
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


def _ignore_line(root):
    """Строка перечня игнорируемых путей для корня следа: от корня проекта, если он внутри."""
    try:
        relative = root.resolve().relative_to(_project_root().resolve())
    except ValueError:
        relative = root
    return f"{relative.as_posix()}/*"


def _derived_values(operation, subject, stamp):
    """Значения, которые порождение выводит само, а не принимает вызовом.

    Перечень один на порождение и приёмку шаблона: два носителя одного перечня разошлись бы
    при первой правке, и приёмка проверяла бы не то, что порождение заполнит.
    """
    return {
        "date": datetime.datetime.now().strftime(DATE_FORMAT),
        "run_stamp": stamp,
        "operation": operation,
        "subject": subject,
        # Носитель порядка исполнения — значение порождения, а не текст шаблона: способ
        # поставки шаблону не принадлежит. Нормы шаблон называет кодом и вызовом входа,
        # и адреса норм среди значений нет: он зависел бы от раскладки и пути поставки.
        "runner": os.environ.get("BACKLOG_RUNNER") or RUNNER_DEFAULT,
    }


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


HELP_EPILOG = """\
Каталог следа: беклог ложится в <корень следа>/<операция>/<предмет>/tasks.md; корень —
каталог backlog в корне проекта, ключ --root либо переменная BACKLOG_ROOT. Перечень
игнорируемых путей проекта вход не правит: если порождённые беклоги не коммитятся,
добавьте в .gitignore строку `backlog/*` — порождение напомнит об этом, заводя корень
следа впервые.

Нормы и образец: `backlog norms` печатает нормы беклога и глоссарий, `backlog norms
--rule BKL-NNN` — одно правило, `backlog sample` — образцовый шаблон операции."""


def _parse(argv):
    """Разбирает вызов: порождение, приёмка шаблона, две проверки, нормы и образец."""
    parser = argparse.ArgumentParser(
        prog="backlog",
        description="Порождение беклога операции по её шаблону и проверка лежащего беклога.",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    check = sub.add_parser(
        "check-template",
        help="Принять шаблон операции: прогнать его по всем сочетаниям признаков без записи файла",
    )
    check.add_argument("path", help="Путь к файлу шаблона; имя файла без расширения — имя операции")

    lint = sub.add_parser(
        "lint", help="Проверить структуру лежащего беклога"
    )
    lint.add_argument("path", help="Путь к файлу беклога")

    verify = sub.add_parser(
        "verify",
        help="Проверить полноту исполнения беклога: структура и отметки",
    )
    verify.add_argument("path", help="Путь к файлу беклога")

    norms = sub.add_parser(
        "norms", help="Напечатать нормы беклога и за ними глоссарий его понятий"
    )
    norms.add_argument(
        "--rule",
        default=None,
        metavar="BKL-NNN",
        help="Напечатать только раздел названного правила",
    )

    sub.add_parser("sample", help="Напечатать образцовый шаблон операции")
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

    fresh = not root.exists()
    values = _derived_values(operation, subject, stamp)
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
    if result.outcome == GENERATED and fresh:
        print(IGNORE_ADVICE.format(line=_ignore_line(root)), file=sys.stderr)
    return EXIT_OK


def _stub(name):
    """Заглушка подстановки: имя остаётся видимым, и ошибка в имени читаема в выводе."""
    return f"<{name}>"


def _check_values(substitutions, derived):
    """Значения приёмки: выводимые порождением и заглушки прочих подстановок.

    Подстановка `<ключ>_scalar` заполняется от значения `<ключ>` тем же видом, каким её
    заполнило бы порождение: приёмка проверяет то, что порождение подставит.
    """
    values = dict(derived)
    for name in substitutions:
        if name in values or name == "template_version":
            continue
        if name.endswith("_scalar"):
            base = name[: -len("_scalar")]
            values[name] = scalar(values.get(base, _stub(base)))
            continue
        values[name] = _stub(name)
    return values


def _combination(flags):
    """Сочетание признаков словами: взведён либо снят каждый."""
    if not flags:
        return "без признаков"
    return ", ".join(f"{name} {'взведён' if state else 'снят'}" for name, state in flags)


def check_template(arguments):
    """Принимает шаблон операции: прогоняет его по всем сочетаниям признаков."""
    path = pathlib.Path(arguments.path)
    operation = _segment(path.stem, "имя операции")
    templates = FileTemplates(path.parent, _environment, suffix=path.suffix)
    version, text = templates.read(operation)

    stamp = datetime.datetime.now().strftime(STAMP_FORMAT)
    grammar = template_grammar(text)
    values = _check_values(
        grammar.substitutions, _derived_values(operation, CHECK_SUBJECT, stamp)
    )

    use_case = CheckTemplateUseCase(render=render, parser=MarkdownBacklog())
    result = use_case.execute(
        CheckTemplateInput(
            template_version=version, text=text, values=values, flags=grammar.flags
        )
    )

    if result.outcome == TOO_MANY_FLAGS:
        _environment(
            f"шаблон несёт признаков {len(grammar.flags)}, вариантов {result.variants}: "
            "шаблон стоит разделить, а не перебирать"
        )

    for item in result.findings:
        print(
            f"  - [{_combination(item.flags)}] строка {item.finding.line}: "
            f"{item.finding.message}",
            file=sys.stderr,
        )
    verdict = (
        f"Шаблон {operation} версии {version}: вариантов {result.variants}, "
        f"расхождений {len(result.findings)}"
    )
    if result.findings:
        print(verdict, file=sys.stderr)
        return EXIT_BLOCKED
    print(verdict)
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


def norms(arguments):
    """Печатает нормы и глоссарий либо раздел одного правила."""
    delivery = DeliveryFiles(DELIVERY_ROOT, _environment)
    if arguments.rule is None:
        sys.stdout.write(delivery.norms())
        return EXIT_OK

    section = delivery.rule(arguments.rule)
    if section is None:
        _environment(f"правила {arguments.rule} в нормах беклога нет")
    sys.stdout.write(section)
    return EXIT_OK


def sample(arguments):
    """Печатает образцовый шаблон операции."""
    sys.stdout.write(DeliveryFiles(DELIVERY_ROOT, _environment).sample())
    return EXIT_OK


def main(argv=None):
    """Разбирает вызов и исполняет подкоманду."""
    arguments = _parse(sys.argv[1:] if argv is None else argv)
    commands = {
        "norms": norms,
        "sample": sample,
        "lint": lint,
        "verify": verify,
        "generate": generate,
        "check-template": check_template,
    }
    return commands[arguments.command](arguments)


if __name__ == "__main__":
    raise SystemExit(main())
