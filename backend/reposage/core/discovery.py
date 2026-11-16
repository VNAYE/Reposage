"""Import every module in a package so their registration decorators run."""

from __future__ import annotations

import importlib
import pkgutil


def autodiscover(package_name: str) -> None:
    package = importlib.import_module(package_name)
    for module in pkgutil.iter_modules(package.__path__):
        if not module.name.startswith("_"):
            importlib.import_module(f"{package_name}.{module.name}")
