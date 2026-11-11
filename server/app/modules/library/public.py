"""Публичный фасад library (B-009): только это другие модули могут импортировать."""

from .domain import is_youtube_url

__all__ = ["is_youtube_url"]
