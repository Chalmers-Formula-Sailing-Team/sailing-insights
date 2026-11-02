from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Sequence
from pathlib import Path

from src.models.canonicalSession import CanonicalSession
from src.transformer.exclusionZones.exclusionZone import ExclusionZoneTransformer


class ExclusionZoneHandler:
    """
    Applies all exclusion zone transformers found in this package.

    New exclusion zones only need to be added as modules/classes in this
    directory; the handler will discover and run them automatically.
    """

    def __init__(self, zones: Sequence[ExclusionZoneTransformer] | None = None) -> None:
        self.zones = list(zones) if zones is not None else self._discover_zones()

    def transform(self, session: CanonicalSession) -> CanonicalSession:
        for zone in self.zones:
            session = zone.transform(session)
        return session

    def print_summary(self) -> None:
        if not self.zones:
            print("exclusion zones: no zones configured")
            return

        for zone in self.zones:
            zone.print_summary()

    def _discover_zones(self) -> list[ExclusionZoneTransformer]:
        zone_classes: list[type[ExclusionZoneTransformer]] = []
        package_name = __package__
        package_dir = Path(__file__).resolve().parent

        for module_info in pkgutil.iter_modules([str(package_dir)]):
            module_name = module_info.name
            if module_name in {"exclusionZone", "handler"}:
                continue

            module = importlib.import_module(f"{package_name}.{module_name}")
            zone_classes.extend(self._extract_zone_classes(module))

        zone_classes.sort(key=lambda zone_class: (zone_class.__module__, zone_class.__name__))
        return [zone_class() for zone_class in zone_classes]

    def _extract_zone_classes(
        self, module: object
    ) -> list[type[ExclusionZoneTransformer]]:
        zone_classes: list[type[ExclusionZoneTransformer]] = []

        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate.__module__ != getattr(module, "__name__", ""):
                continue
            if candidate is ExclusionZoneTransformer:
                continue
            if not issubclass(candidate, ExclusionZoneTransformer):
                continue
            if inspect.isabstract(candidate):
                continue

            zone_classes.append(candidate)

        return zone_classes
