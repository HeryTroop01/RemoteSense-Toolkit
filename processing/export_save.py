# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : export_save.py
# Module     : Module 05 — Export & Save Manager
# Version    : 0.1.2
# Project    : RemoteSense Toolkit
# Author     : Punithan
#
# Description:
#     Exports QGIS project layers independently of the other RemoteSense
#     Toolkit processing modules.
#
# Supported source selections:
#     - Selected layers
#     - Named layer groups
#     - All raster layers
#     - All vector layers
#     - All project layers
#
# Raster formats:
#     - GeoTIFF
#     - VRT
#
# Vector formats:
#     - ESRI Shapefile
#     - GeoPackage
#     - GeoJSON
#
# Additional functionality:
#     - Source group-path recreation
#     - Raster compression and tiling
#     - BigTIFF control
#     - Vector selected-feature export
#     - Existing-file conflict handling
#     - Optional loading of exported layers into QGIS
#     - Export report and JSON manifest generation
#
# Status     : Stable
# =============================================================================

from pathlib import Path
import json
import re
import shutil

from qgis.PyQt.QtCore import QCoreApplication

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingOutputString,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterString,
    QgsProcessingParameterBoolean,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsProject,
    QgsVectorFileWriter,
    QgsCoordinateTransformContext,
    QgsProcessingFeatureSourceDefinition,
)


class ExportSaveAlgorithm(QgsProcessingAlgorithm):
    """Export QGIS project layers to common raster and vector formats."""

    SOURCE_MODE = "SOURCE_MODE"
    INPUT_LAYERS = "INPUT_LAYERS"
    GROUP_PATHS = "GROUP_PATHS"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    RASTER_FORMAT = "RASTER_FORMAT"
    VECTOR_FORMAT = "VECTOR_FORMAT"
    PRESERVE_CRS = "PRESERVE_CRS"
    PRESERVE_NODATA = "PRESERVE_NODATA"
    PRESERVE_DATATYPE = "PRESERVE_DATATYPE"
    COMPRESS = "COMPRESS"
    TILED = "TILED"
    BIGTIFF = "BIGTIFF"
    SELECTED_FEATURES = "SELECTED_FEATURES"
    RECREATE_GROUPS = "RECREATE_GROUPS"
    CONFLICT_MODE = "CONFLICT_MODE"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    REPORT = "REPORT"

    SOURCE_OPTIONS = [
        "Selected layers",
        "Named layer groups",
        "All raster layers",
        "All vector layers",
        "All project layers",
    ]

    RASTER_OPTIONS = [
        "GeoTIFF",
        "VRT",
    ]

    VECTOR_OPTIONS = [
        "ESRI Shapefile",
        "GeoPackage",
        "GeoJSON",
    ]

    COMPRESS_OPTIONS = [
        "None",
        "LZW",
        "DEFLATE",
        "ZSTD",
    ]

    BIGTIFF_OPTIONS = [
        "Auto",
        "Yes",
        "No",
    ]

    CONFLICT_OPTIONS = [
        "Skip existing files",
        "Overwrite existing files",
        "Create numbered copy",
    ]

    def tr(self, string):
        """Translate a user-interface string."""
        return QCoreApplication.translate(
            "ExportSaveAlgorithm",
            string,
        )

    def createInstance(self):
        """Create a new Processing algorithm instance."""
        return ExportSaveAlgorithm()

    def name(self):
        """Return the unique Processing algorithm identifier."""
        return "export_save"

    def displayName(self):
        """Return the algorithm name displayed in QGIS."""
        return self.tr("Export & Save Manager")

    def group(self):
        """Return the Processing Toolbox group name."""
        return self.tr("05 — Export & Save")

    def groupId(self):
        """Return the Processing Toolbox group identifier."""
        return "05_export_save"

    def shortHelpString(self):
        """Return the Processing algorithm help description."""
        return self.tr(
            "Export QGIS project layers independently of the other "
            "RemoteSense Toolkit modules. Supports selected layers, "
            "named groups, all raster/vector layers, and the complete "
            "project layer tree. Raster output supports GeoTIFF/VRT; "
            "vector output supports Shapefile, GeoPackage, and GeoJSON."
        )

    def initAlgorithm(self, config=None):
        """Define Processing parameters and outputs."""

        self.addParameter(
            QgsProcessingParameterEnum(
                self.SOURCE_MODE,
                self.tr("Export source"),
                options=self.SOURCE_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_LAYERS,
                self.tr("Selected raster/vector layers"),
                layerType=QgsProcessing.TypeMapLayer,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.GROUP_PATHS,
                self.tr(
                    "Layer group names/paths "
                    "(one per line; e.g. Band Sets or Raw/Imported)"
                ),
                defaultValue="",
                multiLine=True,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr("Output folder"),
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.RASTER_FORMAT,
                self.tr("Raster export format"),
                options=self.RASTER_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.VECTOR_FORMAT,
                self.tr("Vector export format"),
                options=self.VECTOR_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PRESERVE_CRS,
                self.tr("Preserve source CRS"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PRESERVE_NODATA,
                self.tr("Preserve raster NoData"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PRESERVE_DATATYPE,
                self.tr("Preserve raster data type"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.COMPRESS,
                self.tr("GeoTIFF compression"),
                options=self.COMPRESS_OPTIONS,
                defaultValue=1,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.TILED,
                self.tr("Create tiled GeoTIFF"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.BIGTIFF,
                self.tr("BigTIFF"),
                options=self.BIGTIFF_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.SELECTED_FEATURES,
                self.tr("Export selected vector features only"),
                defaultValue=False,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.RECREATE_GROUPS,
                self.tr("Recreate source layer-group structure"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.CONFLICT_MODE,
                self.tr("If an output file already exists"),
                options=self.CONFLICT_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_OUTPUTS,
                self.tr("Load exported layers into QGIS"),
                defaultValue=False,
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.REPORT,
                self.tr("Export report"),
            )
        )

    # ------------------------------------------------------------------
    # Layer-tree utilities
    # ------------------------------------------------------------------

    def _walk_group(self, group, path_parts=None):
        """Recursively yield layers together with their group paths."""

        path_parts = list(path_parts or [])
        current_path = path_parts + [group.name()]

        for child in group.children():
            if hasattr(child, "layer") and child.layer() is not None:
                yield child.layer(), current_path
            elif hasattr(child, "children"):
                yield from self._walk_group(
                    child,
                    current_path,
                )

    def _normalise_group_path(self, value):
        """Normalize a user-provided layer-group path."""

        value = value.strip().replace("\\", "/")
        value = re.sub(r"/+", "/", value)

        return value.strip("/")

    def _collect_layers(
        self,
        mode,
        input_layers,
        group_paths,
    ):
        """Collect project layers according to the selected source mode."""

        root = QgsProject.instance().layerTreeRoot()

        if mode == 0:
            layers = []
            seen = set()

            for layer in input_layers:
                if layer is None or not layer.isValid():
                    continue

                if layer.id() not in seen:
                    layers.append(
                        (
                            layer,
                            self._layer_path(
                                layer,
                                root,
                            ),
                        )
                    )
                    seen.add(layer.id())

            return layers

        all_tree_layers = list(
            self._walk_group(
                root,
                [],
            )
        )

        if mode == 1:
            requested = {
                self._normalise_group_path(value)
                for value in group_paths.splitlines()
                if self._normalise_group_path(value)
            }

            if not requested:
                raise QgsProcessingException(
                    "Named layer groups were selected, but no group "
                    "names or paths were provided."
                )

            selected = []
            seen = set()

            for layer, path_parts in all_tree_layers:
                path = (
                    "/".join(path_parts[1:])
                    if path_parts
                    else ""
                )

                group_name = (
                    path_parts[-1]
                    if path_parts
                    else ""
                )

                if (
                    path in requested
                    or group_name in requested
                ):
                    if layer.id() not in seen:
                        selected.append(
                            (
                                layer,
                                path_parts,
                            )
                        )
                        seen.add(layer.id())

            return selected

        selected = []
        seen = set()

        for layer, path_parts in all_tree_layers:
            if (
                mode == 2
                and not isinstance(layer, QgsRasterLayer)
            ):
                continue

            if (
                mode == 3
                and not isinstance(layer, QgsVectorLayer)
            ):
                continue

            if layer.id() not in seen:
                selected.append(
                    (
                        layer,
                        path_parts,
                    )
                )
                seen.add(layer.id())

        return selected

    def _layer_path(self, layer, root):
        """Return the layer's position within the QGIS layer tree."""

        node = root.findLayer(layer.id())

        if node is None:
            return [
                root.name(),
                layer.name(),
            ]

        names = []
        current = node.parent()

        while current is not None:
            names.insert(
                0,
                current.name(),
            )
            current = current.parent()

        names.append(layer.name())

        return names

    # ------------------------------------------------------------------
    # Filename and conflict utilities
    # ------------------------------------------------------------------

    def _safe_name(self, name):
        """Create a filesystem-safe name."""

        value = re.sub(
            r'[<>:"/\\|?*]+',
            "_",
            name,
        ).strip()

        value = value.rstrip(". ")

        return value or "layer"

    def _unique_path(
        self,
        path,
        conflict_mode,
    ):
        """Resolve an existing destination according to conflict policy."""

        if not path.exists():
            return path

        if conflict_mode == 0:
            return None

        if conflict_mode == 1:
            try:
                if path.is_file():
                    path.unlink()
                else:
                    shutil.rmtree(path)

            except Exception as exc:
                raise QgsProcessingException(
                    f"Could not overwrite {path}: {exc}"
                )

            return path

        return self._numbered_copy_path(path)

    def _numbered_copy_path(
        self,
        path,
        reserved=None,
    ):
        """Return the next unused numbered destination path."""

        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        reserved = reserved or set()

        index = 1

        while True:
            candidate = (
                parent
                / f"{stem}_{index}{suffix}"
            )

            if (
                not candidate.exists()
                and candidate not in reserved
            ):
                return candidate

            index += 1

    def _destination_directory(
        self,
        output_root,
        path_parts,
        recreate,
        layer=None,
        vector_format=0,
    ):
        """Build the output directory from the layer-tree hierarchy."""

        if not recreate:
            destination = output_root

        else:
            # _layer_path() returns:
            # [root, group1, ..., groupN, layer].
            groups = (
                path_parts[1:-1]
                if len(path_parts) >= 2
                else []
            )

            destination = output_root

            for group in groups:
                destination = (
                    destination
                    / self._safe_name(group)
                )

        # Shapefile consists of multiple sidecar files. Keep all sidecars
        # together inside a directory named after the source layer.
        if (
            isinstance(layer, QgsVectorLayer)
            and vector_format == 0
        ):
            destination = (
                destination
                / self._safe_name(layer.name())
            )

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        return destination

    # ------------------------------------------------------------------
    # Raster export
    # ------------------------------------------------------------------

    def _export_raster(
        self,
        layer,
        destination,
        raster_format,
        compress,
        tiled,
        bigtiff,
        preserve_nodata,
        feedback,
    ):
        """Export a raster layer through GDAL Translate."""

        from osgeo import gdal

        source = layer.source()

        if not source:
            raise QgsProcessingException(
                f"No raster source is available for "
                f"'{layer.name()}'."
            )

        creation_options = []

        if compress != 0:
            creation_options.append(
                f"COMPRESS="
                f"{self.COMPRESS_OPTIONS[compress]}"
            )

        if (
            tiled
            and raster_format == 0
        ):
            creation_options.append(
                "TILED=YES"
            )

        if (
            bigtiff == 1
            and raster_format == 0
        ):
            creation_options.append(
                "BIGTIFF=YES"
            )

        elif (
            bigtiff == 2
            and raster_format == 0
        ):
            creation_options.append(
                "BIGTIFF=NO"
            )

        format_name = (
            "GTiff"
            if raster_format == 0
            else "VRT"
        )

        options = gdal.TranslateOptions(
            format=format_name,
            creationOptions=creation_options,
            noData=None,
        )

        if preserve_nodata:
            # GDAL Translate normally carries source NoData forward.
            options = gdal.TranslateOptions(
                format=format_name,
                creationOptions=creation_options,
            )

        result = gdal.Translate(
            str(destination),
            source,
            options=options,
        )

        if (
            result is None
            or not destination.exists()
        ):
            message = gdal.GetLastErrorMsg()

            raise QgsProcessingException(
                f"Raster export failed for "
                f"'{layer.name()}'. "
                f"GDAL: {message}"
            )

        result.FlushCache()
        result = None

    # ------------------------------------------------------------------
    # Vector export
    # ------------------------------------------------------------------

    def _export_vector(
        self,
        layer,
        destination,
        vector_format,
        preserve_crs,
        selected_features,
    ):
        """Export a vector layer using QgsVectorFileWriter."""

        if not isinstance(
            layer,
            QgsVectorLayer,
        ):
            raise QgsProcessingException(
                f"'{layer.name()}' is not a vector layer."
            )

        format_name = (
            self.VECTOR_OPTIONS[
                vector_format
            ]
        )

        if format_name == "ESRI Shapefile":
            driver = "ESRI Shapefile"

        elif format_name == "GeoPackage":
            driver = "GPKG"

        else:
            driver = "GeoJSON"

        source_crs = layer.crs()
        target_crs = (
            source_crs
            if preserve_crs
            else None
        )

        options = (
            QgsVectorFileWriter.SaveVectorOptions()
        )

        options.driverName = driver
        options.fileEncoding = "UTF-8"
        options.actionOnExistingFile = (
            QgsVectorFileWriter.CreateOrOverwriteFile
        )

        if (
            selected_features
            and layer.selectedFeatureCount() > 0
        ):
            save_layer = layer.materialize(
                QgsProcessingFeatureSourceDefinition(
                    layer.source(),
                    selectedFeaturesOnly=True,
                    featureLimit=-1,
                )
            )

        else:
            save_layer = layer

        result = (
            QgsVectorFileWriter.writeAsVectorFormatV3(
                save_layer,
                str(destination),
                QgsCoordinateTransformContext(),
                options,
            )
        )

        error_code = result[0]

        if (
            error_code
            != QgsVectorFileWriter.NoError
        ):
            error_message = (
                result[1]
                if len(result) > 1
                else "Unknown error"
            )

            raise QgsProcessingException(
                f"Vector export failed for "
                f"'{layer.name()}': "
                f"{error_message}"
            )

    # ------------------------------------------------------------------
    # Main algorithm
    # ------------------------------------------------------------------

    def processAlgorithm(
        self,
        parameters,
        context,
        feedback,
    ):
        """Execute the export operation."""

        mode = self.parameterAsEnum(
            parameters,
            self.SOURCE_MODE,
            context,
        )

        input_layers = self.parameterAsLayerList(
            parameters,
            self.INPUT_LAYERS,
            context,
        )

        group_paths = self.parameterAsString(
            parameters,
            self.GROUP_PATHS,
            context,
        )

        output_folder = self.parameterAsString(
            parameters,
            self.OUTPUT_FOLDER,
            context,
        )

        raster_format = self.parameterAsEnum(
            parameters,
            self.RASTER_FORMAT,
            context,
        )

        vector_format = self.parameterAsEnum(
            parameters,
            self.VECTOR_FORMAT,
            context,
        )

        preserve_crs = self.parameterAsBool(
            parameters,
            self.PRESERVE_CRS,
            context,
        )

        preserve_nodata = self.parameterAsBool(
            parameters,
            self.PRESERVE_NODATA,
            context,
        )

        preserve_datatype = self.parameterAsBool(
            parameters,
            self.PRESERVE_DATATYPE,
            context,
        )

        compress = self.parameterAsEnum(
            parameters,
            self.COMPRESS,
            context,
        )

        tiled = self.parameterAsBool(
            parameters,
            self.TILED,
            context,
        )

        bigtiff = self.parameterAsEnum(
            parameters,
            self.BIGTIFF,
            context,
        )

        selected_features = self.parameterAsBool(
            parameters,
            self.SELECTED_FEATURES,
            context,
        )

        recreate_groups = self.parameterAsBool(
            parameters,
            self.RECREATE_GROUPS,
            context,
        )

        conflict_mode = self.parameterAsEnum(
            parameters,
            self.CONFLICT_MODE,
            context,
        )

        load_outputs = self.parameterAsBool(
            parameters,
            self.LOAD_OUTPUTS,
            context,
        )

        output_root = Path(
            output_folder
        )

        if not output_folder:
            raise QgsProcessingException(
                "Output folder was not provided."
            )

        output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        layers = self._collect_layers(
            mode,
            input_layers,
            group_paths,
        )

        if not layers:
            raise QgsProcessingException(
                "No valid layers were found for export."
            )

        feedback.pushInfo(
            f"Export source contains "
            f"{len(layers)} layer(s)."
        )

        exported = []
        skipped = []
        failed = []

        # Reserve destinations during this execution so two different
        # QGIS layers with the same display name cannot overwrite each other.
        reserved_destinations = set()

        for index, (layer, path_parts) in enumerate(
            layers,
            1,
        ):
            if feedback.isCanceled():
                break

            feedback.setProgress(
                int(
                    (index - 1)
                    * 100
                    / max(len(layers), 1)
                )
            )

            try:
                destination_dir = (
                    self._destination_directory(
                        output_root,
                        path_parts,
                        recreate_groups,
                        layer=layer,
                        vector_format=vector_format,
                    )
                )

                if isinstance(
                    layer,
                    QgsRasterLayer,
                ):
                    extension = (
                        ".tif"
                        if raster_format == 0
                        else ".vrt"
                    )

                elif isinstance(
                    layer,
                    QgsVectorLayer,
                ):
                    extension = (
                        ".shp"
                        if vector_format == 0
                        else ".gpkg"
                        if vector_format == 1
                        else ".geojson"
                    )

                else:
                    skipped.append(
                        (
                            layer.name(),
                            "Unsupported layer type",
                        )
                    )
                    continue

                base_name = self._safe_name(
                    layer.name()
                )

                destination = (
                    destination_dir
                    / f"{base_name}{extension}"
                )

                # Resolve destinations already reserved by another source
                # layer in the current execution before applying the
                # existing-file policy.
                if (
                    destination
                    in reserved_destinations
                ):
                    destination = (
                        self._numbered_copy_path(
                            destination
                        )
                    )

                destination = self._unique_path(
                    destination,
                    conflict_mode,
                )

                if destination is None:
                    skipped.append(
                        (
                            layer.name(),
                            "Output already exists",
                        )
                    )

                    feedback.pushInfo(
                        f"Skipped existing output: "
                        f"{layer.name()}"
                    )

                    continue

                if isinstance(
                    layer,
                    QgsRasterLayer,
                ):
                    self._export_raster(
                        layer,
                        destination,
                        raster_format,
                        compress,
                        tiled,
                        bigtiff,
                        preserve_nodata,
                        feedback,
                    )

                elif isinstance(
                    layer,
                    QgsVectorLayer,
                ):
                    self._export_vector(
                        layer,
                        destination,
                        vector_format,
                        preserve_crs,
                        selected_features,
                    )

                reserved_destinations.add(
                    destination
                )

                exported.append(
                    {
                        "layer": layer.name(),
                        "type": (
                            "Raster"
                            if isinstance(
                                layer,
                                QgsRasterLayer,
                            )
                            else "Vector"
                        ),
                        "output": str(
                            destination
                        ),
                    }
                )

                feedback.pushInfo(
                    f"Exported: "
                    f"{layer.name()} → "
                    f"{destination}"
                )

                if load_outputs:
                    if isinstance(
                        layer,
                        QgsRasterLayer,
                    ):
                        new_layer = QgsRasterLayer(
                            str(destination),
                            destination.stem,
                            "gdal",
                        )

                    else:
                        new_layer = QgsVectorLayer(
                            str(destination),
                            destination.stem,
                            "ogr",
                        )

                    if new_layer.isValid():
                        QgsProject.instance().addMapLayer(
                            new_layer
                        )

                    else:
                        feedback.reportError(
                            "Export succeeded but output "
                            f"could not be loaded: "
                            f"{destination}"
                        )

            except Exception as exc:
                failed.append(
                    {
                        "layer": layer.name(),
                        "error": str(exc),
                    }
                )

                feedback.reportError(
                    f"Failed: {layer.name()} — {exc}"
                )

        report = self._build_report(
            output_root,
            mode,
            layers,
            exported,
            skipped,
            failed,
            recreate_groups,
        )

        report_path = (
            output_root
            / "RemoteSense_Export_Report.txt"
        )

        report_path.write_text(
            report,
            encoding="utf-8",
        )

        definition = {
            "version": "0.1.2",
            "module": "Export & Save Manager",
            "source_mode": self.SOURCE_OPTIONS[mode],
            "output_folder": str(output_root),
            "recreate_groups": recreate_groups,
            "exported": exported,
            "skipped": [
                {
                    "layer": item[0],
                    "reason": item[1],
                }
                for item in skipped
            ],
            "failed": failed,
        }

        json_path = (
            output_root
            / "RemoteSense_Export_Manifest.json"
        )

        json_path.write_text(
            json.dumps(
                definition,
                indent=4,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        feedback.setProgress(100)
        feedback.pushInfo(report)

        return {
            self.REPORT: report,
        }

    def _build_report(
        self,
        output_root,
        mode,
        layers,
        exported,
        skipped,
        failed,
        recreate_groups,
    ):
        """Build the human-readable export report."""

        lines = [
            "REMOTE SENSE TOOLKIT — EXPORT & SAVE REPORT",
            "============================================",
            "Module version: 0.1.2",
            f"Source mode: {self.SOURCE_OPTIONS[mode]}",
            f"Output folder: {output_root}",
            f"Source layers: {len(layers)}",
            f"Exported: {len(exported)}",
            f"Skipped: {len(skipped)}",
            f"Failed: {len(failed)}",
            (
                "Recreated groups: "
                f"{'Yes' if recreate_groups else 'No'}"
            ),
            "",
            "EXPORTED",
            "--------------------------------------------",
        ]

        for item in exported:
            lines.append(
                f"{item['type']}: "
                f"{item['layer']} → "
                f"{item['output']}"
            )

        if skipped:
            lines += [
                "",
                "SKIPPED",
                "--------------------------------------------",
            ]

            for name, reason in skipped:
                lines.append(
                    f"{name}: {reason}"
                )

        if failed:
            lines += [
                "",
                "FAILED",
                "--------------------------------------------",
            ]

            for item in failed:
                lines.append(
                    f"{item['layer']}: "
                    f"{item['error']}"
                )

        lines += [
            "",
            "============================================",
            "Export operation completed.",
        ]

        return "\n".join(lines)