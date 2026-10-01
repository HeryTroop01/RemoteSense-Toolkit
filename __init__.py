# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : __init__.py
# Module     : Plugin Entry Point
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Provides the QGIS plugin entry point used by QGIS to create the
#     RemoteSense Toolkit plugin instance.
#
# Status     : Stable
# =============================================================================


def classFactory(iface):
    """Create and return the RemoteSense Toolkit plugin instance."""
    from .remote_sense_toolkit import RemoteSenseToolkit

    return RemoteSenseToolkit(iface)