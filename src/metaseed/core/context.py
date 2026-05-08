"""Context classes for reducing parameter passing throughout the codebase."""

from dataclasses import dataclass
from functools import cached_property


@dataclass(frozen=True)
class ProfileContext:
    """Context for profile operations, reducing parameter passing.

    This immutable dataclass encapsulates the (profile, version) pair that is
    frequently passed together throughout the codebase. It provides a cache_key
    property for use in caching scenarios.

    Attributes:
        profile: Profile name (e.g., "miappe", "isa", "darwin-core").
        version: Version string (e.g., "1.1", "1.0").

    Example:
        ctx = ProfileContext(profile="miappe", version="1.2")
        loader.load_profile(ctx=ctx)
        loader.load_entity("Investigation", ctx=ctx)
    """

    profile: str
    version: str

    @cached_property
    def cache_key(self) -> str:
        """Generate a cache key for this profile+version combination.

        Returns:
            String in format "profile:version".
        """
        return f"{self.profile}:{self.version}"
