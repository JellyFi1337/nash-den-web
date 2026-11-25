"""Хранилище статики: хеш в имени файла и в импортах ES-модулей."""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class HashedStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Сжатие WhiteNoise и переписывание import/export в файлах .js.

    Без этого флага Django оставляет в app.js пути вида ./modules/gate.js.
    Браузер тогда кеширует модуль без хеша в имени.
    """

    support_js_module_import_aggregation = True
