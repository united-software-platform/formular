# Подготовка изолированного окружения для инструментов рабочего пространства.
#
# Скрипт подключается обёрткой инструмента (`. "$SCRIPT_DIR/../lib/python-env.sh"`) и сам
# ничего не собирает: подключение только объявляет функции. Работу начинает вызов
# prepare_python_env — он и остаётся единственной точкой входа.
#
# Подключение выбрано вместо запуска отдельным процессом: результат подготовки — путь
# к интерпретатору окружения, и отдельный процесс вернул бы его только через стандартный
# вывод, где он смешался бы с сообщениями о сборке.
#
# Использование:
#   . "$SCRIPT_DIR/../lib/python-env.sh"
#   prepare_python_env "$VENV_DIR" "$REQUIREMENTS"
#   exec "$PYTHON_ENV_INTERPRETER" "$SCRIPT_DIR/check.py" "$@"
#
# Вход:  каталог окружения и файл зависимостей — всё, чем инструменты различаются, помимо
#        запускаемого модуля. Команда повторного прогона в диагностике берётся из "$0"
#        вызвавшей обёртки, отдельным сведением не передаётся.
# Выход: PYTHON_ENV_INTERPRETER — путь к интерпретатору собранного окружения.
# Отказ: выход с кодом 2 (ошибка окружения) и диагностикой в поток ошибок.

# Код ошибки окружения. Совпадает с кодом ошибки вызова у инструментов: нехватка окружения
# и дефект проверяемых файлов требуют разных действий, поэтому с кодом нарушений не смешивается.
PYTHON_ENV_EXIT_ENVIRONMENT=2

# Накопитель диагностики: по строке на каждый способ, отпавший или не сработавший.
python_env_reasons=""

# Причина отказа способа. Копится и печатается разом: перечень «что пробовалось и почему
# не вышло» полезен только целиком.
python_env_note() {
    python_env_reasons="$python_env_reasons  - $1
"
}

python_env_fail() {
    echo "ошибка: $1" >&2
    exit "$PYTHON_ENV_EXIT_ENVIRONMENT"
}

# Недоступность индекса пакетов отделена от нехватки средств сборки: окружение уже создано,
# и перебирать способы дальше бессмысленно — не сработает ни один.
python_env_fail_index() {
    echo "ошибка: окружение создано ($python_env_method), но зависимости не установились" >&2
    echo "  нужен доступ к индексу пакетов; файл зависимостей: $python_env_requirements" >&2
    exit "$PYTHON_ENV_EXIT_ENVIRONMENT"
}

# Перечень применимых способов в порядке убывания надёжности. Порядок фиксирован и одинаков
# на всех машинах: способ выбирается наличием инструментов, а не случайным перебором.
#
# Пробы отвечают на вопрос «применим ли способ здесь» до попытки сборки, поэтому неприменимый
# способ попадает в диагностику с внятной причиной, а не с обрывком чужого сообщения.
python_env_probe() {
    python_env_candidates=""

    if command -v uv >/dev/null 2>&1; then
        python_env_candidates="uv"
    else
        python_env_note "uv: не найден в PATH"
    fi

    if python3 -c 'import venv' >/dev/null 2>&1; then
        python_env_has_venv=1
    else
        python_env_has_venv=0
        python_env_note "venv, venv-target: модуль venv недоступен"
    fi

    if [ "$python_env_has_venv" -eq 1 ]; then
        if python3 -c 'import ensurepip' >/dev/null 2>&1; then
            python_env_candidates="$python_env_candidates venv"
        else
            python_env_note "venv: модуль ensurepip недоступен — дистрибутив выносит его в отдельный пакет"
        fi
    fi

    # Внешний pip хоста: им ставятся зависимости в окружение, созданное без pip внутри.
    python_env_pip=""
    if python3 -m pip --version >/dev/null 2>&1; then
        python_env_pip="python3 -m pip"
    elif command -v pip3 >/dev/null 2>&1; then
        python_env_pip="pip3"
    fi

    if [ "$python_env_has_venv" -eq 1 ]; then
        if [ -n "$python_env_pip" ]; then
            python_env_candidates="$python_env_candidates venv-target"
        else
            python_env_note "venv-target: внешний pip недоступен"
        fi
    fi

    # Съедает ведущий пробел, если первый способ отпал
    python_env_candidates=${python_env_candidates# }
}

# Диагностика исчерпания перечня: что пробовалось, почему отпало и чем это закрыть.
# Имя пакета собирается из действующей версии интерпретатора, а не берётся строкой:
# имя, зашитое под одну версию, устаревает молча.
python_env_no_method() {
    interpreter=$(command -v python3 2>/dev/null || echo "python3")
    retry=${0:-}

    echo "ошибка: не удалось подготовить окружение — ни один способ сборки не применим" >&2
    echo "  испробованные способы:" >&2
    printf '%s' "$python_env_reasons" >&2
    echo "  действующий python3: $python_env_version ($interpreter)" >&2
    echo "  чем закрыть — достаточно любого одного:" >&2
    echo "    sudo apt install python$python_env_version-venv   # вернуть ensurepip штатному venv" >&2
    echo "    установить uv: https://docs.astral.sh/uv/getting-started/installation/   # без прав суперпользователя" >&2
    echo "    sudo apt install python3-pip   # внешний pip для окружения без pip внутри" >&2
    if [ -n "$retry" ]; then
        echo "  повторить прогон: sh $retry" >&2
    fi
    exit "$PYTHON_ENV_EXIT_ENVIRONMENT"
}

# uv создаёт окружение, не обращаясь к ensurepip, и ставит в него зависимости, не требуя
# pip внутри. Способ ничего не предполагает о комплектации интерпретатора.
python_env_build_uv() {
    uv venv --quiet "$python_env_venv_dir" >&2 || return 1
    uv pip install --quiet --python "$python_env_venv_dir/bin/python" \
        -r "$python_env_requirements" >&2 || python_env_fail_index
}

# Штатный способ: прежнее поведение обёрток.
python_env_build_venv() {
    python3 -m venv "$python_env_venv_dir" >&2 || return 1
    "$python_env_venv_dir/bin/python" -m pip install --quiet --disable-pip-version-check \
        --upgrade pip >&2 || python_env_fail_index
    "$python_env_venv_dir/bin/python" -m pip install --quiet --disable-pip-version-check \
        -r "$python_env_requirements" >&2 || python_env_fail_index
}

# Окружение без pip внутри, зависимости ставит внешний pip хоста. Каталог назначения
# вычисляет сам интерпретатор окружения: путь зависит от версии, и угадывать его незачем.
#
# Ключ --target выбран вместо `pip --python`: последний появился в pip 23.1, и опора на него
# добавила бы определение версии внешнего pip ради того же результата. Точки входа --target
# не раскладывает — инструментам они не нужны, модуль запускается интерпретатором напрямую.
python_env_build_venv_target() {
    python3 -m venv --without-pip "$python_env_venv_dir" >&2 || return 1
    python_env_target=$("$python_env_venv_dir/bin/python" \
        -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])') || return 1
    $python_env_pip install --quiet --disable-pip-version-check \
        --target "$python_env_target" -r "$python_env_requirements" >&2 || python_env_fail_index
}

# Основание пересборки или пустая строка, если окружение пригодно как есть.
# Способ сборки входит в метку наравне с версией: окружения, собранные разными способами,
# различаются содержимым, дособрать одно другим нельзя, а молчаливое переиспользование
# даёт ошибку импорта вместо внятного сообщения.
python_env_rebuild_reason() {
    if [ ! -x "$python_env_venv_dir/bin/python" ]; then
        echo "окружения нет"
        return 0
    fi
    if [ ! -f "$python_env_mark" ]; then
        echo "метка окружения отсутствует"
        return 0
    fi

    mark_version=$(cut -d' ' -f1 < "$python_env_mark")
    mark_method=$(cut -d' ' -f2 < "$python_env_mark")

    if [ "$mark_version" != "$python_env_version" ]; then
        echo "версия python3 изменилась на $python_env_version"
        return 0
    fi
    if [ "$mark_method" != "$python_env_method" ]; then
        echo "способ сборки изменился: прежний — $mark_method"
        return 0
    fi
    echo ""
}

# Перебор применимых способов: первый сработавший останавливает перебор. Неудача способа
# перебор не прерывает и кодом возврата сама по себе не становится, пока в перечне
# остались неиспробованные способы.
python_env_build() {
    for python_env_method in $python_env_candidates; do
        echo "Сборка окружения в $python_env_venv_dir ($python_env_reason, способ: $python_env_method) ..." >&2
        rm -rf "$python_env_venv_dir"

        case "$python_env_method" in
            uv) python_env_build_uv && return 0 ;;
            venv) python_env_build_venv && return 0 ;;
            venv-target) python_env_build_venv_target && return 0 ;;
        esac

        python_env_note "$python_env_method: создать окружение не удалось"
    done

    rm -rf "$python_env_venv_dir"
    python_env_no_method
}

# Точка входа. Готовит окружение при необходимости и оставляет путь к интерпретатору
# в PYTHON_ENV_INTERPRETER.
prepare_python_env() {
    python_env_venv_dir=$1
    python_env_requirements=$2
    python_env_mark="$python_env_venv_dir/.env-mark"

    command -v python3 >/dev/null 2>&1 || python_env_fail "python3 не найден в PATH"
    [ -f "$python_env_requirements" ] \
        || python_env_fail "не найден файл зависимостей: $python_env_requirements"

    python_env_version=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])') \
        || python_env_fail "не удалось определить версию python3"

    python_env_probe
    [ -n "$python_env_candidates" ] || python_env_no_method

    # Предпочитаемый способ — первый применимый. С ним же сверяется метка: окружение,
    # собранное способом ниже по порядку, пересобирается, когда станет доступен способ выше.
    python_env_method=${python_env_candidates%% *}

    python_env_reason=$(python_env_rebuild_reason)
    if [ -n "$python_env_reason" ]; then
        python_env_build
        printf '%s %s\n' "$python_env_version" "$python_env_method" > "$python_env_mark"
    fi

    PYTHON_ENV_INTERPRETER="$python_env_venv_dir/bin/python"
}
