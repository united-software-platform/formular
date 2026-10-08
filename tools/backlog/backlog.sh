#!/bin/sh
# Вход командной строки порождения беклогов операций.
#
# Одна точка на все операции: вход операций не знает, а шаблон у каждой свой. Подкоманда
# одна — generate; состав вызова называет `sh tools/backlog/backlog.sh generate --help`.
#
# Окружение собирается рядом с пакетом общим tools/lib/python-env.sh. Зависимостей у ядра
# нет, и файл зависимостей пуст — окружение готово к первой, которой пока не появилось.
#
# Коды возврата совпадают с кодами модуля: 0 — беклог порождён либо уже лежал,
# 1 — ввод не позволяет породить, 2 — ошибка вызова или окружения.

set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

. "$SCRIPT_DIR/../lib/python-env.sh"

PACKAGE_DIR="$SCRIPT_DIR/../../src"

prepare_python_env "$PACKAGE_DIR/.venv" "$PACKAGE_DIR/requirements.txt"

PYTHONPATH="$PACKAGE_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

exec "$PYTHON_ENV_INTERPRETER" -m backlog "$@"
