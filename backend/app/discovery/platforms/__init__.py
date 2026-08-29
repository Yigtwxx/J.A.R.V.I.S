"""Platform catalogue, URL matching and existence verification."""

from app.discovery.platforms.registry import (
    CORE_PLATFORMS,
    UNSUPPORTED_PLATFORMS,
    PlatformRegistry,
    core_keys,
    get_core_registry,
    get_registry,
    load_extended_specs,
    registry_for_selection,
)
from app.discovery.platforms.spec import PlatformSpec, spec_from_dict
from app.discovery.platforms.urlmatch import (
    UrlMatch,
    canonical_profile_url,
    is_generic_handle,
    known_platforms,
    match_profile_url,
    platform_for_host,
    registrable_host,
)

__all__ = [
    "CORE_PLATFORMS",
    "UNSUPPORTED_PLATFORMS",
    "PlatformRegistry",
    "PlatformSpec",
    "UrlMatch",
    "canonical_profile_url",
    "core_keys",
    "get_core_registry",
    "get_registry",
    "is_generic_handle",
    "known_platforms",
    "load_extended_specs",
    "match_profile_url",
    "platform_for_host",
    "registrable_host",
    "registry_for_selection",
    "spec_from_dict",
]
