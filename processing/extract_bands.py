# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : extract_bands.py
# Module     : Module 04 — Extraction
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Scans a folder for supported raster datasets, extracts raster and band
#     information, calculates band statistics, generates a CSV report, and
#     optionally loads the input rasters into a QGIS layer group.
#
# Status     : Stable
# =============================================================================

from pathlib import Path
import csv
import re

import processing

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsProject,
    QgsRasterLayer,
)


class ExtractBandsAlgorithm(QgsProcessingAlgorithm):
    """Extract raster and band information and calculate raster statistics."""

    INPUT_FOLDER = "INPUT_FOLDER"
    RECURSIVE = "RECURSIVE"
    GROUP_NAME = "GROUP_NAME"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    REPORT = "REPORT"

    RASTER_EXTENSIONS = {
        ".tif",
        ".tiff",
        ".jp2",
        ".img",
        ".vrt",
    }

    def tr(self, string):
        """Translate a user-interface string."""
        return QCoreApplication.translate(
            "ExtractBandsAlgorithm",
            string,
        )

    def createInstance(self):
        """Create a new instance of the processing algorithm."""
        return ExtractBandsAlgorithm()

    def name(self):
        """Return the unique Processing algorithm identifier."""
        return "extract_bands"

    def displayName(self):
        """Return the algorithm name displayed in QGIS."""
        return self.tr("Extract Bands and Raster Statistics")

    def group(self):
        """Return the Processing Toolbox group name."""
        return self.tr("04 — Extraction")

    def groupId(self):
        """Return the unique Processing Toolbox group identifier."""
        return "04_extraction"

    def shortHelpString(self):
        """Return the algorithm help description."""
        return self.tr(
            "Scans a raster folder, extracts raster and band information, "
            "calculates statistics, creates a CSV report, and optionally "
            "loads the rasters into a user-defined QGIS layer group."
        )

    def initAlgorithm(self, config=None):
        """Define the extraction inputs and outputs."""

        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr("Input raster folder"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.RECURSIVE,
                self.tr("Search subfolders recursively"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.GROUP_NAME,
                self.tr("QGIS layer group name"),
                defaultValue="Extracted Rasters",
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_OUTPUTS,
                self.tr("Load rasters into QGIS"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr("Output report folder"),
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.REPORT,
                self.tr("Extraction report"),
            )
        )

    def find_rasters(self, folder, recursive):
        """Find supported raster files in the input folder."""

        folder_path = Path(folder)

        if recursive:
            files = folder_path.rglob("*")
        else:
            files = folder_path.glob("*")

        rasters = []

        for file_path in files:
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() in self.RASTER_EXTENSIONS:
                rasters.append(file_path)

        return sorted(rasters)

    def extract_band_name(self, filename):
        """Extract a recognizable band identifier from a raster filename."""

        stem = Path(filename).stem

        patterns = [
            r"(?i)(?:^|[_\-\s])(B(?:0?[1-9]|1[0-2]|8A))(?=[_\-\s.]|$)",
            r"(?i)(B8A)",
            r"(?i)(B(?:0?[1-9]|1[0-2]))",
            r"(?i)(AOT)",
            r"(?i)(WVP)",
            r"(?i)(SCL)",
            r"(?i)(TCI)",
        ]

        for pattern in patterns:
            match = re.search(pattern, stem)

            if match:
                return match.group(1).upper()

        return stem

    def calculate_statistics(self, raster, feedback):
        """Calculate minimum, maximum, mean, and standard deviation per band."""

        provider = raster.dataProvider()
        statistics = []

        for band in range(1, raster.bandCount() + 1):
            if feedback.isCanceled():
                break

            band_name = raster.bandName(band)

            try:
                stats = provider.bandStatistics(
                    band,
                    QgsRasterLayer.Min
                    | QgsRasterLayer.Max
                    | QgsRasterLayer.Mean
                    | QgsRasterLayer.StDev,
                )

                minimum = stats.minimumValue
                maximum = stats.maximumValue
                mean = stats.mean
                stddev = stats.stdDev

            except Exception:
                minimum = None
                maximum = None
                mean = None
                stddev = None

            statistics.append(
                {
                    "band": band,
                    "band_name": band_name,
                    "minimum": minimum,
                    "maximum": maximum,
                    "mean": mean,
                    "stddev": stddev,
                }
            )

        return statistics

    def processAlgorithm(self, parameters, context, feedback):
        """Process rasters, calculate statistics, and generate a CSV report."""

        input_folder = self.parameterAsString(
            parameters,
            self.INPUT_FOLDER,
            context,
        )

        recursive = self.parameterAsBool(
            parameters,
            self.RECURSIVE,
            context,
        )

        group_name = self.parameterAsString(
            parameters,
            self.GROUP_NAME,
            context,
        ).strip()

        load_outputs = self.parameterAsBool(
            parameters,
            self.LOAD_OUTPUTS,
            context,
        )

        output_folder = self.parameterAsString(
            parameters,
            self.OUTPUT_FOLDER,
            context,
        )

        if not input_folder:
            raise QgsProcessingException(
                self.tr("Input raster folder was not provided.")
            )

        input_path = Path(input_folder)

        if not input_path.exists():
            raise QgsProcessingException(
                self.tr("Input raster folder does not exist.")
            )

        if not input_path.is_dir():
            raise QgsProcessingException(
                self.tr("Input path is not a folder.")
            )

        if not group_name:
            group_name = "Extracted Rasters"

        if not output_folder:
            raise QgsProcessingException(
                self.tr("Output report folder was not provided.")
            )

        output_path = Path(output_folder)

        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        rasters = self.find_rasters(
            input_path,
            recursive,
        )

        if not rasters:
            raise QgsProcessingException(
                self.tr("No supported raster files were found.")
            )

        feedback.pushInfo(
            f"Found {len(rasters)} raster(s)."
        )

        group = None

        if load_outputs:
            root = QgsProject.instance().layerTreeRoot()

            group = root.findGroup(group_name)

            if group is None:
                group = root.addGroup(group_name)

        csv_path = (
            output_path / "raster_extraction_statistics.csv"
        )

        csv_rows = []
        successful = []
        failed = []

        for index, raster_path in enumerate(rasters):
            if feedback.isCanceled():
                break

            feedback.setProgress(
                int(index / len(rasters) * 100)
            )

            feedback.pushInfo(
                f"Processing: {raster_path.name}"
            )

            raster = QgsRasterLayer(
                str(raster_path),
                raster_path.stem,
                "gdal",
            )

            if not raster.isValid():
                failed.append(
                    (
                        raster_path.name,
                        "Invalid raster",
                    )
                )

                feedback.reportError(
                    f"Invalid raster: {raster_path.name}"
                )

                continue

            try:
                provider = raster.dataProvider()
                crs = raster.crs()
                extent = raster.extent()
                width = raster.width()
                height = raster.height()

                pixel_x = (
                    extent.width() / width
                    if width
                    else 0
                )

                pixel_y = (
                    extent.height() / height
                    if height
                    else 0
                )

                band_name = self.extract_band_name(
                    raster_path.name
                )

                statistics = self.calculate_statistics(
                    raster,
                    feedback,
                )

                for item in statistics:
                    csv_rows.append(
                        {
                            "Raster": raster_path.name,
                            "Band_ID": item["band"],
                            "Band_Name": item["band_name"],
                            "Detected_Name": band_name,
                            "Width": width,
                            "Height": height,
                            "Resolution_X": pixel_x,
                            "Resolution_Y": pixel_y,
                            "CRS": crs.authid(),
                            "Minimum": item["minimum"],
                            "Maximum": item["maximum"],
                            "Mean": item["mean"],
                            "StdDev": item["stddev"],
                        }
                    )

                successful.append(
                    {
                        "input": raster_path.name,
                        "detected": band_name,
                        "width": width,
                        "height": height,
                        "bands": raster.bandCount(),
                        "crs": crs.authid(),
                        "xres": pixel_x,
                        "yres": pixel_y,
                    }
                )

                if load_outputs:
                    layer = QgsRasterLayer(
                        str(raster_path),
                        raster_path.stem,
                        "gdal",
                    )

                    if layer.isValid():
                        added_layer = (
                            QgsProject.instance().addMapLayer(
                                layer,
                                False,
                            )
                        )

                        if group is not None:
                            group.addLayer(added_layer)

                    else:
                        feedback.reportError(
                            "Raster was valid initially but could not "
                            f"be loaded: {raster_path.name}"
                        )

            except Exception as exc:
                failed.append(
                    (
                        raster_path.name,
                        str(exc),
                    )
                )

                feedback.reportError(
                    f"Failed: {raster_path.name} — {exc}"
                )

        fieldnames = [
            "Raster",
            "Band_ID",
            "Band_Name",
            "Detected_Name",
            "Width",
            "Height",
            "Resolution_X",
            "Resolution_Y",
            "CRS",
            "Minimum",
            "Maximum",
            "Mean",
            "StdDev",
        ]

        with open(
            csv_path,
            "w",
            newline="",
            encoding="utf-8",
        ) as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames,
            )

            writer.writeheader()

            for row in csv_rows:
                writer.writerow(row)

        report_lines = [
            "REMOTE SENSE TOOLKIT — RASTER EXTRACTION REPORT",
            "================================================",
            f"Input folder: {input_folder}",
            f"Output folder: {output_folder}",
            f"Files detected: {len(rasters)}",
            f"Successfully processed: {len(successful)}",
            f"Failed: {len(failed)}",
            f"QGIS group: {group_name}",
            f"Statistics CSV: {csv_path}",
            "",
            "PROCESSED RASTERS",
            "------------------------------------------------",
        ]

        for item in successful:
            report_lines.append(
                f"{item['detected']} → "
                f"{item['input']}"
            )

            report_lines.append(
                f"    Size: "
                f"{item['width']} × "
                f"{item['height']} pixels"
            )

            report_lines.append(
                f"    Bands: {item['bands']}"
            )

            report_lines.append(
                f"    CRS: {item['crs']}"
            )

            report_lines.append(
                f"    Resolution: "
                f"{abs(item['xres']):.6f} × "
                f"{abs(item['yres']):.6f}"
            )

        if failed:
            report_lines.extend(
                [
                    "",
                    "FAILED RASTERS",
                    "------------------------------------------------",
                ]
            )

            for filename, reason in failed:
                report_lines.append(
                    f"{filename} → {reason}"
                )

        report_lines.extend(
            [
                "",
                "================================================",
                "Raster extraction completed.",
            ]
        )

        report = "\n".join(report_lines)

        feedback.pushInfo(report)

        return {
            self.REPORT: report,
        }