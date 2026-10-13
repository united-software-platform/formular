# Proposal

## Why

Нормы и глоссарий беклога сейчас доставляются во внешний проект копированием: `backlog install`
кладёт файлы в `rules/`, `docs/`, `backlog/`, `templates/`, дописывает `@`-импорты в `CLAUDE.md`
и строки в `.gitignore`. Распространённые имена путей сталкиваются с файлами проекта, правка
чужих точек подключения навязывает проекту постоянный контекст, а `backlog/*` в `.gitignore`
скрыл бы существующий каталог проекта. Нормы при этом нужны только в момент работы с беклогом —
навыку плагина либо внешнему вызову, — и единственный их носитель есть сама поставка.

## What Changes

- **BREAKING** Подкоманда `backlog install` и манифест `.backlog-manifest.json` удаляются:
  в дерево целевого проекта ничего не копируется, `CLAUDE.md` и `.gitignore` не правятся.
- Новые подкоманды входа: `backlog norms` печатает нормы и за ними глоссарий, `--rule BKL-NNN` —
  одно правило; `backlog sample` печатает образцовый шаблон операции. Это канал внешнего вызова.
- Навыки `backlog-run` и `backlog-template` адресуют нормы, глоссарий и образец через
  `${CLAUDE_PLUGIN_ROOT}` вместо `${CLAUDE_PROJECT_DIR}`.
- **BREAKING** Подстановка `{{rules}}` удаляется: беклог называет норму кодом и вызовом —
  «BKL-006 (`backlog norms --rule BKL-006`)»; структурная проверка ищет в каркасе коды правил,
  а не якоря ссылок. Беклоги, порождённые прежде, коды несут и проверку проходят.
- Вендоренная поставка (носитель порядка путём `.claude/skills/backlog-run/SKILL.md`) удаляется:
  плагин — единственный способ поставки.
- `backlog generate`, впервые заводя корень следа, печатает рекомендацию для `.gitignore`;
  она же есть в справке входа. Умолчания `backlog/` и `templates/` не меняются.
- Описание каталога следа `share/backlog/README.md` удаляется: описание адреса вбирает `BKL-002`.
  Правки норм: `BKL-008` — норма называется кодом правила; `BKL-010` — каркас проверяется
  по кодам.
- Репозиторий formular подключает нормы и глоссарий из источника `plugin/backlog/share/`
  напрямую; корневые копии и манифест удаляются, шаблоны операций formular переводятся
  с `{{rules}}` на коды. Плагин в formular грузится на месте локальным маркетплейсом
  и сам себя не устанавливает.
- Версия плагина — `1.3.0`. Миграции нет: прежние установки были тестовыми.

## Capabilities

### New Capabilities

- `backlog/norms-delivery`: выдача норм, глоссария и образца шаблона в контексте вызова —
  подкоманды `norms` и `sample`, адресация навыками от корня плагина, отказ от копирования
  в дерево проекта.

### Modified Capabilities

- `backlog/rules-installation`: все требования снимаются — установка норм в дерево проекта,
  манифест и шаблоны, приносимые установкой, упраздняются.
- `backlog/plugin-delivery`: требование «Носитель порядка адресует нормы через корень проекта»
  заменяется адресацией от корня плагина.
- `backlog/backlog-lint`: каркас проверяется по кодам норм исполнения, а не по ссылкам на них.
- `backlog/operation-backlog`: вход порождения печатает рекомендацию для `.gitignore`
  при первом заведении корня следа; беклог называет нормы кодом и вызовом.
- `backlog/template-acceptance`: навык приёмки называет нормы кодами, а образец — путём
  в поставке либо вызовом `backlog sample`.

## Impact

- Код плагина: `plugin/backlog/src/backlog/__main__.py`, `application/install_rules.py`,
  `application/__init__.py`, `application/contracts.py`, `infrastructure.py`, `domain.py`,
  `bin/backlog`, `.claude-plugin/plugin.json`.
- Поставка: `plugin/backlog/share/rules/operation-backlog-rules.md`,
  `plugin/backlog/share/backlog/README.md`, `plugin/backlog/templates/sample-operation.md`,
  `plugin/backlog/skills/*/SKILL.md`.
- Тесты: `tests/test_backlog.py` — `InstallRulesTest` удаляется, проверки каркаса переходят
  на коды.
- Репозиторий formular: `CLAUDE.md`, `README.md`, `.gitignore`, шаблоны `templates/*.md`;
  удаляются `rules/operation-backlog-rules.md`, `docs/glossary.md`, `backlog/README.md`,
  `templates/sample-operation.md`, `.backlog-manifest.json`.
- Внешние проекты: после обновления плагина нормы приходят в контекст вызова; файлы прежней
  тестовой установки удаляются руками.
