"""Auto-register repo loaders, chunkers and background job helpers."""

from reposage.core.discovery import autodiscover

autodiscover(__name__)
