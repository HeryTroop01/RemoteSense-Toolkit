# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : remote_sense_provider.py
# Module     : Processing Provider
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Registers the RemoteSense Toolkit processing algorithms with the
#     QGIS Processing framework.
#
# Registered algorithms:
#     - Dataset Import
#     - AOI Creation
#     - Raster Clipping
#     - Band Extraction and Raster Statistics
#     - Band Set
#     - Export and Save
#     - Satellite Data Explorer & Downloader
#
# Status     : Stable
# =============================================================================

from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .import_dataset import ImportDatasetAlgorithm
from .create_aoi import CreateAOIAlgorithm
from .clip_raster import ClipRasterAlgorithm
from .extract_bands import ExtractBandsAlgorithm
from .create_band_set import CreateBandSetAlgorithm
from .export_save import ExportSaveAlgorithm
from .sentinel_downloader import SentinelDownloaderAlgorithm


class RemoteSenseProvider(QgsProcessingProvider):
    """Processing provider for RemoteSense Toolkit."""

    def __init__(self):
        """Initialize the RemoteSense Toolkit Processing provider."""
        super().__init__()

    def loadAlgorithms(self):
        """Register all RemoteSense Toolkit processing algorithms."""

        self.addAlgorithm(ImportDatasetAlgorithm())
        self.addAlgorithm(CreateAOIAlgorithm())
        self.addAlgorithm(ClipRasterAlgorithm())
        self.addAlgorithm(ExtractBandsAlgorithm())
        self.addAlgorithm(CreateBandSetAlgorithm())
        self.addAlgorithm(ExportSaveAlgorithm())
        self.addAlgorithm(SentinelDownloaderAlgorithm())

    def id(self):
        """Return the unique Processing provider identifier."""
        return "remotesensetoolkit"

    def name(self):
        """Return the provider name displayed by QGIS."""
        return "RemoteSense Toolkit"

    def longName(self):
        """Return the full provider name displayed by QGIS."""
        return "RemoteSense Toolkit"

    def icon(self):
        """Return the RemoteSense Toolkit provider icon."""
        icon_path = Path(__file__).parent.parent / "icon.png"
        return QIcon(str(icon_path))