"""Публичный фасад knowledge (B-009): только это другие модули могут импортировать.

Внутренности (service, agents, domain, schemas, infra) — закрыты контрактом
import-linter; события — knowledge.events, генерация — методы сервиса.
"""

from .domain import WIKILINK, BlockDraft, BlockSource, plain_text, slugify
from .schemas import BlockDraftIn

__all__ = ["BlockDraft", "BlockSource", "BlockDraftIn", "WIKILINK", "plain_text", "slugify"]
