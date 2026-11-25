# Proposal

## Why

Разработка formular развёрнута установщиком sdd-developer-kit: агент работает в контейнере
`docker-compose.yml`, подготовку ведёт `Makefile`, правила разработки лежат установленными
копиями в `rules/`, а точка входа агентов продублирована в `CLAUDE.md` и `AGENTS.md`. Набор
выводится из разработки — ему на смену пришёл плагин `tessera` с навыками, правилами и скриптом
поставки для любого харнеса. Пока действуют обе модели, репозиторий требует Docker и образа
`ghcr.io/united-software-platform/sdd-developer-kit` для любой задачи, а копии правил молча
расходятся с источником: шесть из девяти файлов `rules/` дублируют поставку tessera, а `docker.md`
и `makefile-rules.md` описывают то, чего в окружении больше нет.

## What Changes

- **BREAKING** — `CLAUDE.md` удаляется; единственная точка входа агентов — `AGENTS.md`.
- **BREAKING** — каталог `rules/` удаляется целиком, включая три правила, которых нет в поставке
  tessera. Общие правила разработки принимает поставка tessera: скрипт
  `scripts/install.sh --scope project --components tessera,mattpocock-skills` кладёт копии в
  `.tessera/rules/` и ведёт секцию
  в `AGENTS.md`. Нормы беклога и глоссарий по-прежнему подключаются из поставки
  `plugin/backlog/share/`.
- **BREAKING** — контейнер агента уходит: удаляются `docker-compose.yml`, `.env.example`,
  `.sdd-kit-manifest.json` и `tools/host-runner/`. Разработка ведётся на хосте, в выбранном
  разработчиком харнесе.
- **BREAKING** — `Makefile` и `tools/make-lint/` удаляются. Проверки остаются командами
  `CONTRIBUTING.md`: задач окружения у репозитория нет.
- Каталоги харнесов `.agents/`, `.zcode/` и локальная часть `.claude/` становятся локальной
  настройкой и уходят из индекса; из `.claude/` снимается только `.claude/settings.json` с путём
  контейнера, а инструментация OpenSpec остаётся в индексе. Ссылки на навыки tessera ведут
  в хранилище машины.
- tessera ставится в проект составом без formular. Зависимость остаётся однонаправленной
  по продуктам: `tessera-plugin` требует `backlog`, поставка formular от tessera не зависит.
  Плагин `backlog` в харнес разработки не подключается: беклог и есть formular.
- `README.md` и `CONTRIBUTING.md` приводятся к норме документов проекта `DGN`: блок бейджей,
  «Ограничения» и «Лицензия» в `README.md`. `mise.toml` закрепляет только openspec CLI.
- Образец плагина `docs/spec/agent-plugin-blueprint/` перестаёт предполагать в целевом проекте
  набор и контейнер: допущения переформулируются под tessera и mise, правила называются кодами
  без ссылок на локальный `rules/`.
- Исследование `docs/research/import-into-other-projects.md` получает предупреждение
  о пересмотре; текст не переписывается.
- Восемь шаблонов операций раскладки workspace в `templates/` удаляются: они ставят набор
  установщиком, зовут раннер хоста и гасят окружение проектов через `docker compose down`.
  Образцом остаётся `plugin/backlog/templates/sample-operation.md`.

## Capabilities

### New Capabilities

Нет. Изменение заменяет инструментарий, структуру репозитория и документацию разработки.
Нормы окружения formular не вводит, а применяет `ENV-001`..`ENV-007` правил tessera; собственная
спецификация стала бы пересказом чужих правил.

### Modified Capabilities

Нет. Шесть возможностей `backlog/*` описывают механизм беклога; поставка `plugin/backlog/`
и её поведение не меняются.

Спецификаций изменение не несёт: `.openspec.yaml` объявляет `skip_specs: true`.

## Impact

- Удаляются `CLAUDE.md`, `rules/`, `.sdd-kit-manifest.json`, `docker-compose.yml`,
  `.env.example`, `Makefile`, `tools/` и восемь шаблонов `templates/*.md`; добавляется `mise.toml`.
- Добавляются поставкой tessera: `.tessera/rules/` — восемь копий правил, переносятся с проектом.
  Ссылки на навыки в `.agents/skills/` и `.claude/skills/` и реестр `.tessera/registry.json`
  описывают машину и остаются локальными.
- Из индекса уходит только `.claude/settings.json` — файл остаётся локальной настройкой
  разработчика; инструментация OpenSpec в `.claude/` остаётся в индексе.
- Переписываются `AGENTS.md` и `.gitignore`; правятся `CONTRIBUTING.md`, `README.md`, пять
  файлов образца плагина и предупреждение исследования.
- Не затрагиваются поставка `plugin/backlog/`, `tests/`, спецификации
  `openspec/specs/backlog/*`, `docs/use-cases.md` и `prompts/`.
- Зависимости: появляется зависимость разработки от репозитория tessera — навыки, правила
  и скрипт поставки; уходят Docker, образ `sdd-developer-kit` и установщик набора. Продуктовая
  зависимость tessera → formular не меняется.
- Совместимость: разработчику нужен харнес, читающий `AGENTS.md`; для Claude Code это версия
  не ниже 2.1.277.
