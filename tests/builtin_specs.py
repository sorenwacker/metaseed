"""A SpecLoader that sees only the specs packaged in this repository.

Suites that validate the shipped specs must enumerate and load them from the
package, never through user-directory shadowing: a stale authoring copy under
the developer's data dir once hid a broken packaged example locally while CI,
with no user dir, failed on it. Skipping "user-defined" profiles is the wrong
predicate — a profile can be both, and then the packaged copy escapes the
suite exactly on the machine where it was authored.
"""

from pathlib import Path
from unittest import mock

from metaseed.specs.loader import SpecLoader

_NO_USER_SPECS = Path("/nonexistent-user-specs")


def builtin_only_loader(profile: str = "miappe") -> SpecLoader:
    """Build a SpecLoader whose user specs directory cannot resolve."""
    with mock.patch(
        "metaseed.specs.loader.get_user_specs_dir", return_value=_NO_USER_SPECS
    ):
        return SpecLoader(profile=profile)
