# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : sentinel_downloader.py
# Module     : Module 07 — Satellite Data Explorer & Downloader
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Provides the QGIS Processing entry point for the Module 07 custom
#     satellite-data exploration and download interface.
#
#     The Processing algorithm defines the standard search parameters while
#     the custom dialog provides the interactive user interface used for
#     dataset search, inspection, selection, and download.
#
# Current supported data:
#     - Sentinel-2 Level-2A
#     - Sentinel-2 Level-1C
#
# Data source:
#     - Copernicus Data Space Ecosystem (CDSE)
#
# Status     : Stable
# =============================================================================

from qgis.PyQt.QtCore import QCoreApplication

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterEnum,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSource,
)

from ..sentinel_downloader_dialog import SentinelDownloaderDialog


class SentinelDownloaderAlgorithm(QgsProcessingAlgorithm):
    """
    RemoteSense Toolkit — Module 07

    Satellite Data Explorer & Downloader.

    Custom Processing algorithm that launches the Module 07 custom
    QGIS dialog.

    The Processing parameters provide the standard satellite-data
    search configuration, while the custom dialog handles the
    interactive workflow.
    """

    # -------------------------------------------------------------------------
    # CDSE STAC CONFIGURATION
    # -------------------------------------------------------------------------

    STAC_URL = (
        "https://stac.dataspace.copernicus.eu/v1/search"
    )

    COLLECTIONS = {
        "Sentinel-2 Level-2A": "sentinel-2-l2a",
        "Sentinel-2 Level-1C": "sentinel-2-l1c",
    }

    # -------------------------------------------------------------------------
    # TRANSLATION
    # -------------------------------------------------------------------------

    def tr(self, string):
        """Translate a user-interface string."""
        return QCoreApplication.translate(
            "SentinelDownloaderAlgorithm",
            string,
        )

    # -------------------------------------------------------------------------
    # INSTANCE
    # -------------------------------------------------------------------------

    def createInstance(self):
        """Create a new Processing algorithm instance."""
        return SentinelDownloaderAlgorithm()

    # -------------------------------------------------------------------------
    # ALGORITHM NAME
    # -------------------------------------------------------------------------

    def name(self):
        """Return the unique Processing algorithm identifier."""
        return "sentinel_downloader"

    # -------------------------------------------------------------------------
    # DISPLAY NAME
    # -------------------------------------------------------------------------

    def displayName(self):
        """Return the algorithm name displayed in QGIS."""
        return self.tr(
            "Satellite Data Explorer & Downloader"
        )

    # -------------------------------------------------------------------------
    # PROCESSING GROUP
    # -------------------------------------------------------------------------

    def group(self):
        """Return the Processing Toolbox group name."""
        return self.tr(
            "06 — Satellite Data Explorer & Downloader"
        )

    # -------------------------------------------------------------------------
    # GROUP ID
    # -------------------------------------------------------------------------

    def groupId(self):
        """Return the unique Processing Toolbox group identifier."""
        return "06_satellite_data_explorer_downloader"

    # -------------------------------------------------------------------------
    # HELP
    # -------------------------------------------------------------------------

    def shortHelpString(self):
        """Return the Processing algorithm help description."""
        return self.tr(
            "Search, inspect, select, and download satellite datasets "
            "from the Copernicus Data Space Ecosystem (CDSE)."
        )

    # -------------------------------------------------------------------------
    # CUSTOM PROCESSING DIALOG
    # -------------------------------------------------------------------------

    def createCustomParametersWidget(self, parent=None):
        """Create the custom Module 07 QGIS dialog."""
        return SentinelDownloaderDialog(
            self,
            parent,
        )

    # -------------------------------------------------------------------------
    # PROCESSING PARAMETERS
    # -------------------------------------------------------------------------

    def initAlgorithm(self, config=None):
        """Define the standard Processing parameters."""

        # ---------------------------------------------------------------------
        # DATA SOURCE
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterEnum(
                "DATA_SOURCE",
                self.tr("Data source"),
                options=[
                    "Copernicus Data Space Ecosystem (CDSE)",
                ],
                defaultValue=0,
            )
        )

        # ---------------------------------------------------------------------
        # MISSION
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterEnum(
                "MISSION",
                self.tr("Mission"),
                options=[
                    "Sentinel-2",
                ],
                defaultValue=0,
            )
        )

        # ---------------------------------------------------------------------
        # PRODUCT
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterEnum(
                "PRODUCT",
                self.tr("Product"),
                options=[
                    "Sentinel-2 Level-2A",
                    "Sentinel-2 Level-1C",
                ],
                defaultValue=0,
            )
        )

        # ---------------------------------------------------------------------
        # START DATE
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterDateTime(
                "START_DATE",
                self.tr("Start date"),
                type=QgsProcessingParameterDateTime.Date,
            )
        )

        # ---------------------------------------------------------------------
        # END DATE
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterDateTime(
                "END_DATE",
                self.tr("End date"),
                type=QgsProcessingParameterDateTime.Date,
            )
        )

        # ---------------------------------------------------------------------
        # MAXIMUM CLOUD COVER
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterNumber(
                "MAX_CLOUD",
                self.tr(
                    "Maximum cloud cover (%)"
                ),
                type=QgsProcessingParameterNumber.Double,
                minValue=0.0,
                maxValue=100.0,
                defaultValue=20.0,
            )
        )

        # ---------------------------------------------------------------------
        # MAXIMUM RESULTS
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterNumber(
                "MAX_RESULTS",
                self.tr(
                    "Maximum search results"
                ),
                type=QgsProcessingParameterNumber.Integer,
                minValue=1,
                maxValue=100,
                defaultValue=20,
            )
        )

        # ---------------------------------------------------------------------
        # AOI
        # ---------------------------------------------------------------------

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "AOI",
                self.tr(
                    "AOI / study area"
                ),
                types=[
                    QgsProcessing.TypeVectorPolygon,
                ],
                optional=True,
            )
        )

    # -------------------------------------------------------------------------
    # PROCESS
    # -------------------------------------------------------------------------

    def processAlgorithm(
        self,
        parameters,
        context,
        feedback,
    ):
        """
        Execute the Processing algorithm.

        Module 07 currently performs its interactive work through the custom
        dialog. The Processing algorithm therefore acts as the entry point
        and confirms that the custom interface has been initialized.
        """

        feedback.pushInfo(
            "Satellite Data Explorer & Downloader — "
            "custom UI loaded."
        )

        return {}