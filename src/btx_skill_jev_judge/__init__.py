"""Public package surface exposing metadata and configuration.

This module provides the stable public API for the package, routing imports
through the proper architectural layers:
- Composition exports: Wired adapter services (configuration)
- Metadata: Package information
"""

from __future__ import annotations

# Metadata
from .__init__conf__ import print_info

# Composition exports (wired adapters)
from .composition import get_config

__all__ = [
    "get_config",
    "print_info",
]
