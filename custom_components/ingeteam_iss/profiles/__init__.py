"""Explicit profile registry. Never load modules from user-provided names."""

from types import MappingProxyType

from .base import ModelProfile, UnsupportedProfileError
from .tl_m import PROFILE

CONF_PROFILE = "profile"
DEFAULT_PROFILE_ID = "tl_m"
PROFILES = MappingProxyType({PROFILE.id: PROFILE})


def get_profile(profile_id: str | None = None) -> ModelProfile:
    if profile_id is None:
        profile_id = DEFAULT_PROFILE_ID
    if not isinstance(profile_id, str) or profile_id not in PROFILES:
        raise UnsupportedProfileError("Unknown or unsupported inverter profile")
    return PROFILES[profile_id]


def resolve_profile(profile_id: str | None, capabilities) -> ModelProfile:
    profile = get_profile(profile_id)
    profile.validate_map(capabilities)
    return profile
