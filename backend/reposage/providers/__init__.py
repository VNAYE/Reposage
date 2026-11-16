"""Auto-register every provider module in this package."""

from reposage.core.discovery import autodiscover

autodiscover(__name__)
