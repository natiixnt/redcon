# Repository brief: django

Task-independent map of 5680 scanned files (.py x2924, .po x1274, .txt x717), 11349 internal import links. Geography only, no per-change file list.

## Module geography
- `django/apps/` (3 files): __init__, config, registry
- `django/conf/` (286 files): locale/, app_template/, project_template/, urls/, +2 more
- `django/contrib/` (1668 files): admin/, gis/, auth/, sessions/, +12 more
- `django/core/` (111 files): management/, checks/, files/, mail/, +12 more
- `django/db/` (122 files): backends/, models/, migrations/, __init__, +2 more
- `django/dispatch/` (2 files): __init__, dispatcher
- `django/forms/` (101 files): jinja2/, templates/, __init__, boundfield, +7 more
- `django/http/` (5 files): __init__, cookie, multipartparser, request, +1 more
- `django/middleware/` (10 files): __init__, cache, clickjacking, common, +6 more
- `django/tasks/` (9 files): backends/, __init__, base, checks, +2 more
- `django/template/` (27 files): backends/, loaders/, __init__, autoreload, +13 more
- `django/templatetags/` (6 files): __init__, cache, i18n, l10n, +2 more
- `django/urls/` (7 files): __init__, base, conf, converters, +3 more
- `django/utils/` (48 files): translation/, __init__, _os, archive, +40 more
- `django/views/` (28 files): decorators/, generic/, templates/, __init__, +5 more
- `django/` top-level modules: __init__, __main__, shortcuts

## Entry points
- `django/__main__.py`
- `django/contrib/admin/views/main.py`
- `django/core/asgi.py`
- `django/core/handlers/asgi.py`
- `django/core/handlers/wsgi.py`
- `django/core/wsgi.py`

## Test layout
- 2480 files total
- `tests/`: 2447 files
- `django/`: 12 files
- `js_tests/`: 12 files
- (repository root): 5 files
- `scripts/`: 3 files
- `docs/`: 1 file

## Build and config
- `pyproject.toml`
- `tox.ini`
- `package.json`
- `.pre-commit-config.yaml`
