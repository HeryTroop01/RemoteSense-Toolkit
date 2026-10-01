# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : clip_raster.py
# Module     : Module 03 — Clip / Download
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Clips supported raster datasets to a selected polygon AOI using the
#     QGIS/GDAL processing framework and optionally loads the generated
#     rasters into QGIS.
#
# Status     : Stable
# =============================================================================

from pathlib import Path
import re

import processing

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterString,
    QgsProcessingOutputString,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)


class ClipRasterAlgorithm(QgsProcessingAlgorithm):
    """Batch clip supported raster datasets to a polygon AOI."""

    INPUT_FOLDER = "INPUT_FOLDER"
    INPUT_AOI = "INPUT_AOI"
    RECURSIVE = "RECURSIVE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    PREFIX = "PREFIX"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    CREATE_GROUP = "CREATE_GROUP"
    REPORT = "REPORT"

    RASTER_EXTENSIONS = {
        ".tif",
        ".tiff",
        ".img",
        ".jp2",
        ".vrt",
    }

    def tr(self, string):
        """Translate a user-interface string."""
        return QCoreApplication.translate("ClipRasterAlgorithm", string)

    def createInstance(self):
        """Create a new instance of the processing algorithm."""
        return ClipRasterAlgorithm()

    def name(self):
        """Return the unique Processing algorithm identifier."""
        return "clip_raster"

    def displayName(self):
        """Return the algorithm name displayed in QGIS."""
        return self.tr("Batch Clip Rasters to AOI")

    def group(self):
        """Return the Processing Toolbox group name."""
        return self.tr("03 — Clip / Download")

    def groupId(self):
        """Return the unique Processing Toolbox group identifier."""
        return "03_clip_download"

    def shortHelpString(self):
        """Return the algorithm help description."""
        return self.tr(
            "Clips all supported raster datasets in a folder to a selected "
            "polygon AOI and optionally loads the results into a QGIS layer "
            "group."
        )

    def initAlgorithm(self, config=None):
        """Define the clipping inputs and outputs."""

        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr("Input raster folder"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_AOI,
                self.tr("AOI polygon"),
                [QgsProcessing.TypeVectorPolygon],
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
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr("Output folder"),
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.PREFIX,
                self.tr("Output naming prefix"),
                defaultValue="Clipped_Extent",
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_OUTPUTS,
                self.tr("Load clipped rasters into QGIS"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CREATE_GROUP,
                self.tr("Create QGIS layer group"),
                defaultValue=True,
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.REPORT,
                self.tr("Batch clip report"),
            )
        )

    def extract_band_name(self, filename):
        """Extract a standard band identifier from a raster filename."""

        stem = Path(filename).stem

        patterns = [
            r"(?i)(?:^|[_\-\s])(B(?:0?[1-9]|1[0-2]|8A))(?=[_\-\s.]|$)",
            r"(?i)(B8A)",
            r"(?i)(B(?:0?[1-9]|1[0-2]))",
        ]

        for pattern in patterns:
            match = re.search(pattern, stem)

            if match:
                return match.group(1).upper()

        cleaned = re.sub(
            r"[^A-Za-z0-9]+",
            "_",
            stem,
        ).strip("_")

        return cleaned

    def find_rasters(self, folder, recursive):
        """Return supported raster files from the input folder."""

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

    def processAlgorithm(self, parameters, context, feedback):
        """Clip all supported rasters to the selected AOI."""

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

        output_folder = self.parameterAsString(
            parameters,
            self.OUTPUT_FOLDER,
            context,
        )

        prefix = self.parameterAsString(
            parameters,
            self.PREFIX,
            context,
        ).strip()

        load_outputs = self.parameterAsBool(
            parameters,
            self.LOAD_OUTPUTS,
            context,
        )

        create_group = self.parameterAsBool(
            parameters,
            self.CREATE_GROUP,
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

        if not output_folder:
            raise QgsProcessingException(
                self.tr("Output folder was not provided.")
            )

        output_path = Path(output_folder)
        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not prefix:
            prefix = "Clipped_Extent"

        prefix = re.sub(
            r"[^A-Za-z0-9_\-]+",
            "_",
            prefix,
        )

        aoi = self.parameterAsSource(
            parameters,
            self.INPUT_AOI,
            context,
        )

        if aoi is None:
            raise QgsProcessingException(
                self.tr("A valid AOI polygon is required.")
            )

        aoi_crs = aoi.sourceCrs()

        if not aoi_crs.isValid():
            raise QgsProcessingException(
                self.tr("The AOI does not have a valid CRS.")
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

        if create_group and load_outputs:
            root = QgsProject.instance().layerTreeRoot()

            group = root.findGroup("Clipped Extent")

            if group is None:
                group = root.addGroup("Clipped Extent")

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

            raster_crs = raster.crs()

            if not raster_crs.isValid():
                failed.append(
                    (
                        raster_path.name,
                        "Invalid CRS",
                    )
                )

                feedback.reportError(
                    f"Invalid CRS: {raster_path.name}"
                )

                continue

            # Create a temporary in-memory AOI layer.
            aoi_layer = QgsVectorLayer(
                "Polygon",
                "AOI_for_clipping",
                "memory",
            )

            aoi_layer.setCrs(aoi_crs)

            aoi_provider = aoi_layer.dataProvider()

            for feature in aoi.getFeatures():
                geometry = feature.geometry()

                if geometry.isNull():
                    continue

                if geometry.isEmpty():
                    continue

                copied = QgsFeature()
                copied.setGeometry(geometry)

                aoi_provider.addFeature(copied)

            aoi_layer.updateExtents()

            # Reproject the AOI when its CRS differs from the raster CRS.
            clipping_layer = aoi_layer

            if aoi_crs != raster_crs:
                feedback.pushInfo(
                    "Reprojecting AOI to raster CRS."
                )

                transform = QgsCoordinateTransform(
                    aoi_crs,
                    raster_crs,
                    QgsProject.instance(),
                )

                reprojected = QgsVectorLayer(
                    "Polygon",
                    "AOI_reprojected",
                    "memory",
                )

                reprojected.setCrs(raster_crs)

                repro_provider = reprojected.dataProvider()

                for feature in aoi_layer.getFeatures():
                    geometry = feature.geometry()

                    geometry.transform(transform)

                    copied = QgsFeature()
                    copied.setGeometry(geometry)

                    repro_provider.addFeature(copied)

                reprojected.updateExtents()
                clipping_layer = reprojected

            band_name = self.extract_band_name(
                raster_path.name
            )

            output_filename = (
                f"{prefix}_{band_name}.tif"
            )

            output_file = output_path / output_filename

            # Prevent accidental overwrite conflicts when multiple input
            # files resolve to the same band name.
            if output_file.exists():
                counter = 2

                while True:
                    candidate = (
                        output_path
                        / f"{prefix}_{band_name}_{counter}.tif"
                    )

                    if not candidate.exists():
                        output_file = candidate
                        break

                    counter += 1

            try:
                result = processing.run(
                    "gdal:cliprasterbymasklayer",
                    {
                        "INPUT": str(raster_path),
                        "MASK": clipping_layer,
                        "SOURCE_CRS": raster_crs,
                        "TARGET_CRS": raster_crs,
                        "NODATA": None,
                        "ALPHA_BAND": False,
                        "CROP_TO_CUTLINE": True,
                        "KEEP_RESOLUTION": True,
                        "SET_RESOLUTION": False,
                        "X_RESOLUTION": None,
                        "Y_RESOLUTION": None,
                        "MULTITHREADING": True,
                        "OPTIONS": "",
                        "DATA_TYPE": 0,
                        "EXTRA": "",
                        "OUTPUT": str(output_file),
                    },
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

                result_path = result.get("OUTPUT")

                if not result_path:
                    raise RuntimeError(
                        "GDAL returned no output."
                    )

                # Verify that the generated raster can be opened by QGIS.
                clipped = QgsRasterLayer(
                    str(result_path),
                    output_file.stem,
                    "gdal",
                )

                if not clipped.isValid():
                    raise RuntimeError(
                        "Output raster could not be opened."
                    )

                successful.append(
                    {
                        "input": raster_path.name,
                        "band": band_name,
                        "output": str(output_file),
                        "width": clipped.width(),
                        "height": clipped.height(),
                        "bands": clipped.bandCount(),
                        "crs": clipped.crs().authid(),
                        "xres": clipped.rasterUnitsPerPixelX(),
                        "yres": clipped.rasterUnitsPerPixelY(),
                    }
                )

                if load_outputs:
                    layer = QgsRasterLayer(
                        str(output_file),
                        output_file.stem,
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
                            group.insertLayer(
                                0,
                                added_layer,
                            )
                        else:
                            QgsProject.instance().addMapLayer(
                                layer
                            )
                    else:
                        feedback.reportError(
                            "Output was created but could not be loaded: "
                            f"{output_file.name}"
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

        report_lines = [
            "REMOTE SENSE TOOLKIT — BATCH CLIP REPORT",
            "==========================================",
            f"Input folder: {input_folder}",
            f"Output folder: {output_folder}",
            f"Files detected: {len(rasters)}",
            f"Successfully clipped: {len(successful)}",
            f"Failed: {len(failed)}",
            f"AOI CRS: {aoi_crs.authid()}",
            "",
            "SUCCESSFUL OUTPUTS",
            "------------------------------------------",
        ]

        for item in successful:
            report_lines.append(
                f"{item['band']} → "
                f"{Path(item['output']).name}"
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
                    "FAILED OUTPUTS",
                    "------------------------------------------",
                ]
            )

            for filename, reason in failed:
                report_lines.append(
                    f"{filename} → {reason}"
                )

        report_lines.extend(
            [
                "",
                "==========================================",
                "Batch clipping completed.",
            ]
        )

        report = "\n".join(report_lines)

        feedback.pushInfo(report)

        return {
            self.REPORT: report,
        }