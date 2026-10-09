# Импорт функционала проекта в другие проекты

Разбор способов отдать механизм беклога операций другому проекту: инвентарь переносимого,
жёсткие предположения о раскладке, варианты поставки по первичным источникам и рекомендуемое
решение с шагами внедрения.

---

## Навигация

- [Границы исследования](#границы-исследования)
- [Инвентарь переносимого](#инвентарь-переносимого)
- [Жёсткие предположения о раскладке](#жёсткие-предположения-о-раскладке)
- [Прецедент установки: sdd-kit](#прецедент-установки-sdd-kit)
- [Варианты по первичным источникам](#варианты-по-первичным-источникам)
- [Сопоставление вариантов](#сопоставление-вариантов)
- [Рекомендуемое решение](#рекомендуемое-решение)
- [Шаги внедрения](#шаги-внедрения)
- [Что придётся изменить в коде](#что-придётся-изменить-в-коде)
- [Отклонённые альтернативы](#отклонённые-альтернативы)
- [Допущения, ограничения и риски](#допущения-ограничения-и-риски)
- [Источники](#источники)
- [Версионирование](#версионирование)

---

## Границы исследования

Исследование отвечает на вопрос «чем отдать механизм другому проекту» и не меняет код
механизма. Каждое утверждение несёт источник: URL первичной документации либо путь файла
репозитория с номером строки. Даты и версии проверены на 2026-10-09; действующая версия
Claude Code в этом окружении — `2.1.266` (вывод `claude --version`).

Каталог `openspec/changes/archive/` не читался по [READ-004](../../rules/reading-rules.md#запрет-каталогов-read-004);
история git не читалась по [GIT-019](../../rules/git-rules.md#чтение-истории).

---

## Инвентарь переносимого

Состав механизма сверен с перечнем в [`README.md`](../../README.md) (строки 32–40) и деревом
репозитория.

### Что обязано уехать в проект-потребитель

| Что | Где сейчас | Почему обязано |
|-----|-----------|----------------|
| Ядро: домен, сценарий порождения, адаптеры | `src/backlog/` | Без него порождать нечем |
| Вход командной строки | `tools/backlog/backlog.sh` | Единственная точка вызова порождения ([BKL-003](../../rules/operation-backlog-rules.md#порождение-прогоном)) |
| Сборка окружения интерпретатора | `tools/lib/python-env.sh` | Подключается входом: `tools/backlog/backlog.sh:17` |
| Носитель порядка исполнения | `.claude/skills/backlog-run/SKILL.md` | [BKL-008](../../rules/operation-backlog-rules.md#передача-исполнения) требует загрузки носителя перед первой задачей |
| Нормы беклога | `rules/operation-backlog-rules.md` | `BKL-001`..`BKL-009`; подключаются `@`-импортом из `CLAUDE.md:42` |
| Понятия | `docs/glossary.md` | Единственный источник определений по [TERM-001](../../rules/terminology.md#единый-источник-определения); подключён из `CLAUDE.md:24` |
| Описание адреса каталога следа | `backlog/README.md` | Навык ссылается на него: `.claude/skills/backlog-run/SKILL.md:54` |
| Образцовый шаблон | `templates/sample-operation.md` | Грамматика формата; рабочие шаблоны проект заводит сам |

### Что остаётся принадлежностью репозитория-источника

| Что | Где | Почему не едет |
|-----|-----|----------------|
| Проверки ядра | `tests/test_backlog.py` | Проверяют реализацию, а не применение; путь к ядру вычисляют сами: `tests/test_backlog.py:13` |
| Спецификация предмета | `openspec/specs/backlog/operation-backlog/spec.md` | Артефакт процесса разработки источника |
| Конфигурация OpenSpec | `openspec/config.yaml` | В поставку sdd-kit не входит по тому же основанию: `Makefile:127` |
| Пайплайны проверки | в репозитории отсутствуют | Прямое указание: `tools/make-lint/check.sh:15` — «Пайплайн в поставку не входит» |
| Порождённые беклоги | `backlog/sample-operation/*/tasks.md` | Принадлежат прогону, закрыты `.gitignore:12` |

### Спорная граница

Каталог следа `backlog/` переносится не содержимым, а соглашением: умолчание `--root` равно
`backlog` (`src/backlog/__main__.py:117-121`), а сами беклоги в репозиторий не попадают
(`.gitignore:12-13`). В проект-потребитель едет только `backlog/README.md` плюс пара строк
в его собственный `.gitignore`.

---

## Жёсткие предположения о раскладке

Каждое предположение ниже мешает импорту: оно верно только в этом дереве.

### Вход предполагает своё место в дереве

```sh
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPT_DIR/../lib/python-env.sh"
PACKAGE_DIR="$SCRIPT_DIR/../../src"
```

`tools/backlog/backlog.sh:15-19` — вход требует, чтобы над ним лежал `tools/lib/`, а двумя
уровнями выше — `src/`. Перенос входа в другой каталог ломает обе ссылки.

Сам `tools/lib/python-env.sh` раскладки не предполагает: каталог окружения и файл зависимостей
приходят параметрами `prepare_python_env` (`tools/lib/python-env.sh:201-204`). Относительный
путь есть только в примере использования (`tools/lib/python-env.sh:12`), и это комментарий.

### Окружение пишется в каталог поставки

`tools/backlog/backlog.sh:21` собирает venv в `$PACKAGE_DIR/.venv`, то есть внутри каталога
ядра. Для каталога, раздаваемого как поставка, это запись в неизменяемое: документация плагинов
прямо запрещает держать там состояние — «`${CLAUDE_PLUGIN_ROOT}` changes when the plugin
updates, so don't write state there» (`https://code.claude.com/docs/en/plugins/manifest-reference`).

Отягчающее обстоятельство: `src/requirements.txt` пуст по содержанию (только комментарии),
и venv сейчас не нужен вовсе — ядро обходится стандартной библиотекой
([`README.md`](../../README.md):41).

### Навык адресует нормы тремя уровнями вверх

`.claude/skills/backlog-run/SKILL.md` ссылается на нормы и на описание каталога следа путями
`../../../rules/operation-backlog-rules.md` (строки 13, 14, 21, 41, 43, 75) и
`../../../backlog/README.md` (строка 54). Это верно только пока навык лежит ровно в
`<корень>/.claude/skills/backlog-run/`. В каталоге плагина `../../../` уходит за пределы
плагина, а такой путь платформа отвергает: «a path that resolves outside the plugin root doesn't
load» (`https://code.claude.com/docs/en/plugins/loading`).

### Разрешённые прогоны навыка названы путём

```text
allowed-tools: Bash(sh tools/backlog/backlog.sh:*), Bash(python3:*), ...
```

`.claude/skills/backlog-run/SKILL.md:4` — правило разрешения записано относительным путём входа.
Любая другая раскладка оставляет навык без разрешения на вызов.

### Нормы называют вход путём

`rules/operation-backlog-rules.md:173` — в `BKL-009` прогон назван как
`sh tools/backlog/backlog.sh generate ...`. То же в `backlog/README.md:54,62`
и [`README.md`](../../README.md):48.

### Умолчания входа относительны рабочему каталогу

`src/backlog/__main__.py:117-126` задаёт `--root` = `backlog` и `--templates` = `templates`;
`src/backlog/__main__.py:152-153` превращает их в `pathlib.Path` без привязки к корню проекта.
Значит умолчания верны лишь тогда, когда прогон запущен из корня проекта. Это не дефект — корень
следа объявлен значением вызова ([BKL-002](../../rules/operation-backlog-rules.md#адрес-беклога)), —
но при импорте умолчание придётся связать с корнем проекта явно.

### Строка-указатель носителя порядка вшита в шаблон

`templates/sample-operation.md:25` и `:41-42` называют носитель порядка как
`.claude/skills/backlog-run/SKILL.md`, и это значение дословно попадает в порождённый беклог —
`backlog/sample-operation/20261008195216/tasks.md:24,41`. При поставке навыка плагином путь
становится другим (навык вызывается как `/<плагин>:backlog-run`), а порождённое задним числом
не правится по [BKL-004](../../rules/operation-backlog-rules.md#порождённое-не-правится).

### Ссылки шаблона ломаются уже сейчас

`templates/sample-operation.md:19,23,24,26` ссылается на нормы как `../rules/...` — верно
относительно каталога `templates/`. Порождённый файл лежит на три уровня ниже корня, и те же
строки в нём (`backlog/sample-operation/20261008195216/tasks.md:18,22,23,25`) указывают на
`backlog/sample-operation/rules/...`, которого нет. Дефект существует независимо от импорта,
но импорт его усугубляет: корень следа задаётся вызовом и глубина пути перестаёт быть известной.

### Точки подключения правил

`CLAUDE.md:24` (`@docs/glossary.md`) и `CLAUDE.md:42` (`@rules/operation-backlog-rules.md`) —
импорты относительны файлу, их содержащему. `AGENTS.md:20-27` ведёт тот же перечень ссылками,
но без `@`-импортов и без строки беклога: `AGENTS.md` отстал от `CLAUDE.md` по составу правил.
При импорте механизма обе точки придётся править в целевом проекте.

---

## Прецедент установки: sdd-kit

Репозиторий сам установлен внешней поставкой, и модель установки зафиксирована манифестом.

### Что несёт манифест

`.sdd-kit-manifest.json` содержит `kit_version` (`1.4.3`), `kit_ref` (`main`), `installed_at`
(`2026-10-07T22:44:35Z`) и перечень из 18 файлов, каждый с `sha256`.

Состав поставки по манифесту: `.env.example`, `AGENTS.md`, `CLAUDE.md`, `Makefile`,
`docker-compose.yml`, девять файлов `rules/`, три файла `tools/host-runner/`
и `tools/make-lint/check.sh`.

### Какую модель это задаёт

Модель читается из структуры манифеста прямо:

- поставка есть **копирование файлов в дерево целевого проекта** — иначе хранить их перечень
  незачем;
- `sha256` каждого файла даёт **обнаружение правок**: установщик видит, разошёлся ли файл
  с поставленным, и не затирает чужое изменение молча;
- `kit_version` и `kit_ref` дают **обновление**: известно, что именно установлено и откуда
  тянуть следующее.

Нормы репозитория эту модель уже отражают. `tools/make-lint/check.sh:13-16`: «Скрипт входит
в состав поставки вместе с документом rules/makefile-rules.md, который предписывает его прогон,
и работает в том проекте, где лежит: корень определяется по расположению самого скрипта».
`rules/makefile-rules.md` (назначение, строки 3–4): «Документ и проверка входят в состав
поставки: правило применимо в любом проекте, где они лежат». `rules/documentation-rules.md`
в `DOC-022` вводит исключение по типу документа для `README.md`, а `Makefile:125-127` объясняет,
почему `openspec/config.yaml` в поставку не входит.

Показательно и обратное: ни `src/`, ни `templates/`, ни `backlog/`, ни `.claude/skills/`,
ни `docs/glossary.md`, ни `rules/operation-backlog-rules.md` в манифесте нет. Механизм беклога —
собственная надстройка этого репозитория над поставленным набором, и своей модели поставки
у него пока не заведено.

### Применима ли та же модель к беклогу

Применима частично, и ровно там, где у поставки нет альтернативы.

- **Нормы, глоссарий и строки `@`-импортов** — только копированием в дерево проекта: иного
  способа подать их в контекст агента платформа не даёт (см. раздел о `@`-импортах ниже).
- **Описание каталога следа и образцовый шаблон** — копированием: целевой проект их правит
  под себя.
- **Ядро, вход и навык** — копированием тоже можно, но тогда обновление остаётся ручным
  прогоном установщика, тогда как для исполняемого кода и навыка платформа предлагает механизм
  с собственным обновлением (плагин).

Отдельное ограничение прецедента: `prepare_python_env` собирает venv внутри `src/`, а манифест
поставки файлов `src/` не знает; копирование ядра в целевой проект потребовало бы исключить
`src/.venv/` из сверки `sha256`.

### Второй прецедент: окружение поставляется образом

Рядом с файловой поставкой в репозитории живёт вторая, иной природы: **окружение агента приходит
опубликованным образом из реестра, а не исходником**.

```yaml
image: ${SDD_KIT_IMAGE:-ghcr.io/united-software-platform/sdd-developer-kit}:${SDD_KIT_IMAGE_TAG:-latest}${SDD_KIT_IMAGE_DIGEST:-}
```

`docker-compose.yml:15`, и основание названо комментарием выше (`docker-compose.yml:3-5`):
«Секции сборки здесь нет — исходник образа в поставку не входит, и описание сборки ссылалось бы
на отсутствующий файл».

Модель этой поставки складывается из трёх частей:

- **образ в реестре** — адрес, тег и digest вынесены в переменные `.env.example:1-6`, чтобы
  «закрепить конкретную версию или состав, подставить свою сборку можно в .env, не редактируя
  этот файл» (`docker-compose.yml:7-9`);
- **compose-сервис** с отдельным профилем (`docker-compose.yml:17`), чтобы `docker compose up`
  окружение агента не поднимал, и с монтированием рабочего дерева в `${PROJECT_DIR:-/app}`
  (`docker-compose.yml:20,31`);
- **нормы** `DOCK-001`..`DOCK-015` ([`rules/docker.md`](../../rules/docker.md)), которым этот
  сервис подчиняется.

Отсюда и третий путь поставки механизма, разобранный ниже наравне с остальными:
[поставка Docker-контейнером](#поставка-docker-контейнером).

### Чего в репозитории под поставку ещё нет

Ни `Makefile`, ни `docker-compose.yml` целей беклога не содержат: перечень целей —
`Makefile:8,34,46,55,65,72,84,108,131` — это `help`, `init*` и `openspec-init`.
Ни порождения, ни проверок ядра `make` не вызывает. Окружение агента — эфемерный контейнер
с смонтированным деревом проекта (`docker-compose.yml:31` — `.:${PROJECT_DIR:-/app}`)
и смонтированным каталогом аккаунта под `CLAUDE_CONFIG_DIR` (`docker-compose.yml:28,36`).
Это существенно: каталог конфигурации агента переживает перезапуск контейнера, то есть
установленный плагин не теряется, — но лежит он в `.claude-accounts/`, закрытом `.gitignore:3`,
и потому принадлежит профилю аккаунта, а не репозиторию.

---

## Варианты по первичным источникам

### Плагины и marketplace Claude Code

**Что плагин умеет поставлять.** «A Claude Code plugin is a directory of skills, agents, hooks,
MCP servers, or other components that Claude Code installs and loads as one unit»
(`https://code.claude.com/docs/en/plugins`). Стандартная раскладка перечисляет каталоги
компонентов и, что важнее для нас, два каталога произвольных файлов
(`https://code.claude.com/docs/en/plugins/manifest-reference`, раздел Standard layout):

| Каталог | Назначение по документации |
|---------|---------------------------|
| `skills/` | `One <name>/SKILL.md per skill` |
| `bin/` | `Files here are on the Bash tool's PATH while the plugin is enabled, so Claude runs them as bare commands` |
| `scripts/` | Показан в примере раскладки как «a `scripts/` folder that its hooks call» |

**Ответ на ключевой вопрос.** Да, плагин поставляет исполняемый код и произвольные файлы,
а не только Markdown. Каталог `bin/` кладётся на `PATH` инструмента Bash, то есть shell- или
Python-вход становится командой без пути. Оговорка той же страницы: «claude.ai and Cowork don't
install a plugin that has this directory» — `bin/` ограничивает плагин терминальным Claude Code.

**Как навык плагина адресует файлы рядом с собой.** Через подстановку в теле Markdown. Таблица
«Where each variable resolves» называет для компонента «Skill, command, and agent content»
поле «Anywhere in the Markdown body»; переменные —
`${CLAUDE_PLUGIN_ROOT}` («Absolute path of the plugin's installed version»),
`${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`, «created on first reference and kept
across plugin updates») и `${CLAUDE_PROJECT_DIR}` («The project root»). Там же ограничение,
решающее для нашего входа: «The variables aren't present in the environment of commands Claude
runs through the Bash tool, in the main session or in a subagent». Значит скрипт, запущенный
агентом, своего каталога из окружения не узнает и обязан вычислить его сам из `$0`.

**Запрет на выход за пределы плагина.** «Every component path must resolve inside the plugin
root and must exist»; «A path containing `..` is the usual case»
(`https://code.claude.com/docs/en/plugins/manifest-reference`).
И на уровне загрузки: «Files outside the plugin directory aren't copied, so when a script inside
a copied plugin reads a path above the plugin root, such as `../shared`, it doesn't find them»
(`https://code.claude.com/docs/en/plugins/loading`).

**Где плагин лежит на машине.** Корень — `~/.claude/plugins` (переопределяется
`CLAUDE_CODE_PLUGIN_CACHE_DIR`); установленная версия — в
`cache/<marketplace>/<plugin>/<version>/`, и «`${CLAUDE_PLUGIN_ROOT}` points at this directory»
(`https://code.claude.com/docs/en/plugins/loading`).

**Манифест.** `.claude-plugin/plugin.json`, единственное обязательное поле — `name`; манифест
вообще необязателен: «Without it, Claude Code loads the components it finds in the standard
layout». Важное предупреждение той же страницы: «A `CLAUDE.md` at the plugin root isn't loaded
as context, and `claude plugin validate` warns when it finds one. To include instructions that
load into Claude's context, put them in a skill».

**Marketplace из git-репозитория.** Каталог — `.claude-plugin/marketplace.json` с полями
`name`, `owner`, `plugins`. Источники плагина включают относительный путь внутри самого
marketplace, `github` (`owner/repo`), `url` (любой git по URL), `git-subdir` (один подкаталог
чужого репозитория, частичный клон), `npm`, `archive` и `command`
(`https://code.claude.com/docs/en/plugins/marketplace-reference`). Источники самого marketplace —
`github`, `git`, `url`, `file`, `directory`, `settings`; в настройках пишутся как
`extraKnownMarketplaces`.

**Версионирование и обновление.** «Because the manifest comes first, a manifest that pins
`"version": "1.0.0"` keeps every user on the cached copy until its author changes the string,
however many commits they push. To let users track commits instead, leave `version` out of both
the manifest and the entry» (`https://code.claude.com/docs/en/plugins/loading`). Автообновление:
после первого сообщения в интерактивной сессии — случайная задержка до десяти минут, затем
обновление плагинов из marketplace с включённым `autoUpdate`; по умолчанию он включён для
официальных marketplace Anthropic и выключен «for every other marketplace».

**Плагин, включённый репозиторием.** Два пути. Первый — `enabledPlugins` в коммитимом
`.claude/settings.json`, и у него есть прямое ограничение: «When a plugin's only `true` is in
the project's `.claude/settings.json`, Claude Code doesn't fetch it onto a machine where it isn't
installed, unless its marketplace entry has a relative-path source». Второй — положить каталог
плагина с его `.claude-plugin/plugin.json` прямо в `<project>/.claude/skills/<name>/`:
«To make a plugin load for everyone in one repository, create the same layout yourself at
`<project>/.claude/skills/<name>/`, including its `.claude-plugin/plugin.json`»
(`https://code.claude.com/docs/en/plugins/create`). Такой плагин получает origin `@skills-dir`,
загружается на месте и не копируется, но: загружается только из `.claude/skills/` первичного
рабочего каталога, требует принятия диалога доверия, и у него «Background monitors do not load»
(`https://code.claude.com/docs/en/plugins/loading`).

### Agent Skills

**Уровни.** Личные `~/.claude/skills/<skill>/SKILL.md`, проектные `.claude/skills/<skill>/SKILL.md`
(«Committed to repo, shared with team»), корпоративные в каталоге managed settings, плагинные
`<plugin>/skills/<skill>/SKILL.md` (вызов как `/plugin-name:skill-name`), вложенные
`<subdir>/.claude/skills/` и добавленные через `--add-dir`
(`https://code.claude.com/docs/en/skills`).

**Фронтматтер.** Все поля необязательны, рекомендуется только `description`. Среди полей —
`name`, `description`, `allowed-tools`, `disallowed-tools`, `disable-model-invocation`,
`user-invocable`, `argument-hint`, `arguments`, `model`, `effort`, `context`, `agent`, `paths`,
`metadata`, `license`, `compatibility`.

**Ссылки на файлы рядом.** «Skills can bundle multiple files in their directory. Use relative
paths from the skill's directory»; «When Claude reads a link to a supporting file, it loads that
file on demand — only when needed, saving token cost». Это ровно то, чем живёт `SKILL.md`
сегодня, и ровно то, что ломается при выходе за каталог навыка.

**Запуск скриптов поставки из навыка.** Можно, и для адресации есть собственная переменная:
«Use the `${CLAUDE_SKILL_DIR}` variable to reference the skill's directory regardless of where
it is installed». Доступные в содержимом навыка подстановки — `${CLAUDE_SKILL_DIR}`,
`${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}` и `${CLAUDE_PLUGIN_DATA}` (последние две —
только у плагинных навыков). Рабочий каталог внедрённых команд — «the session's current shell
directory», поэтому документация и советует писать пути через эти переменные.

### CLAUDE.md и импорты памяти

**Синтаксис и глубина.** «CLAUDE.md files can import additional files using `@path/to/import`
syntax. Imported files are expanded and loaded into context at launch alongside the CLAUDE.md
that references them»; «Both relative and absolute paths are allowed. Relative paths resolve
relative to the file containing the import, not the working directory. Imported files can
recursively import other files, with a maximum depth of four hops»
(`https://code.claude.com/docs/en/memory`).

**Пути вне репозитория.** Допустимы, но с ценой: «An import in a project-level memory file is
external when its path resolves outside your working directory... The first time Claude Code
encounters external imports in a project, it shows an approval dialog listing the files. If you
decline, the imports stay disabled and the dialog doesn't appear again». Для `~/.claude/rules/`
и `~/.claude/CLAUDE.md` диалога нет — это файлы пользователя.

**Вывод для нашего случая.** Правила, физически лежащие в каталоге плагина, подключить
`@`-импортом нельзя по трём причинам сразу: корень плагина версионный и адрес меняется при
обновлении; импорт туда внешний и требует одобрения; а `CLAUDE.md` в корне плагина платформа
как контекст не читает вовсе. Остаются два честных пути: файл норм лежит в дереве проекта
(и тогда импорт относительный), либо норма подаётся телом навыка (и тогда она не контекст
каждой сессии, а содержимое вызванного навыка).

**AGENTS.md.** Читается вместо `CLAUDE.md`, «Reading `AGENTS.md` directly requires Claude Code
v2.1.277 or later»; внутри него `@path`-импорты раскрываются. На действующей здесь `2.1.266`
прямое чтение недоступно, но при наличии `CLAUDE.md` оно и не применяется.

### MCP

**Конфигурация.** «The `.mcp.json` file is a standardized configuration file stored at your
project's root directory that enables team collaboration on MCP servers»; области — `local`
(`~/.claude.json`), `project` (`.mcp.json`, «Yes, via version control»), `user`
(`~/.claude.json`, все проекты) (`https://code.claude.com/docs/en/mcp`). Для проектной области:
«For security reasons, Claude Code prompts for approval in interactive sessions before using
project-scoped servers from `.mcp.json` files».

**Плагинные серверы.** Объявляются в `.mcp.json` корня плагина либо инлайном в `plugin.json`,
адресуются `${CLAUDE_PLUGIN_ROOT}`; имя инструмента —
`mcp__plugin_<plugin-name>_<server-name>__<tool-name>`.

**Цена.** Страница обзора плагинов называет её прямо: «Processes: MCP servers the plugin defines
run alongside each session where it's enabled, and its hooks fire at their events»
(`https://code.claude.com/docs/en/plugins`).

**Спецификация.** Действующая ревизия — `2026-07-28` (схема по ссылке
`schema/2026-07-28/schema.ts`); сервер предлагает `Resources`, `Prompts`, `Tools`; транспорт —
JSON-RPC 2.0 (`https://modelcontextprotocol.io/specification/latest`). Расширения — `Tasks`,
`Skills over MCP`, `MCP Apps` — «always opt-in and require explicit support from both client
and server».

### Упаковка Python

**Метаданные и точка входа.** `[project]` требует `name` и `version`; `[project.scripts]`
объявляет консольные команды — формат `spam-cli = "spam:main_cli"`
(`https://packaging.python.org/en/latest/guides/writing-pyproject-toml/`).

**Не-код в пакете.** `[tool.setuptools.package-data]` задаёт glob-шаблоны: «The `package_data`
argument is a dictionary that maps from package names to lists of glob patterns», и такие файлы
«neither require to be included within a MANIFEST.in file, nor require to be added by a revision
control system plugin»; `include-package-data` в `pyproject.toml` по умолчанию `true`
(`https://setuptools.pypa.io/en/latest/userguide/datafiles.html`). Чтение — через
`importlib.resources`: «It is strongly recommended that, if you are using data files, you should
use `importlib.resources` to access them».

**Доступ к ресурсам.** `importlib.resources.files()` возвращает `Traversable`, `as_file()` даёт
`pathlib.Path` через контекстный менеджер; обе добавлены в 3.9, поддержка каталога в `as_file()` —
с 3.12 (`https://docs.python.org/3/library/importlib.resources.html`). Действующий интерпретатор
окружения — 3.12.14.

**Установка инструмента.** `uvx` «invokes a tool without installing it», `uv tool install`
«installs it to a persistent environment and add it to the `PATH`»; из git —
`uvx --from git+https://github.com/httpie/cli httpie` и
`uv tool install git+https://github.com/httpie/cli`, с ветвью, тегом или коммитом через `@`
(`https://docs.astral.sh/uv/guides/tools/`). Изоляция названа прямо: «Installing a tool does not
make its modules available in the current environment». Альтернатива — pipx: «creates a separate
virtual environment for each application», «accepts any source pip supports: local directories,
wheels, and git URLs» (`https://pipx.pypa.io/stable/`).

### Вендоринг через git

**Submodule.** «A submodule is a repository embedded inside another repository. The submodule has
its own history; the repository it is embedded in is called a superproject». Суперпроект хранит
`gitlink` — «the object name of the commit that the superproject expects the submodule's working
directory to be at» — и запись в `.gitmodules`. Решающее: «When cloning or pulling a repository
containing submodules the submodules will not be checked out by default»
(`https://git-scm.com/docs/gitsubmodules`). Инициализация — `git clone --recurse-submodules`
или `git submodule update --init`; переход на свежий upstream — `--remote`
(`https://git-scm.com/docs/git-submodule`).

**Subtree.** «Subtrees allow subprojects to be included within a subdirectory of the main
project, optionally including the subproject's entire history»; «a subtree is just a subdirectory
that can be committed to, branched, and merged along with your project in any way you want».
`add` «Create the <prefix> subtree by importing its contents»; `pull` «Exactly like merge, but
parallels git pull»; `--prefix` обязателен для всех команд; `--squash` даёт «only a single commit
that contains all the differences»
(`https://raw.githubusercontent.com/git/git/master/contrib/subtree/git-subtree.adoc`).

**Разница, важная нам.** Файлы subtree лежат в собственном дереве и истории проекта-потребителя
и приезжают обычным `git clone`. Файлы submodule в рабочем дереве присутствуют, но по умолчанию
не выгружаются, и `@`-импорт на них после простого клона указывал бы в пустоту.

### Поставка Docker-контейнером

Вариант опирается на прецедент, разобранный выше: механизм отдаётся не файлами и не плагином,
а опубликованным образом. Разбор начинается с препятствия, потому что оно разводит подварианты
по пригодности раньше, чем любое их удобство.

#### Решающее препятствие: вызов из контейнера агента

Агент этого проекта работает **внутри** контейнера, и средств виртуализации у него нет.
Проверено тремя независимыми способами.

- **Сокет не смонтирован.** Перечень томов сервиса `claude` — `docker-compose.yml:30-41` —
  несёт рабочее дерево, каталог аккаунта, анонимный том профилей, ключи SSH и маскировку `.env`;
  `/var/run/docker.sock` в нём нет.
- **Инструментов нет.** `tools/host-runner/README.md:23`: «В контейнере агента нет ни `make`,
  ни `docker`: рабочее дерево смонтировано внутрь, а подготовка проекта остаётся на хосте».
  Прямая проверка в этом сеансе подтверждает: `/var/run/docker.sock` отсутствует, `docker`
  не найден в `PATH`.
- **Навык это уже учитывает.** Таблица исходов задач несёт строку «Задача хостовой части |
  Передать владельцу перечнем команд и отметить: средств виртуализации в контейнере нет»
  (`.claude/skills/backlog-run/SKILL.md:97`).

Для этого разрыва в репозитории и живёт раннер хоста. Но он разрыв **не закрывает** —
и это главный вывод подраздела.

| Свойство раннера | Где зафиксировано | Следствие для порождения беклога |
|------------------|-------------------|----------------------------------|
| Исполняет только `make <цель>` | `tools/host-runner/README.md:36` — «принимает `GET /run/{цель}`, выполняет `make {цель}` в корне репозитория» | Вызвать `docker run` напрямую нельзя |
| Белый список из трёх целей | `tools/host-runner/runner.py:32` — `ALLOWED_TARGETS = frozenset({"init", "openspec-init", "help"})` | Цели порождения в списке нет; «Любое другое имя отклоняется с кодом 400» (`tools/host-runner/README.md:127-128`) |
| Параметров не передаёт | `tools/host-runner/README.md:131-133` — «команда собирается как список `["make", цель]` и выполняется без интерпретатора команд — ни подстановка через имя цели, ни передача произвольных значений в рецепт `make` невозможны» | **Решающее**: порождение без параметров бессмысленно |
| Один запуск за раз | `tools/host-runner/README.md:134` | Долгий прогон блокирует канал |
| Канал защищён токеном и портом | `AGENT_RUNNER_PORT=11900`, `AGENT_RUNNER_URL`, `AGENT_RUNNER_TOKEN` — `.env.example:22-24`; клиент — `tools/host-runner/call.sh:18-32` | Цена: раннер на хосте, открытый порт, токен; «`AGENT_RUNNER_BIND` по умолчанию `0.0.0.0`» (`tools/host-runner/README.md:137-139`) |

Последняя строка таблицы и есть приговор двум из трёх подвариантов. Вход порождения
по построению **принимает параметры**: «Он принимает имя операции, предмет, значения подстановок
и признаки условных блоков» (`src/backlog/__main__.py:3-4`), и `--operation` объявлен
обязательным (`src/backlog/__main__.py:91`). Канал раннера параметров не несёт вовсе, поэтому
через него порождается разве что одна операция с одним зашитым набором значений — то есть
не механизм, а его имитация. Расширить канал параметрами значило бы снять ровно ту границу,
ради которой раннер и заведён вместо сокета: «одна цель `make` из фиксированного перечня вместо
доступа к Docker-сокету, который дал бы контейнеру полный контроль над хостом»
(`tools/host-runner/README.md:27-28`).

#### Подвариант 1: механизм запечён в образ окружения агента

Вход лежит на `PATH` внутри того же контейнера, где работает агент. Препятствия вызова нет
вовсе: это обычный прогон инструментом Bash, и ни плагина, ни копирования кода потребителю
не нужно — механизм приезжает вместе с обновлением образа.

Что это даёт:

- обновление механизма идёт тем же путём, что и обновление окружения, — сменой тега или digest
  в `.env` (`.env.example:1-6`), а побайтовую неизменность даёт digest: «When pulling an image
  by digest, you specify exactly which version of an image to pull. Doing so, allows you to
  'pin' an image to that version, and guarantee that the image you're using is always the same»
  (`https://docs.docker.com/reference/cli/docker/image/pull/`);
- у потребителя не остаётся ни ядра, ни входа в дереве — нечему расходиться с поставкой.

Чего не даёт:

- **Исходник образа в поставку не входит** (`docker-compose.yml:3-5`). Принять механизм в состав
  образа — решение владельца репозитория kit'а, а не этого проекта; своей версии у механизма
  больше нет, она становится версией чужого образа.
- **Навык образом не поставляется.** Положить `SKILL.md` в образ физически можно, но путь
  личных навыков — `~/.claude/skills/` — внутри контейнера совпадает с `CLAUDE_CONFIG_DIR`
  (`docker-compose.yml:28`), а этот каталог перекрыт монтированием каталога аккаунта
  (`docker-compose.yml:36`). Запечённый навык оказывается под монтированием и не виден.
- **Нормы в контекст не попадают** — по той же причине, что и у плагина: контекст агента
  собирается из файлов дерева проекта, и образ их не несёт.
- Потребитель, работающий без контейнера, механизма не получает вовсе.

#### Подвариант 2: отдельный образ механизма, разовый прогон

```bash
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/app" -w /app \
  ghcr.io/<owner>/backlog:1.0.0 generate --operation sample-operation --value target=проба
```

Опоры: `--rm` — «Automatically remove the container and its associated anonymous volumes when
it exits»; `-w` задаёт каталог прогона; `-v` монтирует каталог хоста; `-u` принимает
«Username or UID (format: `<name|uid>[:<group|gid>]`)»
(`https://docs.docker.com/reference/cli/docker/container/run/`). Аргументы после имени образа
становятся аргументами точки входа: «`CMD` should be used as a way of defining default arguments
for an `ENTRYPOINT` command» (`https://docs.docker.com/reference/dockerfile/`), то есть
`ENTRYPOINT ["backlog"]` превращает образ в команду.

Пригодность: **только прогону владельцем руками**. Агент такой вызов не выполнит по препятствию
выше, и каждое порождение становится задачей хостовой части — тем самым исходом, который навык
уже описывает как передачу владельцу (`.claude/skills/backlog-run/SKILL.md:97`). Для механизма,
чья первая задача — породить порядок работ, которым дальше пойдёт агент, это выворачивает
порядок наизнанку.

#### Подвариант 3: compose-сервис в проекте потребителя

По образцу сервиса `claude`: образ из реестра, отдельный профиль, монтирование дерева,
переменные из `.env`.

```yaml
services:
  shop-backlog:
    image: ${BACKLOG_IMAGE:-ghcr.io/owner/backlog}:${BACKLOG_IMAGE_TAG:-1.0.0}${BACKLOG_IMAGE_DIGEST:-}
    container_name: shop-backlog
    profiles: ["backlog"]
    working_dir: ${PROJECT_DIR:-/app}
    user: "${USER_ID:-1000}:${GROUP_ID:-1000}"
    environment:
      BACKLOG_ROOT: ${BACKLOG_ROOT:-backlog}
    volumes:
      - .:${PROJECT_DIR:-/app}
    networks:
      - shop-net
```

Опоры в спецификации Compose (`https://docs.docker.com/reference/compose-file/services/`):
`image` принимает форму `[<registry>/][<project>/]<image>[:<tag>|@<digest>]`; `profiles`
«defines a list of named profiles for the service to be enabled under. If unassigned, the service
is always started but if assigned, it is only started if the profile is activated» — именно это
и держит сервис в стороне от `docker compose up`; `working_dir` «overrides the container's working
directory»; `user` «overrides the user used to run the container process. The default is set by
the image»; `volumes` в короткой форме — `VOLUME:CONTAINER_PATH`. Подстановка переменных —
«Compose files use a Bash-like syntax `${VARIABLE}`», с формами `${VAR:-default}` и `${VAR-default}`
(`https://docs.docker.com/reference/compose-file/interpolation/`).

Вызов — `docker compose run --rm shop-backlog generate --operation ...`: «Runs a one-time command
against a service», причём переданная команда замещает команду сервиса, а `--rm` удаляет
контейнер по выходе; оговорка — «run starts linked services by default, unless you use the
`--no-deps` flag» (`https://docs.docker.com/reference/cli/docker/compose/run/`).

Пригодность: как и подвариант 2, **только с хоста**, и то же выворачивание порядка. В сравнении
с ним подвариант аккуратнее: версия, образ, монтирование, пользователь и переменные описаны
в файле проекта и подчиняются `DOCK-001`..`DOCK-015`, а не живут в памяти владельца. Именование
и сеть при этом обязаны следовать [DOCK-001](../../rules/docker.md#префикс-имён-dock-001002),
[DOCK-002](../../rules/docker.md#префикс-имён-dock-001002) и
[DOCK-003](../../rules/docker.md#сеть-dock-003), а `env_file` запрещён
[DOCK-004](../../rules/docker.md#переменные-окружения-dock-004-dock-009-dock-010) — значения
идут через `environment` с интерполяцией.

#### Владение порождёнными файлами

Беклог пишется в дерево проекта на хосте через bind mount, и запись на хост — штатное свойство
такого монтирования: «Bind mounts have write access to files on the host by default. One side
effect of using bind mounts is that you can change the host filesystem via processes running
in a container, including creating, modifying, or deleting important system files or directories»
(`https://docs.docker.com/engine/storage/bind-mounts/`). Отображения UID и GID та же страница
не описывает — вопрос за её рамками, и владельца файла определяет тот пользователь, под которым
идёт процесс контейнера. Задают его три места:

| Где задаётся | Формулировка источника |
|--------------|------------------------|
| `USER` в Dockerfile | «sets the user name (or UID) and optionally the user group (or GID) to use as the default user and group for the remainder of the current stage», действует на последующие `RUN`, `ENTRYPOINT`, `CMD` |
| `--user` у `docker run` | «Username or UID (format: `<name|uid>[:<group|gid>]`)» |
| `user:` у сервиса Compose | «overrides the user used to run the container process. The default is set by the image, for example Dockerfile `USER`» |

Умолчание же для копируемых в образ файлов — `root`: «Without this flag, files are created with
UID and GID of 0» (о `COPY --chown`, `https://docs.docker.com/reference/dockerfile/`). Отсюда обе
нормы репозитория: [DOCK-012](../../rules/docker.md#пользователь-контейнера-приложения-dock-012-dock-013)
требует непривилегированного пользователя, [DOCK-013](../../rules/docker.md#пользователь-контейнера-приложения-dock-012-dock-013) —
владения рабочим каталогом и внутренними файлами.

Что из этого проверяемо в репозитории: `USER_ID=1000` и `GROUP_ID=1000` объявлены
(`.env.example:19-20`) и приезжают в контейнер через `env_file: .env` (`docker-compose.yml:21`),
но ни `docker-compose.yml`, ни `Makefile` их не читают, и `user:` у сервиса `claude` не задан.
Значит пользователя определяет `USER` образа, а потребитель этих двух переменных — сам образ,
исходник которого в поставку не входит (`docker-compose.yml:3-5`). Из репозитория это
не подтверждается; зафиксировано допущением и риском ниже.

Практический вывод для подвариантов 2 и 3: пользователь прогона задаётся явно —
`-u "$(id -u):$(id -g)"` либо `user:` из `USER_ID`/`GROUP_ID`, — иначе порождённый беклог
достаётся чужому владельцу, и дописывание отметок исполнения упирается в права.

#### Реестр и приватность

Адресация — `ghcr.io/NAMESPACE/IMAGE_NAME`, где NAMESPACE есть «the name of the personal account
or organization to which you want the image to be scoped». Умолчание видимости — приватная:
«When you first publish a package, the default visibility is private»; публичный образ тянется
без учётных данных — «You can also access public container images anonymously», а приватный
требует токена «with at least `read:packages` scope»
(`https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry`).

Закрепление состава — digest, и его смысл задан спецификацией OCI: «The _digest_ property of
a Descriptor acts as a content identifier, enabling content addressability... It uniquely
identifies content by taking a collision-resistant hash of the bytes»
(`https://github.com/opencontainers/image-spec/blob/main/descriptor.md`). Цена закрепления
названа документацией Docker прямо: «Docker does therefore not pull updated versions of
an image, which may include security updates».

#### Доступность на 2026-10-09

Все названные возможности — bind mounts, `docker run` с `--rm`/`-w`/`-v`/`-u`, `docker compose run`,
атрибуты `image`/`profiles`/`volumes`/`working_dir`/`user`/`env_file`/`command` спецификации
Compose, интерполяция `${VAR:-default}`, инструкции `ENTRYPOINT`/`CMD`/`USER`/`WORKDIR`/`COPY --chown`,
закрепление образа по digest, `ghcr.io` с публичной и приватной видимостью — описаны в действующей
документации как штатные, ни одна не помечена экспериментальной или предварительной.
Относительные пути хоста в `-v` отмечены как доступные «as of Docker Engine version 23»
(`https://docs.docker.com/reference/cli/docker/container/run/`) — единственное версионное
ограничение, встреченное в этом варианте.

### Версии и экспериментальность на 2026-10-09

| Возможность | Требование | Доступна здесь (2.1.266) |
|-------------|-----------|--------------------------|
| `bin/` на `PATH` инструмента Bash | версия не названа | Да |
| `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` / `${CLAUDE_PROJECT_DIR}` | версия не названа | Да |
| Загрузка плагина из `<project>/.claude/skills/<name>/` | версия не названа | Да |
| Папка плагинов через `--plugin-dir` | v2.1.265 | Да |
| `metadata` в манифесте | v2.1.222 | Да |
| `options` в `userConfig` | v2.1.271 | Нет |
| `CLAUDE_CODE_PLUGIN_DIRS` | v2.1.280 | Нет |
| Прямое чтение `AGENTS.md` | v2.1.277 | Нет |
| Проверка MCP-записей в `claude plugin validate` | v2.1.281 | Нет |

Помечено экспериментальным: контейнер `experimental` манифеста — `themes`, `monitors`, `evals`,
«whose manifest shape may still change»; монитор «run only in interactive sessions». В MCP
расширения `Tasks`, `Skills over MCP`, `MCP Apps` объявлены опциональными и согласуемыми при
инициализации. Рекомендуемое ниже решение ни на одну экспериментальную возможность не опирается.

---

## Сопоставление вариантов

Критерии: **а** — нормы и понятия в единственном носителе и в контексте агента; **б** —
порождённые беклоги в дереве целевого проекта; **в** — шаблоны свои у каждого потребителя;
**г** — обновляемость без ручного копирования; **д** — не утяжелять зависимость, ядро на
стандартной библиотеке.

| Вариант | а | б | в | г | д |
|---------|---|---|---|---|---|
| Плагин из своего marketplace | Нет: `CLAUDE.md` плагина не контекст | Да: `${CLAUDE_PROJECT_DIR}` | Да: шаблоны остаются в проекте | Да: `claude plugin update`, авто-обновление | Да: `bin/` + stdlib |
| Плагин, вендоренный в `.claude/skills/` | Частично: нормы рядом, но импорт прописывает проект | Да | Да | Через `git subtree pull` | Да |
| Только навык проекта (`.claude/skills/`) | Да, если нормы копируются рядом | Да | Да | Нет: ручное копирование | Да |
| Пакет Python с console script | Нет | Да | Да, через `--templates` | Да: `uv tool upgrade` | Нет: требует uv или pipx на машине |
| Инструмент MCP | Нет | Да | Да | Да, вместе с плагином | Нет: процесс на сессию и токены на ход |
| `git submodule` | Нет: после клона файла может не быть | Да | Нет: правка шаблона внутри чужого модуля | `submodule update --remote` | Да |
| `git subtree` | Да: файлы в дереве и истории проекта | Да | Да | `git subtree pull` | Да |
| Механизм запечён в образ окружения агента | Нет: образ файлов дерева не несёт, а навык под монтированием `CLAUDE_CONFIG_DIR` не виден | Да: bind mount пишет в дерево хоста | Да | Да, но версией чужого образа | Да: вход уже на `PATH` |
| Отдельный образ механизма, `docker run` | Нет | Да | Да | Да: тег или digest в `.env` | Нет: требует docker и прогона с хоста |
| Compose-сервис с профилем у потребителя | Нет | Да | Да | Да: тег или digest в `.env` | Нет: требует docker и прогона с хоста |
| Копирование по манифесту (модель sdd-kit) | Да | Да | Да | Нет: прогон установщика руками | Да |

Читается это так: ни один вариант не закрывает все пять критериев, и разлом проходит ровно
по критерию **а**. Docker его не закрывает в принципе: контекст агента собирается из файлов
дерева проекта, образ таких файлов не несёт, а запечённый в образ навык перекрыт монтированием
каталога аккаунта (`docker-compose.yml:28,36`). Нормы остаются файлами дерева проекта при любом
подварианте Docker-поставки. Нормы обязаны лежать в дереве проекта — платформа иного способа подать их
в контекст не даёт. Всё остальное — исполняемый код, навык, образцовый шаблон — удобнее отдавать
механизмом с собственным обновлением.

---

## Рекомендуемое решение

**Разделить поставку на два носителя по природе ограничения: механизм — плагином Claude Code
из своего marketplace в этом репозитории; нормы, понятия, точки подключения, каталог шаблонов
и каталог следа — установочным прогоном в дерево целевого проекта по модели
`.sdd-kit-manifest.json`.**

### Состав плагина

```text
plugin/backlog/
├── .claude-plugin/
│   └── plugin.json          name: backlog, version: X.Y.Z
├── bin/
│   └── backlog              вход: на PATH инструмента Bash
├── src/
│   └── backlog/             ядро: домен, сценарий, адаптеры
├── lib/
│   └── python-env.sh        сборка окружения, когда появится зависимость
├── skills/
│   └── backlog-run/
│       └── SKILL.md         носитель порядка исполнения
└── templates/
    └── sample-operation.md  образец грамматики, не рабочий шаблон
```

Основания состава, по порядку:

- `bin/backlog` — «Files here are on the Bash tool's `PATH` while the plugin is enabled»,
  поэтому агент вызывает `backlog generate ...` без пути, и разрешение навыка записывается
  как `Bash(backlog:*)` вместо пути из `.claude/skills/backlog-run/SKILL.md:4`;
- `src/` и `lib/` внутри плагина — потому что «Files outside the plugin directory aren't
  copied»: ядро обязано лежать под корнем плагина;
- `skills/backlog-run/` — плагинный навык, вызов `/backlog:backlog-run`, ссылки на нормы через
  `${CLAUDE_PROJECT_DIR}` (подстановка разрешается «Anywhere in the Markdown body»);
- `templates/sample-operation.md` остаётся в плагине только образцом; рабочие шаблоны операций
  живут в целевом проекте, и `--templates` по умолчанию смотрит туда.

### Состав установочного прогона в целевой проект

| Файл в целевом проекте | Откуда | Зачем именно копией |
|------------------------|--------|---------------------|
| `rules/operation-backlog-rules.md` | поставка | `@`-импорт обязан быть относительным файлу, его содержащему |
| `docs/glossary.md` (или раздел в нём) | поставка | Единственный источник определений по [TERM-001](../../rules/terminology.md#единый-источник-определения) |
| Строки `@`-импортов в `CLAUDE.md` и `AGENTS.md` | правка | Точка подключения норм в контекст агента |
| `templates/` с образцом | поставка | Шаблоны — свои у каждого потребителя |
| `backlog/README.md` и строки `.gitignore` | поставка | Адрес каталога следа и запрет коммитить прогоны |
| `.backlog-manifest.json` | порождается | `kit_version`-подобные поля и `sha256` для обновления и обнаружения правок |

### Почему именно так

- Критерий **а** закрыт единственным возможным способом: нормы лежат в дереве проекта, импорт
  относительный, диалога одобрения внешних импортов нет. Единственность носителя сохранена —
  навык плагина не пересказывает норму, а адресует её через `${CLAUDE_PROJECT_DIR}`, как
  требует [BKL-008](../../rules/operation-backlog-rules.md#передача-исполнения).
- Критерий **б** закрыт умолчанием `--root`, привязанным к корню проекта, а не к каталогу
  плагина: «`${CLAUDE_PLUGIN_ROOT}` changes when the plugin updates, so don't write state there».
- Критерий **в** закрыт тем, что шаблоны в плагин не входят рабочим составом: «механизм порождения
  один на все операции, а шаблон свой у каждой» ([BKL-003](../../rules/operation-backlog-rules.md#порождение-прогоном)).
- Критерий **г** закрыт для механизма (обновление плагина) и остаётся прогоном установщика
  для норм — то есть ровно для того состава, который целевой проект и так правит под себя
  и которому молчаливое затирание противопоказано.
- Критерий **д** закрыт: ни индекса пакетов, ни `uv`, ни `pipx` решение не требует. Пока
  `src/requirements.txt` пуст, `bin/backlog` запускает `python3 -m backlog` напрямую.

### Путь распространения

Marketplace — в этом же репозитории: `.claude-plugin/marketplace.json` в корне, запись с
относительным путём `./plugin/backlog`. Относительный путь выбран намеренно: он единственный,
при котором плагин, включённый коммитимым `.claude/settings.json` целевого проекта, доустановится
сам — «unless its marketplace entry has a relative-path source». Для проектов, которым нужен
только беклог и не нужен весь репозиторий, та же запись дублируется источником `git-subdir`
с `path: plugin/backlog` — частичный клон подкаталога.

Версию плагина фиксировать в манифесте: «a manifest that pins `"version": "1.0.0"` keeps every
user on the cached copy until its author changes the string». Иначе каждый коммит в `main`
станет новой версией у всех потребителей.

### Чем Docker-вариант вывод меняет и чего не меняет

Вывод не меняется: рекомендация остаётся «плагин для механизма плюс установочный прогон для норм».
Проверено по трём вопросам, которые Docker-вариант ставит.

**Вытесняет ли «запечь механизм в образ окружения агента» рекомендованный плагин?** Нет,
по четырём причинам, каждая из которых самостоятельна:

- **Версия.** Плагин несёт свою версию в своём манифесте, и она меняется осознанно. Запечённый
  механизм версии не имеет — он получает версию чужого образа, собираемого чужим пайплайном
  (`docker-compose.yml:3-5`).
- **Навык.** Образ носителем компонентов Claude Code не является: путь личных навыков внутри
  контейнера совпадает с `CLAUDE_CONFIG_DIR` (`docker-compose.yml:28`), перекрытым монтированием
  каталога аккаунта (`docker-compose.yml:36`). Плагин же поставляет навык штатно, и тот
  вызывается как `/backlog:backlog-run`.
- **Разрешения прогонов.** `allowed-tools` навыка — его собственный фронтматтер
  (`https://code.claude.com/docs/en/skills`); образ такого объявления не несёт и нести не может.
- **Потребитель без контейнера.** Плагин работает всюду, где работает Claude Code; запечённый
  механизм — только внутри этого образа.

**Вытесняет ли Docker отклонённый «пакет Python для CI и прогонов вне агента»?** Да, и здесь
вывод правится. Для прогонов вне агента образ с закреплённым digest даёт побайтово тот же
состав — «guarantee that the image you're using is always the same»
(`https://docs.docker.com/reference/cli/docker/image/pull/`), — тогда как `uv tool install
git+...` зависит и от наличия `uv` на машине, и от доступности индекса пакетов. Поэтому
дополнением к рекомендации для CI назван образ механизма (подвариант 2), а не пакет Python;
соответствующая строка отклонённых альтернатив переформулирована.

**Становится ли Docker-вариант частью рекомендации?** Частично и с оговоркой. Подварианты 2 и 3
остаются **прогоном владельца и CI**, а не прогоном агента: препятствие вызова из контейнера
непреодолимо без расширения канала раннера параметрами, то есть без снятия той самой границы,
ради которой раннер заведён (`tools/host-runner/README.md:27-28,131-133`). Подвариант 1 в состав
рекомендации не входит, потому что решается не здесь: он требует принять механизм в состав
чужого образа. Если это однажды произойдёт, плагину останется навык, а вход окажется на `PATH`
и без него, — и рекомендация упростится, не перевернувшись.

---

## Шаги внедрения

1. Завести каталог `plugin/backlog/` с `.claude-plugin/plugin.json` (`name`, `version`,
   `description`, `author`, `license`) и проверить `claude plugin validate ./plugin/backlog`
   до нуля ошибок и предупреждений (`--strict`).
2. Перенести ядро в `plugin/backlog/src/backlog/`, вход — в `plugin/backlog/bin/backlog`,
   сборку окружения — в `plugin/backlog/lib/python-env.sh`. Проверки ядра оставить в `tests/`
   источника, направив их на новый путь.
3. Развязать пути входа (см. следующий раздел) и прогнать порождение из каталога, не являющегося
   корнем репозитория, — это и есть проверка развязки.
4. Перенести навык в `plugin/backlog/skills/backlog-run/SKILL.md`, заменив `allowed-tools`
   на `Bash(backlog:*)` и ссылки `../../../` на `${CLAUDE_PROJECT_DIR}/...`.
5. Завести `.claude-plugin/marketplace.json` в корне репозитория с записью
   `{"name": "backlog", "source": "./plugin/backlog"}`.
6. Завести установочный прогон (`tools/backlog-install/install.sh` либо цель `Makefile`
   в пределах нормы 30 строк по [MAKE-001](../../rules/makefile-rules.md#норма-объёма-секции-make-001)),
   который копирует нормы, глоссарий, образцовый шаблон, `backlog/README.md`, дописывает строки
   `@`-импортов и `.gitignore` и пишет `.backlog-manifest.json` с `sha256` каждого файла.
7. Описать в [`README.md`](../../README.md) два прогона потребителя: `claude plugin marketplace add`
   плюс `claude plugin install backlog@backlog`, затем установочный прогон норм.
8. Проверить полный цикл на пустом репозитории-потребителе: установка, `/backlog:backlog-run`,
   порождение беклога в `<проект>/backlog/...`, повторный прогон установщика без изменений
   (должен ничего не затереть), прогон после правки нормы в потребителе (должен сообщить
   расхождение `sha256`, а не перезаписать).
9. Прогнать `sh tools/make-lint/check.sh` по [MAKE-004](../../rules/makefile-rules.md#локальный-прогон-проверки-make-004),
   если `Makefile` затронут.

---

## Что придётся изменить в коде

### Вход находит ядро сам

Переменные плагина недоступны прогону через инструмент Bash, поэтому вход обязан вычислить
свой корень из `$0`:

```sh
#!/bin/sh
set -eu

SELF=$(command -v "$0" 2>/dev/null || printf '%s' "$0")
ROOT=$(cd "$(dirname "$SELF")/.." && pwd)   # корень плагина, где лежат src/ и lib/

PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

exec python3 -m backlog "$@"
```

Приём не нов для репозитория: так же устроен `tools/make-lint/check.sh:20-22` —
`SCRIPT_DIR`, затем `ROOT` двумя уровнями выше. Разница одна: здесь путь приходит через `PATH`,
поэтому `$0` может быть именем команды, и его надо разрешить `command -v`.

### Окружение не пишется в каталог поставки

Пока `src/requirements.txt` пуст, venv не собирается вовсе — `prepare_python_env` не вызывается.
Когда первая зависимость появится, каталог окружения берётся не из каталога плагина:
`${CLAUDE_PLUGIN_DATA}` («kept across plugin updates»), если переменная задана, иначе
`${XDG_CACHE_HOME:-$HOME/.cache}/backlog/venv`. Параметры `prepare_python_env` для этого уже
годятся — он принимает каталог окружения аргументом (`tools/lib/python-env.sh:201-204`),
и править его не нужно.

### Корень следа и каталог шаблонов привязаны к проекту

`src/backlog/__main__.py:117-126` оставить как есть по смыслу, но умолчания вычислять от корня
проекта, а не от рабочего каталога: читать `BACKLOG_ROOT` и `BACKLOG_TEMPLATES` из окружения,
при их отсутствии — `CLAUDE_PROJECT_DIR`, и только затем `$PWD`. Вход плагина эти переменные
выставляет сам, а норма [BKL-002](../../rules/operation-backlog-rules.md#адрес-беклога) —
«корень каталога следа есть значение вызова, а не константа кода» — соблюдается тем же способом,
что и сейчас.

### Навык ссылается на нормы через корень проекта

Семь ссылок `../../../` в `.claude/skills/backlog-run/SKILL.md` (строки 13, 14, 21, 41, 43, 54,
75) заменяются на `${CLAUDE_PROJECT_DIR}/rules/operation-backlog-rules.md` и
`${CLAUDE_PROJECT_DIR}/backlog/README.md`. Подстановка разрешается платформой в теле Markdown,
а запрет на выход за пределы плагина обойдён не хитростью, а тем, что цель ссылки действительно
лежит в проекте.

`allowed-tools` (`.claude/skills/backlog-run/SKILL.md:4`) приводится к
`Bash(backlog:*), Bash(python3:*), Bash(git:*), Bash(grep:*), Read, Edit, Write`.

### Указатель носителя порядка становится подстановкой

`templates/sample-operation.md:25,41-42` вшивает `.claude/skills/backlog-run/SKILL.md`. Значение
заменяется подстановкой `{{runner}}`, которую вход заполняет сам: для плагинной поставки —
именем навыка `/backlog:backlog-run`, для проектной — путём `.claude/skills/backlog-run/SKILL.md`.
Так [BKL-008](../../rules/operation-backlog-rules.md#передача-исполнения) продолжает называть
носитель порядка адресуемо, не зная способа поставки.

### Ссылки шаблона на нормы перестают быть относительными

`templates/sample-operation.md:19,23,24,26` в порождённом файле указывают в пустоту (см. раздел
о жёстких предположениях). В шаблоне остаётся либо код правила без ссылки (`BKL-005`), либо
подстановка `{{rules}}`, значение которой вход вычисляет от корня следа до корня проекта.
Это правка шаблона, а не порождённых файлов: лежащие беклоги задним числом не правятся.

### Нормы называют вход новым именем

`rules/operation-backlog-rules.md:173` (`BKL-009`), `backlog/README.md:54,62` и
[`README.md`](../../README.md):48 приводятся к `backlog generate ...`. Правка документов —
отдельная от правки кода, и каждая требует записи в таблицу версий по
[DOC-022](../../rules/documentation-rules.md#жизненный-цикл-документа).

---

## Отклонённые альтернативы

| Вариант | Причина отказа |
|---------|----------------|
| Только плагин, без установочного прогона | Нормы в контекст не попадут: `CLAUDE.md` корня плагина как контекст не читается, а `@`-импорт в версионный каталог плагина внешний и требует одобрения |
| Только копирование по модели sdd-kit, без плагина | Обновление исполняемого кода остаётся ручным прогоном; платформа даёт для этого готовый механизм, и отказ от него ничего не покупает |
| Пакет Python с console script (`uv tool install git+...`) | Добавляет требование `uv` или `pipx` на каждой машине и второй путь обновления — критерий **д**. Для прогонов вне агента вытеснен образом механизма: digest даёт побайтово тот же состав, а пакет зависит от наличия `uv` и от индекса пакетов |
| Порождение беклога инструментом MCP | Процесс на каждую сессию, где плагин включён, и токены описаний на каждый ход, тогда как порождение есть однократная запись файла, которую агент делает инструментом Bash. Проектная область ещё и требует подтверждения в интерактивной сессии |
| `git submodule` | «the submodules will not be checked out by default»: после обычного клона `@`-импорт нормы указывал бы в пустоту. Шаблоны внутри чужого модуля потребитель править не может |
| Механизм, запечённый в образ окружения агента, вместо плагина | Версия механизма становится версией чужого образа, собираемого чужим пайплайном (`docker-compose.yml:3-5`); навык, положенный в образ, перекрыт монтированием каталога аккаунта (`docker-compose.yml:28,36`); `allowed-tools` образ не несёт; потребитель без контейнера механизма не получает. Остаётся возможным дополнением, но решается владельцем образа, а не этим проектом |
| Отдельный образ механизма как основной путь | Агент вызвать его не может: ни `docker`, ни сокета в контейнере нет (`tools/host-runner/README.md:23`, `docker-compose.yml:30-41`), а раннер хоста исполняет только `make` из белого списка и параметров не передаёт (`tools/host-runner/runner.py:32`, `tools/host-runner/README.md:131-133`). Каждое порождение становилось бы задачей хостовой части. Принят дополнением для CI и прогонов владельца |
| Compose-сервис механизма как основной путь | То же препятствие вызова, что и у отдельного образа. Аккуратнее его тем, что версия и прогон описаны файлом проекта, поэтому принят той же ролью — дополнением, не основным путём |
| Расширить канал раннера параметрами ради вызова `docker run` из контейнера | Снимает границу, ради которой раннер заведён вместо сокета: «одна цель `make` из фиксированного перечня вместо доступа к Docker-сокету, который дал бы контейнеру полный контроль над хостом» (`tools/host-runner/README.md:27-28`) |
| `git subtree` как основной путь | Файлы в дереве и истории проекта — это плюс, но обновление идёт `git subtree pull` на каждом потребителе и приносит чужие коммиты в его историю. Оставлен резервным путём для проектов без доступа к marketplace |
| Навык в `~/.claude/skills/` и нормы в `~/.claude/rules/` | Диалога одобрения нет, обновление простое, но носитель уходит из репозитория: его не версионирует проект и не видит коллега |

Резервный путь зафиксирован явно: проект, которому marketplace недоступен, вендорит тот же
каталог плагина в `<project>/.claude/skills/backlog/` через `git subtree add --prefix`.
Плагин при этом загружается на месте с origin `@skills-dir`; состав файлов и развязка путей
остаются теми же, меняется только способ доставки и обновления.

---

## Допущения, ограничения и риски

### Допущения

- Потребитель работает в терминальном Claude Code. Каталог `bin/` этого требует прямо:
  «claude.ai and Cowork don't install a plugin that has this directory».
- У потребителя есть `python3`. Это и сейчас так: `prepare_python_env` падает кодом `2`
  без него (`tools/lib/python-env.sh:206`).
- Корень проекта совпадает с первичным рабочим каталогом сессии. Иначе `${CLAUDE_PROJECT_DIR}`
  и умолчания `--root` укажут не туда, а для `@skills-dir`-поставки плагин вообще не загрузится:
  «If you launch from a subdirectory, a plugin at the repository root doesn't load».
- Версии платформы у потребителя не ниже той, что требует использованная возможность.
  Рекомендуемый состав ни одной возможности выше `2.1.265` не требует.
- Пользователь контейнера окружения агента непривилегирован и совпадает по UID с владельцем
  рабочего дерева. Из репозитория это не подтверждается: `USER_ID`/`GROUP_ID` объявлены
  (`.env.example:19-20`) и приезжают через `env_file: .env` (`docker-compose.yml:21`),
  но `user:` у сервиса `claude` не задан, и потребителем переменных остаётся сам образ,
  исходник которого в поставку не входит (`docker-compose.yml:3-5`).
- Для дополнений Docker-поставки у владельца и в CI есть docker. В контейнере агента его
  нет, и допущение на агента не распространяется (`tools/host-runner/README.md:23`).

### Ограничения

- Полная единственность носителя недостижима: нормы обязаны лежать в дереве потребителя,
  а механизм — в каталоге плагина. Единственность сохраняется внутри каждого состава
  (одна копия норм, один навык), но поставка остаётся двухчастной.
- Обновление норм остаётся прогоном установщика. Автоматического обновления файлов в дереве
  проекта платформа не предлагает, а затирать правки потребителя нельзя.
- Плагин устанавливается на машину и профиль аккаунта, а не в репозиторий. В этом окружении
  каталог конфигурации монтируется из `.claude-accounts/<профиль>` (`docker-compose.yml:28,36`),
  закрытого `.gitignore:3`: каждый профиль ставит плагин заново.
- Образцовый шаблон в плагине остаётся примером грамматики. Рабочий шаблон операции потребитель
  пишет сам, и проверить его состав поставка не может — только прогон порождения
  ([BKL-009](../../rules/operation-backlog-rules.md#прогон-при-правке-шаблона)).
- Образ как носитель механизма потребителю не правится: он получает слои, а не исходник, —
  и точка правки остаётся в репозитории-источнике. Для поставки это свойство, а не дефект,
  но оно исключает локальную заплатку, доступную при файловой поставке.
- Порождение беклога из контейнера агента через Docker недостижимо ни одним подвариантом:
  канал раннера исполняет `make` из белого списка и параметров не передаёт
  (`tools/host-runner/runner.py:32`, `tools/host-runner/README.md:131-133`), а вход
  порождения параметры требует (`src/backlog/__main__.py:91`).
- Нормы в контекст агента Docker не подаёт ни при каком подварианте: запечённый в образ
  навык перекрыт монтированием каталога аккаунта поверх `CLAUDE_CONFIG_DIR`
  (`docker-compose.yml:28,36`).

### Риски

| Риск | Чем вызван | Чем снижается |
|------|-----------|---------------|
| Плагин включён `.claude/settings.json`, но не установлен на машине коллеги | «Claude Code doesn't fetch it onto a machine where it isn't installed, unless its marketplace entry has a relative-path source» | Запись marketplace с относительным путём; инструкция установки в `README.md` потребителя |
| Каждый коммит источника становится новой версией у всех | Без `version` версией становится SHA коммита | `version` в манифесте плагина, меняемая осознанно |
| Авто-обновление молча меняет поведение механизма посреди работы | «Plugin updated: <name> · Run /reload-plugins to apply» | Для сторонних marketplace `autoUpdate` выключен по умолчанию; не включать его |
| Нормы в потребителе разошлись с поставкой | Потребитель правит файл, установщик обновляет | `sha256` каждого файла в `.backlog-manifest.json`: расхождение называется, а не затирается |
| Указатель носителя порядка в лежащих беклогах устарел | Порождённое задним числом не правится ([BKL-004](../../rules/operation-backlog-rules.md#порождённое-не-правится)) | Это не дефект: `backlog/README.md:65-71` уже фиксирует, что в исполненных беклогах остаются имена снятых инструментов |
| Запись venv в каталог плагина при появлении первой зависимости | Действующий `tools/backlog/backlog.sh:21` пишет в `src/.venv` | Каталог окружения переносится в `${CLAUDE_PLUGIN_DATA}` до появления первой зависимости, а не после |
| Тег образа переставлен, и состав механизма сменился молча | «When using tags, you can `docker pull` an image again to make sure you have the most up-to-date version of that image» | Закрепление digest, как это уже сделано для окружения: `SDD_KIT_IMAGE_DIGEST` (`.env.example:4-6`) |
| Digest закреплён, и обновления безопасности не приходят | «Docker does therefore not pull updated versions of an image, which may include security updates» | Пересмотр закреплённого digest по расписанию проекта-потребителя |
| Образ приватен, и потребитель его не тянет | «When you first publish a package, the default visibility is private» | Публичная видимость либо токен «with at least `read:packages` scope» в инструкции установки |
| Порождённый беклог достался чужому владельцу | Владельца задаёт пользователь процесса контейнера; умолчание для копируемых в образ файлов — UID 0 | Явный `-u "$(id -u):$(id -g)"` либо `user:` из `USER_ID`/`GROUP_ID`; нормы [DOCK-012](../../rules/docker.md#пользователь-контейнера-приложения-dock-012-dock-013) и [DOCK-013](../../rules/docker.md#пользователь-контейнера-приложения-dock-012-dock-013) |
| У потребителя нет docker, и дополнение неприменимо | Docker-подварианты требуют его на хосте | Основной путь — плагин, docker не требующий; Docker-поставка остаётся дополнением |
| Попытка дать агенту `docker` расширением канала раннера | Соблазн закрыть препятствие вызова | Запрет назван прямо: канал заведён «вместо доступа к Docker-сокету, который дал бы контейнеру полный контроль над хостом» (`tools/host-runner/README.md:27-28`) |
| Диалог доверия не принят, и `@skills-dir`-плагин не загружен | Проектный плагин требует «workspace trust dialog» | Основной путь — marketplace, где диалога доверия нет; резервный путь документируется с этой оговоркой |

---

## Источники

Ссылки даны текстом по [DOC-015](../../rules/documentation-rules.md#ссылки-doc-015): URL —
инлайн-кодом, не Markdown-ссылкой.

| Источник | URL |
|----------|-----|
| Claude Code: обзор плагинов | `https://code.claude.com/docs/en/plugins` |
| Claude Code: справочник манифеста плагина | `https://code.claude.com/docs/en/plugins/manifest-reference` |
| Claude Code: справочник загрузки плагинов | `https://code.claude.com/docs/en/plugins/loading` |
| Claude Code: справочник marketplace | `https://code.claude.com/docs/en/plugins/marketplace-reference` |
| Claude Code: создание плагина | `https://code.claude.com/docs/en/plugins/create` |
| Claude Code: Agent Skills | `https://code.claude.com/docs/en/skills` |
| Claude Code: память и `@`-импорты | `https://code.claude.com/docs/en/memory` |
| Claude Code: MCP-серверы | `https://code.claude.com/docs/en/mcp` |
| Спецификация MCP, ревизия 2026-07-28 | `https://modelcontextprotocol.io/specification/latest` |
| Python Packaging: `pyproject.toml` и PEP 621 | `https://packaging.python.org/en/latest/guides/writing-pyproject-toml/` |
| setuptools: файлы данных в пакете | `https://setuptools.pypa.io/en/latest/userguide/datafiles.html` |
| Python: `importlib.resources` | `https://docs.python.org/3/library/importlib.resources.html` |
| uv: инструменты, `uvx` и `uv tool install` | `https://docs.astral.sh/uv/guides/tools/` |
| pipx | `https://pipx.pypa.io/stable/` |
| git: `gitsubmodules` | `https://git-scm.com/docs/gitsubmodules` |
| Docker: bind mounts | `https://docs.docker.com/engine/storage/bind-mounts/` |
| Docker: `docker run` | `https://docs.docker.com/reference/cli/docker/container/run/` |
| Docker: `docker image pull` (закрепление по digest) | `https://docs.docker.com/reference/cli/docker/image/pull/` |
| Docker: `docker compose run` | `https://docs.docker.com/reference/cli/docker/compose/run/` |
| Compose: атрибуты сервиса | `https://docs.docker.com/reference/compose-file/services/` |
| Compose: интерполяция переменных | `https://docs.docker.com/reference/compose-file/interpolation/` |
| Dockerfile reference | `https://docs.docker.com/reference/dockerfile/` |
| OCI Image Spec: дескриптор и digest | `https://github.com/opencontainers/image-spec/blob/main/descriptor.md` |
| GitHub Container Registry | `https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry` |
| git: `git-submodule` | `https://git-scm.com/docs/git-submodule` |
| git: `git-subtree` (документация из поставки git) | `https://raw.githubusercontent.com/git/git/master/contrib/subtree/git-subtree.adoc` |

Файлы репозитория, на которые опираются утверждения: [`README.md`](../../README.md),
[`CLAUDE.md`](../../CLAUDE.md), [`AGENTS.md`](../../AGENTS.md), [`Makefile`](../../Makefile),
[`docker-compose.yml`](../../docker-compose.yml), [`.env.example`](../../.env.example),
[`.gitignore`](../../.gitignore),
[`.sdd-kit-manifest.json`](../../.sdd-kit-manifest.json),
[`rules/operation-backlog-rules.md`](../../rules/operation-backlog-rules.md),
[`rules/makefile-rules.md`](../../rules/makefile-rules.md),
[`rules/docker.md`](../../rules/docker.md),
[`tools/host-runner/README.md`](../../tools/host-runner/README.md),
[`tools/host-runner/runner.py`](../../tools/host-runner/runner.py),
[`tools/host-runner/call.sh`](../../tools/host-runner/call.sh),
[`docs/glossary.md`](../glossary.md),
[`src/backlog/__main__.py`](../../src/backlog/__main__.py),
[`src/backlog/infrastructure.py`](../../src/backlog/infrastructure.py),
[`tools/backlog/backlog.sh`](../../tools/backlog/backlog.sh),
[`tools/lib/python-env.sh`](../../tools/lib/python-env.sh),
[`tools/make-lint/check.sh`](../../tools/make-lint/check.sh),
[`templates/sample-operation.md`](../../templates/sample-operation.md),
[`backlog/README.md`](../../backlog/README.md),
[`.claude/skills/backlog-run/SKILL.md`](../../.claude/skills/backlog-run/SKILL.md),
[`tests/test_backlog.py`](../../tests/test_backlog.py).

---

## Версионирование

| Версия | Дата | Задача | Агент | Модель | Описание изменений |
|--------|------|--------|-------|--------|--------------------|
| 1.0.0 | 2026-10-09 | Исследование: импорт функционала проекта в другие проекты | Claude Code | Claude Opus 5 | Начальное создание: инвентарь переносимого и остающегося источнику, восемь жёстких предположений о раскладке с файлом и строкой, разбор прецедента установки `.sdd-kit-manifest.json`, семь вариантов поставки по первичным источникам (плагины и marketplace Claude Code, Agent Skills, `@`-импорты памяти, MCP, упаковка Python, `git submodule`, `git subtree`) с таблицей доступности возможностей на версии `2.1.266`, сопоставление по пяти критериям проекта, рекомендуемое решение «плагин для механизма плюс установочный прогон для норм и точек подключения», девять шагов внедрения, шесть правок кода с развязкой путей входа и адресации навыка, семь отклонённых альтернатив с причинами, допущения, ограничения и семь рисков |
| 1.0.1 | 2026-10-09 | Исследование: добавить вариант поставки через Docker-контейнер | Claude Code | Claude Opus 5 | Добавлен вариант «Поставка Docker-контейнером» с тремя подвариантами (механизм запечён в образ окружения агента, отдельный образ разового прогона, compose-сервис с профилем), разбором решающего препятствия — вызова из контейнера агента через раннер хоста, — владения порождёнными файлами при bind mount, реестра и приватности образа и доступности возможностей на 2026-10-09. В раздел о прецеденте установки добавлен второй прецедент: окружение агента поставляется опубликованным образом (`docker-compose.yml:15`, `.env.example:1-6`). Таблица сопоставления дополнена тремя строками, вывод таблицы — прямым утверждением, что критерий «нормы в контексте» Docker не закрывает ни при каком подварианте. Рекомендация по сути не изменилась — плагин для механизма плюс установочный прогон для норм, — и для неё добавлен подраздел с разбором трёх вопросов, которые Docker-вариант ставит; изменилось одно: дополнением для CI и прогонов вне агента назван образ механизма вместо пакета Python, и строка отклонённых альтернатив о пакете переформулирована. В отклонённые добавлены четыре строки, в допущения — две, в ограничения — три, в риски — шесть. Источники дополнены девятью первичными документами Docker, OCI и GHCR |
