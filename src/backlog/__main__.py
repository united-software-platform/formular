"""Вход командной строки: порождение беклога операции.

Вход операций не знает. Он принимает имя операции, предмет, значения подстановок и признаки
условных блоков — и тем же составом вызывается для любой операции, у которой есть шаблон.
Операция, знающая свои предусловия и свои значения, собирает вызов снаружи: иначе вход
пришлось бы править при заведении каждой новой операции.

Признаки условных блоков называются вызовом полностью — и взведённые, и снятые: признак,
не названный вовсе, оставляет маркер блока в тексте и прекращает порождение.

Коды возврата: 0 — беклог порождён либо уже лежал, 1 — ввод не позволяет породить,
2 — ошибка вызова или окружения. Исход «уже порождён» ошибкой не является: порождённое задним
числом не правится, и повторный вызов отвечает путём лежащего файла, оставляя его неизменным.
"""

import argparse
import datetime
import pathlib
import sys

from . import FileBacklogs, FileTemplates, render, scalar
from .application import ALREADY_GENERATED, GenerateBacklogInput, GenerateBacklogUseCase

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_ENVIRONMENT = 2

STAMP_FORMAT = "%Y%m%d%H%M%S"
DATE_FORMAT = "%Y-%m-%d"


def _blocked(message):
    """Отказ по вводу: вызов составлен так, что порождать нечем."""
    print(f"Отказ: {message}", file=sys.stderr)
    raise SystemExit(EXIT_BLOCKED)


def _environment(message):
    """Отказ по окружению: дефект шаблона или каталога обнаружен до исполнения операции."""
    print(f"Ошибка окружения: {message}", file=sys.stderr)
    raise SystemExit(EXIT_ENVIRONMENT)


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
    """Разбирает вызов. Единственная подкоманда — порождение."""
    parser = argparse.ArgumentParser(
        prog="backlog",
        description="Порождение беклога операции по её шаблону.",
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
        default="backlog",
        help="Корень каталога следа; умолчание — backlog",
    )
    generate.add_argument(
        "--templates",
        default="templates",
        help="Каталог шаблонов операций; умолчание — templates",
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

    values = {
        "date": datetime.datetime.now().strftime(DATE_FORMAT),
        "run_stamp": stamp,
        "operation": operation,
        "subject": subject,
    }
    values.update(_pairs(arguments.value))
    flags = _flags(arguments.flag, arguments.no_flag)

    templates = FileTemplates(pathlib.Path(arguments.templates), _environment)
    backlogs = FileBacklogs(pathlib.Path(arguments.root), _environment)
    use_case = GenerateBacklogUseCase(
        templates=templates,
        backlogs=backlogs,
        render=lambda text, given, conditions: render(
            text, given, conditions, _environment
        ),
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


def main(argv=None):
    """Разбирает вызов и исполняет подкоманду."""
    arguments = _parse(sys.argv[1:] if argv is None else argv)
    return generate(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
