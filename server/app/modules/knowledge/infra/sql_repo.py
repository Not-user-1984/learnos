"""SQL-репозитории knowledge (SQLAlchemy Core).

Разрез по агрегатам (B-009): блоки — blocks_repo, версии — versions_repo,
категории — categories_repo; этот модуль — точка сборки для совместимости.
"""

from .blocks_repo import BlockRepository
from .categories_repo import CategoryRepository
from .versions_repo import BlockVersionsRepository

__all__ = ["BlockRepository", "BlockVersionsRepository", "CategoryRepository"]
