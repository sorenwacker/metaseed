"""Convenience functions for common profile facades.

This module provides factory functions to quickly instantiate ProfileFacade
instances for commonly used metadata profiles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.facade.core import ProfileFacade


def miappe(version: str | None = None) -> ProfileFacade:
    """Get MIAPPE profile facade.

    Args:
        version: MIAPPE version. If None, uses the latest available version.

    Returns:
        ProfileFacade for MIAPPE.

    Example:
        >>> from metaseed.facade import miappe
        >>> m = miappe()
        >>> m.Investigation.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("miappe", version)


def miappe_htp(version: str | None = None) -> ProfileFacade:
    """Get MIAPPE-HTP profile facade.

    Args:
        version: MIAPPE-HTP version. If None, uses the latest available version.

    Returns:
        ProfileFacade for MIAPPE-HTP (High Throughput Phenotyping).

    Example:
        >>> from metaseed import miappe_htp
        >>> m = miappe_htp()
        >>> m.Investigation.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("miappe-htp", version)


def isa(version: str | None = None) -> ProfileFacade:
    """Get ISA profile facade.

    Args:
        version: ISA version. If None, uses the latest available version.

    Returns:
        ProfileFacade for ISA.

    Example:
        >>> from metaseed.facade import isa
        >>> i = isa()
        >>> i.Investigation.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("isa", version)


def ena(version: str | None = None) -> ProfileFacade:
    """Get ENA profile facade.

    Args:
        version: ENA version. If None, uses the latest available version.

    Returns:
        ProfileFacade for ENA (European Nucleotide Archive).

    Example:
        >>> from metaseed import ena
        >>> e = ena()
        >>> e.Study.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("ena", version)


def pride(version: str | None = None) -> ProfileFacade:
    """Get PRIDE profile facade.

    Args:
        version: PRIDE version. If None, uses the latest available version.

    Returns:
        ProfileFacade for PRIDE (ProteomeXchange).

    Example:
        >>> from metaseed import pride
        >>> p = pride()
        >>> p.Project.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("pride", version)


def metabolights(version: str | None = None) -> ProfileFacade:
    """Get MetaboLights profile facade.

    Args:
        version: MetaboLights version. If None, uses the latest available version.

    Returns:
        ProfileFacade for MetaboLights.

    Example:
        >>> from metaseed import metabolights
        >>> m = metabolights()
        >>> m.Investigation.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("metabolights", version)


def dissco(version: str | None = None) -> ProfileFacade:
    """Get DiSSCo profile facade.

    Args:
        version: DiSSCo version. If None, uses the latest available version.

    Returns:
        ProfileFacade for DiSSCo.

    Example:
        >>> from metaseed import dissco
        >>> d = dissco()
        >>> d.DigitalSpecimen.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("dissco", version)


def darwin_core(version: str | None = None) -> ProfileFacade:
    """Get Darwin Core profile facade.

    Args:
        version: Darwin Core version. If None, uses the latest available version.

    Returns:
        ProfileFacade for Darwin Core.

    Example:
        >>> from metaseed import darwin_core
        >>> d = darwin_core()
        >>> d.Occurrence.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("darwin-core", version)


def rembi(version: str | None = None) -> ProfileFacade:
    """Get REMBI profile facade.

    Args:
        version: REMBI version. If None, uses the latest available version.

    Returns:
        ProfileFacade for the REMBI profile.

    Example:
        >>> from metaseed import rembi
        >>> r = rembi()
        >>> r.Study.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("rembi", version)


def health_ri_core(version: str | None = None) -> ProfileFacade:
    """Get Health-RI core metadata profile facade.

    Args:
        version: Health-RI core version. If None, uses the latest available version.

    Returns:
        ProfileFacade for the Health-RI core profile.

    Example:
        >>> from metaseed import health_ri_core
        >>> h = health_ri_core()
        >>> h.Catalog.help()
    """
    from metaseed.facade.core import ProfileFacade

    return ProfileFacade("health-ri-core", version)
