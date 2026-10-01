# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : import_dataset.py
# Module     : Module 01 — Dataset Import
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Scans a selected folder for supported raster datasets, validates them
#     through QGIS/GDAL, loads valid rasters into the current QGIS project,
#     and generates a basic dataset import report.
#
# Supported raster formats:
#     - GeoTIFF (.tif, .tiff)
#     - JPEG 2000 (.jp2)
#     - ERDAS Imagine (.img)
#     - Virtual Raster (.vrt)
#     - NetCDF (.nc)
#
# Status     : Stable
# =============================================================================

from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProject,
    QgsRasterLayer,
)


# Raster extensions accepted by the dataset import algorithm.
SUPPORTED_EXTENSIONS = {
    ".tif",
    ".tiff",
    ".jp2",
    ".img",
    ".vrt",
    ".nc",
}


class ImportDatasetAlgorithm(QgsProcessingAlgorithm):
    """Scan a folder, inspect supported rasters, and load valid datasets."""

    INPUT_FOLDER = "INPUT_FOLDER"
    RECURSIVE = "RECURSIVE"
    REPORT = "REPORT"

    def tr(self, string):
        """Translate a user-interface string."""
        return QCoreApplication.translate("ImportDatasetAlgorithm", string)

    def createInstance(self):
        """Create a new instance of the processing algorithm."""
        return ImportDatasetAlgorithm()

    def name(self):
        """Return the unique Processing algorithm identifier."""
        return "import_remote_sensing_dataset"

    def displayName(self):
        """Return the algorithm name displayed in QGIS."""
        return self.tr("Import Remote Sensing Dataset")

    def group(self):
        """Return the Processing Toolbox group name."""
        return self.tr("01 — Dataset Import")

    def groupId(self):
        """Return the unique Processing Toolbox group identifier."""
        return "dataset_import"

    def shortHelpString(self):
        """Return the algorithm help description."""
        return self.tr(
            "Scans a folder for supported raster datasets, reports their basic "
            "metadata, and loads valid raster files into the current QGIS "
            "project."
        )

    def initAlgorithm(self, config=None):
        """Define the input parameters and processing outputs."""

        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr("Input dataset folder"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.RECURSIVE,
                self.tr("Scan subfolders recursively"),
                defaultValue=True,
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.REPORT,
                self.tr("Import report"),
            )
        )

    def _raster_files(self, folder, recursive):
        """
        Find supported raster files in the selected folder.

        Parameters
        ----------
        folder : str
            Input folder containing remote-sensing datasets.

        recursive : bool
            Whether subdirectories should also be searched.

        Returns
        -------
        list[Path]
            Sorted list of supported raster files.
        """

        folder_path = Path(folder)

        if recursive:
            candidates = folder_path.rglob("*")
        else:
            candidates = folder_path.glob("*")

        return sorted(
            path
            for path in candidates
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def processAlgorithm(self, parameters, context, feedback):
        """Scan, validate, load, and report supported raster datasets."""

        folder = self.parameterAsString(
            parameters,
            self.INPUT_FOLDER,
            context,
        )

        recursive = self.parameterAsBool(
            parameters,
            self.RECURSIVE,
            context,
        )

        if not folder or not Path(folder).is_dir():
            raise QgsProcessingException(
                "The selected input folder does not exist."
            )

        files = self._raster_files(folder, recursive)

        if not files:
            feedback.pushWarning(
                "No supported raster files were found in the selected folder."
            )

            return {
                self.REPORT: "No supported raster datasets found."
            }

        report_lines = [
            "REMOTE SENSE TOOLKIT — DATASET IMPORT REPORT",
            "=" * 52,
            f"Input folder: {folder}",
            f"Files detected: {len(files)}",
            "",
        ]

        loaded = 0
        failed = 0

        for index, file_path in enumerate(files, start=1):
            if feedback.isCanceled():
                break

            feedback.setProgress(
                int(index * 100 / len(files))
            )

            feedback.pushInfo(
                f"Inspecting: {file_path.name}"
            )

            # Use the GDAL raster provider so QGIS handles the supported
            # remote-sensing raster formats consistently.
            layer = QgsRasterLayer(
                str(file_path),
                file_path.stem,
                "gdal",
            )

            if not layer.isValid():
                failed += 1

                report_lines.extend(
                    [
                        f"[FAILED] {file_path.name}",
                        "  Reason: QGIS could not create a valid raster layer.",
                        "",
                    ]
                )

                feedback.reportError(
                    f"Invalid raster: {file_path}"
                )

                continue

            provider = layer.dataProvider()
            extent = layer.extent()
            crs = layer.crs()

            width = provider.xSize()
            height = provider.ySize()
            band_count = provider.bandCount()

            pixel_x = (
                extent.width() / layer.width()
                if layer.width()
                else 0
            )

            pixel_y = (
                extent.height() / layer.height()
                if layer.height()
                else 0
            )

            data_types = []
            nodata_values = []

            for band in range(1, band_count + 1):
                data_types.append(
                    str(provider.dataType(band))
                )

                try:
                    if provider.sourceHasNoDataValue(band):
                        nodata_values.append(
                            str(provider.sourceNoDataValue(band))
                        )
                    else:
                        nodata_values.append("None")

                except Exception:
                    nodata_values.append("Unknown")

            # Add the validated raster to the current QGIS project.
            QgsProject.instance().addMapLayer(layer)
            loaded += 1

            report_lines.extend(
                [
                    f"[LOADED] {file_path.name}",
                    f"  Path: {file_path}",
                    f"  CRS: {crs.authid()}",
                    f"  Size: {width} x {height} pixels",
                    f"  Resolution: {pixel_x:g} x {pixel_y:g}",
                    f"  Bands: {band_count}",
                    f"  Data type(s): {', '.join(data_types)}",
                    f"  NoData: {', '.join(nodata_values)}",
                    (
                        "  Extent: "
                        f"{extent.xMinimum():.6f}, "
                        f"{extent.yMinimum():.6f}, "
                        f"{extent.xMaximum():.6f}, "
                        f"{extent.yMaximum():.6f}"
                    ),
                    "",
                ]
            )

        report_lines.extend(
            [
                "=" * 52,
                f"Successfully loaded: {loaded}",
                f"Failed: {failed}",
            ]
        )

        report = "\n".join(report_lines)

        feedback.pushInfo(report)

        return {
            self.REPORT: report
        }