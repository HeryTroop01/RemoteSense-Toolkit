# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : create_band_set.py
# Module     : Module 05 — Band Set Creation
# Version    : 0.4.6
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Creates deterministic multiband raster band sets from selected QGIS
#     raster layers, validates spatial compatibility, preserves source-band
#     identity, stores per-band metadata, and optionally loads the outputs
#     into QGIS with an appropriate renderer.
#
# Status     : Stable
# =============================================================================

from pathlib import Path
import json
import re
import tempfile
import shutil

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingOutputString,
    QgsRasterLayer,
    QgsProject,
)


class CreateBandSetAlgorithm(QgsProcessingAlgorithm):
    """Create a validated multiband raster band set."""

    INPUT_RASTERS = "INPUT_RASTERS"
    SATELLITE = "SATELLITE"
    BAND_SET_NAME = "BAND_SET_NAME"
    BAND_MIN_VALUES = "BAND_MIN_VALUES"
    BAND_MAX_VALUES = "BAND_MAX_VALUES"
    OUTPUT_FORMAT = "OUTPUT_FORMAT"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    GROUP_NAME = "GROUP_NAME"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    REPORT = "REPORT"

    SENSOR_OPTIONS = [
        "Sentinel-2",
        "Landsat 8/9",
        "Landsat 5/7",
        "MODIS",
        "Sentinel-1 SAR",
        "Custom",
    ]

    SENSOR_BANDS = {
        "Sentinel-2": {
            "B01": "Coastal Aerosol",
            "B02": "Blue",
            "B03": "Green",
            "B04": "Red",
            "B05": "Red Edge 1",
            "B06": "Red Edge 2",
            "B07": "Red Edge 3",
            "B08": "NIR",
            "B8A": "Narrow NIR",
            "B09": "Water Vapor",
            "B10": "Cirrus",
            "B11": "SWIR 1",
            "B12": "SWIR 2",
            "AOT": "Aerosol Optical Thickness",
            "WVP": "Water Vapour",
            "SCL": "Scene Classification",
            "TCI": "True Color Image",
        },
        "Landsat 8/9": {
            "B01": "Coastal / Aerosol",
            "B02": "Blue",
            "B03": "Green",
            "B04": "Red",
            "B05": "NIR",
            "B06": "SWIR 1",
            "B07": "SWIR 2",
            "B08": "Panchromatic",
            "B09": "Cirrus",
            "B10": "Thermal Infrared 1",
            "B11": "Thermal Infrared 2",
        },
        "Landsat 5/7": {
            "B01": "Blue / Green",
            "B02": "Green",
            "B03": "Red",
            "B04": "NIR",
            "B05": "SWIR 1",
            "B06": "Thermal Infrared",
            "B07": "SWIR 2",
            "B08": "Panchromatic",
        },
        "MODIS": {
            "B01": "Red",
            "B02": "NIR",
            "B03": "Blue",
            "B04": "Green",
            "B05": "NIR / SWIR",
            "B06": "SWIR",
            "B07": "SWIR",
        },
        "Sentinel-1 SAR": {
            "VV": "VV Polarization",
            "VH": "VH Polarization",
            "HH": "HH Polarization",
            "HV": "HV Polarization",
            "VV-VH": "VV − VH",
            "VH-VV": "VH − VV",
            "VV/VH": "VV / VH Ratio",
            "VH/VV": "VH / VV Ratio",
        },
    }

    def tr(self, string):
        """Translate a user-interface string."""
        return QCoreApplication.translate(
            "CreateBandSetAlgorithm",
            string,
        )

    def createInstance(self):
        """Create a new instance of the Processing algorithm."""
        return CreateBandSetAlgorithm()

    def name(self):
        """Return the unique Processing algorithm identifier."""
        return "create_band_set"

    def displayName(self):
        """Return the algorithm name displayed in QGIS."""
        return self.tr("Create Band Set")

    def group(self):
        """Return the Processing Toolbox group name."""
        return self.tr("04 — Extraction")

    def groupId(self):
        """Return the unique Processing Toolbox group identifier."""
        return "04_extraction"

    def shortHelpString(self):
        """Return the algorithm help description."""
        return self.tr(
            "Creates a multiband raster from selected raster channels. "
            "Each actual source channel becomes exactly one output band. "
            "Color-composite controls are intentionally omitted. "
            "Per-band display minimum and maximum values are stored."
        )

    def initAlgorithm(self, config=None):
        """Define Processing parameters and outputs."""

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_RASTERS,
                self.tr("Input raster layers"),
                QgsProcessing.TypeRaster,
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.SATELLITE,
                self.tr("Satellite / dataset"),
                options=self.SENSOR_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.BAND_SET_NAME,
                self.tr("Band Set name"),
                defaultValue="Sentinel-2_10m",
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.BAND_MIN_VALUES,
                self.tr("Band minimum values"),
                defaultValue="0",
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.BAND_MAX_VALUES,
                self.tr(
                    "Band maximum values "
                    "(one value or comma-separated per band)"
                ),
                defaultValue="",
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.OUTPUT_FORMAT,
                self.tr("Output format"),
                options=["VRT", "GeoTIFF", "Both"],
                defaultValue=0,
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
                self.GROUP_NAME,
                self.tr("QGIS layer group name"),
                defaultValue="Band Sets",
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_OUTPUTS,
                self.tr("Load output into QGIS"),
                defaultValue=True,
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.REPORT,
                self.tr("Band Set report"),
            )
        )

    def extract_band_name(self, filename):
        """Extract a recognizable band or polarization identifier."""

        stem = Path(filename).stem

        patterns = [
            r"(?i)(?:^|[_\-\s])(B(?:0?[1-9]|1[0-2]|8A))(?=[_\-\s.]|$)",
            r"(?i)(B8A)",
            r"(?i)(B(?:0?[1-9]|1[0-2]))",
            r"(?i)(VV[-_]?VH|VH[-_]?VV|VV[/]VH|VH[/]VV)",
            r"(?i)(VV|VH|HH|HV)",
            r"(?i)(AOT|WVP|SCL|TCI)",
        ]

        for pattern in patterns:
            match = re.search(pattern, stem)

            if match:
                return match.group(1).upper().replace("_", "-")

        return stem

    def semantic_band_name(self, sensor, detected):
        """Return the sensor-specific descriptive name for a band."""

        key = detected.upper().replace("_", "-")

        return self.SENSOR_BANDS.get(
            sensor,
            {},
        ).get(
            key,
            key,
        )

    def _safe_name(self, name):
        """Create a filesystem-safe output name."""

        value = re.sub(
            r"[^A-Za-z0-9_\-]+",
            "_",
            name,
        ).strip("_")

        return value or "Band_Set"

    def _parse_values(
        self,
        text,
        band_count,
        label,
        default=None,
        required=False,
    ):
        """Parse one value or one comma-separated value per band."""

        raw = (text or "").strip()

        if not raw:
            if required:
                raise QgsProcessingException(
                    self.tr(
                        f"{label} are required. "
                        "Enter one value per band."
                    )
                )

            return [float(default)] * band_count

        parts = [
            part.strip()
            for part in raw.split(",")
            if part.strip()
        ]

        try:
            values = [float(part) for part in parts]
        except ValueError:
            raise QgsProcessingException(
                self.tr(
                    f"{label} must contain numeric "
                    "comma-separated values."
                )
            )

        if len(values) == 1:
            return values * band_count

        if len(values) != band_count:
            raise QgsProcessingException(
                self.tr(
                    f"{label}: expected one value or "
                    f"{band_count} values, but received "
                    f"{len(values)}."
                )
            )

        return values

    def _source_band_description(
        self,
        layer,
        source_band,
        sensor,
    ):
        """Determine the detected and descriptive source-band names."""

        detected = self.extract_band_name(
            Path(layer.source()).name
        )

        if layer.bandCount() == 1:
            return (
                detected,
                self.semantic_band_name(
                    sensor,
                    detected,
                ),
            )

        description = ""

        try:
            description = (
                layer.dataProvider().bandDescription(
                    source_band
                )
                or ""
            )
        except Exception:
            description = ""

        if description.strip():
            return (
                f"{description.strip()}_{source_band}",
                description.strip(),
            )

        return (
            f"{detected}_{source_band}",
            f"{detected} — Channel {source_band}",
        )

    def _collect_output_bands(
        self,
        rasters,
        sensor,
        feedback,
    ):
        """Build the ordered list of source bands for the output stack."""

        entries = []
        used = set()
        order = 1

        for raster in rasters:
            for source_band in range(
                1,
                raster.bandCount() + 1,
            ):
                detected, display_name = (
                    self._source_band_description(
                        raster,
                        source_band,
                        sensor,
                    )
                )

                if display_name in used:
                    display_name = (
                        f"{display_name} "
                        f"({raster.name()} B{source_band})"
                    )

                used.add(display_name)

                entries.append(
                    {
                        "order": order,
                        "source_layer": raster.name(),
                        "source": raster.source(),
                        "source_band": source_band,
                        "detected_name": detected,
                        "display_name": display_name,
                    }
                )

                feedback.pushInfo(
                    f"Output Band {order}: {display_name} <- "
                    f"{raster.name()} "
                    f"[source band {source_band}]"
                )

                order += 1

        return entries

    def validate_rasters(self, rasters, feedback):
        """Validate spatial compatibility of all input rasters."""

        reference = rasters[0]

        reference_crs = reference.crs()
        reference_width = reference.width()
        reference_height = reference.height()
        reference_extent = reference.extent()

        reference_xres = (
            reference_extent.width() / reference_width
            if reference_width
            else 0
        )

        reference_yres = (
            reference_extent.height() / reference_height
            if reference_height
            else 0
        )

        for raster in rasters[1:]:
            if raster.crs() != reference_crs:
                raise QgsProcessingException(
                    f"Raster CRS mismatch: {raster.name()} "
                    f"({raster.crs().authid()}) vs "
                    f"{reference_crs.authid()}"
                )

            if (
                raster.width() != reference_width
                or raster.height() != reference_height
            ):
                raise QgsProcessingException(
                    f"Raster dimensions do not match: "
                    f"{raster.name()} "
                    f"({raster.width()} × {raster.height()})"
                )

            extent = raster.extent()

            xres = (
                extent.width() / raster.width()
                if raster.width()
                else 0
            )

            yres = (
                extent.height() / raster.height()
                if raster.height()
                else 0
            )

            tolerance = 1e-6

            if (
                abs(xres - reference_xres) > tolerance
                or abs(yres - reference_yres) > tolerance
            ):
                raise QgsProcessingException(
                    f"Raster resolution mismatch: "
                    f"{raster.name()}"
                )

            if not (
                abs(
                    extent.xMinimum()
                    - reference_extent.xMinimum()
                ) <= tolerance
                and abs(
                    extent.xMaximum()
                    - reference_extent.xMaximum()
                ) <= tolerance
                and abs(
                    extent.yMinimum()
                    - reference_extent.yMinimum()
                ) <= tolerance
                and abs(
                    extent.yMaximum()
                    - reference_extent.yMaximum()
                ) <= tolerance
            ):
                raise QgsProcessingException(
                    f"Raster extent mismatch: "
                    f"{raster.name()}"
                )

        feedback.pushInfo(
            "Raster compatibility validation passed."
        )

        return {
            "crs": reference_crs.authid(),
            "width": reference_width,
            "height": reference_height,
            "xres": reference_xres,
            "yres": reference_yres,
            "extent": reference_extent,
        }

    def _set_band_descriptions(
        self,
        path,
        descriptions,
        feedback,
    ):
        """Write descriptive names to output raster bands."""

        try:
            from osgeo import gdal

            dataset = gdal.Open(
                str(path),
                gdal.GA_Update,
            )

            if dataset is None:
                feedback.reportError(
                    f"Could not open output for band descriptions: "
                    f"{path}"
                )
                return False

            for index, description in enumerate(
                descriptions,
                1,
            ):
                band = dataset.GetRasterBand(index)

                if band:
                    band.SetDescription(
                        str(description)
                    )

            dataset.FlushCache()
            dataset = None

            return True

        except Exception as exc:
            feedback.reportError(
                f"Band descriptions could not be written to "
                f"{path}: {exc}"
            )
            return False

    def _set_band_metadata(
        self,
        path,
        entries,
        mins,
        maxs,
        feedback,
    ):
        """Store RemoteSense Toolkit metadata on output bands."""

        try:
            from osgeo import gdal

            dataset = gdal.Open(
                str(path),
                gdal.GA_Update,
            )

            if dataset is None:
                return False

            for entry, min_value, max_value in zip(
                entries,
                mins,
                maxs,
            ):
                band = dataset.GetRasterBand(
                    entry["order"]
                )

                if band:
                    band.SetMetadataItem(
                        "REMOTE_SENSE_MIN",
                        str(min_value),
                    )

                    band.SetMetadataItem(
                        "REMOTE_SENSE_MAX",
                        str(max_value),
                    )

                    band.SetMetadataItem(
                        "REMOTE_SENSE_SOURCE",
                        f"{entry['source_layer']}|"
                        f"band={entry['source_band']}",
                    )

            dataset.FlushCache()
            dataset = None

            return True

        except Exception as exc:
            feedback.reportError(
                f"Band display metadata could not be written: "
                f"{exc}"
            )
            return False

    def _make_single_band_vrt(
        self,
        source,
        source_band,
        destination,
    ):
        """Create a single-band VRT referencing a source raster band."""

        from osgeo import gdal

        dataset = gdal.Open(
            str(source),
            gdal.GA_ReadOnly,
        )

        if dataset is None:
            raise QgsProcessingException(
                f"Could not open source raster: {source}"
            )

        try:
            result = gdal.Translate(
                str(destination),
                dataset,
                format="VRT",
                bandList=[source_band],
            )
        finally:
            dataset = None

        if (
            result is None
            or not destination.exists()
        ):
            error = gdal.GetLastErrorMsg()

            raise QgsProcessingException(
                f"Could not create single-band VRT for "
                f"{source} band {source_band}. "
                f"GDAL: {error}"
            )

        result = None

    def _xml_escape(self, value):
        """Escape a value for insertion into VRT XML."""

        value = str(value)
        return (
            value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _build_bandset_vrt(
        self,
        output_vrt,
        entries,
        feedback,
    ):
        """Build and validate a deterministic multiband VRT."""

        from osgeo import gdal

        if not entries:
            raise QgsProcessingException(
                "No bands available for VRT creation."
            )

        first_dataset = gdal.Open(
            str(entries[0]["source"]),
            gdal.GA_ReadOnly,
        )

        if first_dataset is None:
            raise QgsProcessingException(
                f"Could not open source raster: "
                f"{entries[0]['source']}"
            )

        try:
            width = first_dataset.RasterXSize
            height = first_dataset.RasterYSize
            projection = first_dataset.GetProjection()
            geotransform = first_dataset.GetGeoTransform()
        finally:
            first_dataset = None

        data_types = []
        nodata_values = []

        for entry in entries:
            dataset = gdal.Open(
                str(entry["source"]),
                gdal.GA_ReadOnly,
            )

            if dataset is None:
                raise QgsProcessingException(
                    f"Could not open source raster: "
                    f"{entry['source']}"
                )

            try:
                if (
                    dataset.RasterXSize != width
                    or dataset.RasterYSize != height
                ):
                    raise QgsProcessingException(
                        "Source raster dimensions changed: "
                        f"{entry['source']}"
                    )

                band = dataset.GetRasterBand(
                    int(entry["source_band"])
                )

                if band is None:
                    raise QgsProcessingException(
                        "Could not access source band "
                        f"{entry['source_band']} in "
                        f"{entry['source']}"
                    )

                data_types.append(
                    gdal.GetDataTypeName(
                        band.DataType
                    )
                )

                nodata_values.append(
                    band.GetNoDataValue()
                )

            finally:
                dataset = None

        geotransform_text = ", ".join(
            f"{float(value):.15g}"
            for value in geotransform
        )

        parts = [
            f'<VRTDataset rasterXSize="{width}" '
            f'rasterYSize="{height}">'
        ]

        if projection:
            parts.append(
                '<SRS dataAxisToSRSAxisMapping="1,2">'
                + self._xml_escape(projection)
                + "</SRS>"
            )

        parts.append(
            f"<GeoTransform>{geotransform_text}</GeoTransform>"
        )

        for index, entry in enumerate(
            entries,
            1,
        ):
            data_type = data_types[index - 1]

            parts.append(
                f'<VRTRasterBand '
                f'dataType="{self._xml_escape(data_type)}" '
                f'band="{index}">'
            )

            parts.append(
                "<Description>"
                + self._xml_escape(
                    entry["display_name"]
                )
                + "</Description>"
            )

            nodata = nodata_values[index - 1]

            if nodata is not None:
                parts.append(
                    f"<NoDataValue>{nodata}</NoDataValue>"
                )

            parts.append("<SimpleSource>")

            parts.append(
                '<SourceFilename relativeToVRT="0">'
                + self._xml_escape(
                    Path(
                        entry["source"]
                    ).resolve()
                )
                + "</SourceFilename>"
            )

            parts.append(
                f"<SourceBand>"
                f"{int(entry['source_band'])}"
                f"</SourceBand>"
            )

            parts.append(
                f'<SourceProperties '
                f'RasterXSize="{width}" '
                f'RasterYSize="{height}" '
                f'DataType="{self._xml_escape(data_type)}" '
                f'BlockXSize="{width}" '
                f'BlockYSize="1"/>'
            )

            parts.append(
                f'<SrcRect xOff="0" yOff="0" '
                f'xSize="{width}" '
                f'ySize="{height}"/>'
            )

            parts.append(
                f'<DstRect xOff="0" yOff="0" '
                f'xSize="{width}" '
                f'ySize="{height}"/>'
            )

            parts.append("</SimpleSource>")
            parts.append("</VRTRasterBand>")

        parts.append("</VRTDataset>")

        output_vrt.write_text(
            "\n".join(parts),
            encoding="utf-8",
        )

        if not output_vrt.exists():
            raise QgsProcessingException(
                f"VRT creation failed: {output_vrt}"
            )

        check = gdal.Open(
            str(output_vrt),
            gdal.GA_ReadOnly,
        )

        if check is None:
            error = gdal.GetLastErrorMsg()

            raise QgsProcessingException(
                "VRT creation failed during GDAL validation. "
                f"GDAL: {error}"
            )

        actual_bands = check.RasterCount
        check = None

        if actual_bands != len(entries):
            raise QgsProcessingException(
                f"VRT validation failed: expected "
                f"{len(entries)} bands, found "
                f"{actual_bands}."
            )

        feedback.pushInfo(
            f"VRT created and validated successfully: "
            f"{output_vrt.name} "
            f"({actual_bands} bands)"
        )

    def _load_output(
        self,
        output,
        group,
        sensor,
        entries,
        mins,
        maxs,
        feedback,
    ):
        """Load an output raster and configure its QGIS metadata."""

        layer = QgsRasterLayer(
            str(output),
            output.stem,
            "gdal",
        )

        if not layer.isValid():
            feedback.reportError(
                f"Output could not be loaded: {output}"
            )
            return None

        QgsProject.instance().addMapLayer(
            layer,
            False,
        )

        group.addLayer(layer)

        self._set_band_descriptions(
            output,
            [
                entry["display_name"]
                for entry in entries
            ],
            feedback,
        )

        self._set_band_metadata(
            output,
            entries,
            mins,
            maxs,
            feedback,
        )

        layer.reload()

        layer.setCustomProperty(
            "RemoteSenseToolkit/satellite",
            sensor,
        )

        layer.setCustomProperty(
            "RemoteSenseToolkit/band_set",
            output.stem,
        )

        layer.setCustomProperty(
            "RemoteSenseToolkit/band_count",
            len(entries),
        )

        for entry, min_value, max_value in zip(
            entries,
            mins,
            maxs,
        ):
            index = entry["order"]

            layer.setCustomProperty(
                f"RemoteSenseToolkit/band_{index}_name",
                entry["display_name"],
            )

            layer.setCustomProperty(
                f"RemoteSenseToolkit/band_{index}_source",
                f"{entry['source_layer']} | "
                f"source band {entry['source_band']}",
            )

            layer.setCustomProperty(
                f"RemoteSenseToolkit/band_{index}_min",
                min_value,
            )

            layer.setCustomProperty(
                f"RemoteSenseToolkit/band_{index}_max",
                max_value,
            )

        try:
            from qgis.core import (
                QgsContrastEnhancement,
                QgsMultiBandColorRenderer,
                QgsSingleBandGrayRenderer,
            )

            if len(entries) >= 3:
                red_band = 3
                green_band = 2
                blue_band = 1

                renderer = QgsMultiBandColorRenderer(
                    layer.dataProvider(),
                    red_band,
                    green_band,
                    blue_band,
                )

                def make_enhancement(band_index):
                    enhancement = QgsContrastEnhancement(
                        layer.dataProvider().dataType(
                            band_index
                        )
                    )

                    enhancement.setMinimumValue(
                        float(
                            mins[band_index - 1]
                        ),
                        False,
                    )

                    enhancement.setMaximumValue(
                        float(
                            maxs[band_index - 1]
                        ),
                        False,
                    )

                    enhancement.setContrastEnhancementAlgorithm(
                        QgsContrastEnhancement.StretchToMinimumMaximum,
                        True,
                    )

                    return enhancement

                renderer.setRedContrastEnhancement(
                    make_enhancement(red_band)
                )

                renderer.setGreenContrastEnhancement(
                    make_enhancement(green_band)
                )

                renderer.setBlueContrastEnhancement(
                    make_enhancement(blue_band)
                )

                for band_index, setter in (
                    (
                        red_band,
                        renderer.setRedContrastEnhancement,
                    ),
                    (
                        green_band,
                        renderer.setGreenContrastEnhancement,
                    ),
                    (
                        blue_band,
                        renderer.setBlueContrastEnhancement,
                    ),
                ):
                    enhancement = QgsContrastEnhancement(
                        layer.dataProvider().dataType(
                            band_index
                        )
                    )

                    enhancement.setMinimumValue(
                        float(
                            mins[band_index - 1]
                        ),
                        False,
                    )

                    enhancement.setMaximumValue(
                        float(
                            maxs[band_index - 1]
                        ),
                        False,
                    )

                    enhancement.setContrastEnhancementAlgorithm(
                        QgsContrastEnhancement.StretchToMinimumMaximum,
                        True,
                    )

                    setter(enhancement)

                layer.setRenderer(renderer)

                layer.setCustomProperty(
                    "RemoteSenseToolkit/renderer",
                    "Multiband Color",
                )

                layer.setCustomProperty(
                    "RemoteSenseToolkit/red_band",
                    red_band,
                )

                layer.setCustomProperty(
                    "RemoteSenseToolkit/green_band",
                    green_band,
                )

                layer.setCustomProperty(
                    "RemoteSenseToolkit/blue_band",
                    blue_band,
                )

                layer.triggerRepaint()

                feedback.pushInfo(
                    "QGIS renderer configured: Multiband Color "
                    f"(R=Band {red_band}, "
                    f"G=Band {green_band}, "
                    f"B=Band {blue_band})."
                )

            else:
                renderer = QgsSingleBandGrayRenderer(
                    layer.dataProvider(),
                    1,
                )

                enhancement = QgsContrastEnhancement(
                    layer.dataProvider().dataType(1)
                )

                enhancement.setMinimumValue(
                    float(mins[0]),
                    False,
                )

                enhancement.setMaximumValue(
                    float(maxs[0]),
                    False,
                )

                enhancement.setContrastEnhancementAlgorithm(
                    QgsContrastEnhancement.StretchToMinimumMaximum,
                    True,
                )

                renderer.setContrastEnhancement(
                    enhancement
                )

                layer.setRenderer(renderer)

                layer.setCustomProperty(
                    "RemoteSenseToolkit/renderer",
                    "Singleband Gray",
                )

                layer.triggerRepaint()

        except Exception as exc:
            feedback.reportError(
                "Automatic QGIS renderer configuration failed: "
                f"{exc}"
            )

        return layer

    def processAlgorithm(
        self,
        parameters,
        context,
        feedback,
    ):
        """Create the requested multiband raster outputs."""

        input_layers = self.parameterAsLayerList(
            parameters,
            self.INPUT_RASTERS,
            context,
        )

        sensor = self.SENSOR_OPTIONS[
            self.parameterAsEnum(
                parameters,
                self.SATELLITE,
                context,
            )
        ]

        band_set_name = self.parameterAsString(
            parameters,
            self.BAND_SET_NAME,
            context,
        ).strip()

        output_format = self.parameterAsEnum(
            parameters,
            self.OUTPUT_FORMAT,
            context,
        )

        output_folder = self.parameterAsString(
            parameters,
            self.OUTPUT_FOLDER,
            context,
        )

        group_name = (
            self.parameterAsString(
                parameters,
                self.GROUP_NAME,
                context,
            ).strip()
            or "Band Sets"
        )

        load_outputs = self.parameterAsBool(
            parameters,
            self.LOAD_OUTPUTS,
            context,
        )

        if not band_set_name:
            raise QgsProcessingException(
                self.tr("Band Set name cannot be empty.")
            )

        if not input_layers:
            raise QgsProcessingException(
                self.tr("Select at least one raster layer.")
            )

        rasters = []

        for layer in input_layers:
            if (
                not isinstance(layer, QgsRasterLayer)
                or not layer.isValid()
            ):
                raise QgsProcessingException(
                    self.tr(
                        f"Invalid raster layer: "
                        f"{layer.name()}"
                    )
                )

            rasters.append(layer)

        reference = self.validate_rasters(
            rasters,
            feedback,
        )

        entries = self._collect_output_bands(
            rasters,
            sensor,
            feedback,
        )

        if not entries:
            raise QgsProcessingException(
                self.tr("No raster bands were found.")
            )

        band_count = len(entries)

        mins = self._parse_values(
            self.parameterAsString(
                parameters,
                self.BAND_MIN_VALUES,
                context,
            ),
            band_count,
            "Band minimum values",
            default=0,
        )

        maxs = self._parse_values(
            self.parameterAsString(
                parameters,
                self.BAND_MAX_VALUES,
                context,
            ),
            band_count,
            "Band maximum values",
            required=True,
        )

        for entry, min_value, max_value in zip(
            entries,
            mins,
            maxs,
        ):
            if max_value <= min_value:
                raise QgsProcessingException(
                    self.tr(
                        f"{entry['display_name']}: maximum "
                        f"({max_value}) must be greater than "
                        f"minimum ({min_value})."
                    )
                )

        if (
            not output_folder
            or output_folder == "TEMPORARY_OUTPUT"
        ):
            output_path = Path(
                tempfile.mkdtemp(
                    prefix="RemoteSenseToolkit_"
                )
            )
            temporary_output_folder = True
        else:
            output_path = Path(output_folder)
            output_path.mkdir(
                parents=True,
                exist_ok=True,
            )
            temporary_output_folder = False

        safe_name = self._safe_name(
            band_set_name
        )

        output_vrt = (
            output_path / f"{safe_name}.vrt"
        )

        output_tif = (
            output_path / f"{safe_name}.tif"
        )

        output_json = (
            output_path
            / f"{safe_name}_band_set.json"
        )

        source_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{safe_name}_sources_",
                dir=str(output_path),
            )
        )

        created = []

        try:
            source_vrts = []

            for entry in entries:
                source_vrt = (
                    source_dir
                    / f"band_{entry['order']:03d}.vrt"
                )

                self._make_single_band_vrt(
                    entry["source"],
                    entry["source_band"],
                    source_vrt,
                )

                source_vrts.append(
                    source_vrt
                )

            if output_format in (0, 2):
                feedback.pushInfo(
                    f"Building VRT from "
                    f"{len(source_vrts)} "
                    "single-band sources..."
                )

                self._build_bandset_vrt(
                    output_vrt,
                    entries,
                    feedback,
                )

                self._set_band_descriptions(
                    output_vrt,
                    [
                        entry["display_name"]
                        for entry in entries
                    ],
                    feedback,
                )

                self._set_band_metadata(
                    output_vrt,
                    entries,
                    mins,
                    maxs,
                    feedback,
                )

                created.append(
                    output_vrt
                )

            if output_format in (1, 2):
                from osgeo import gdal

                vrt_source = (
                    output_vrt
                    if output_vrt.exists()
                    else (
                        source_dir
                        / f"{safe_name}_temporary.vrt"
                    )
                )

                if not output_vrt.exists():
                    self._build_bandset_vrt(
                        vrt_source,
                        entries,
                        feedback,
                    )

                translated = gdal.Translate(
                    str(output_tif),
                    str(vrt_source),
                    format="GTiff",
                )

                if (
                    translated is None
                    or not output_tif.exists()
                ):
                    error = gdal.GetLastErrorMsg()

                    raise QgsProcessingException(
                        f"GeoTIFF creation failed. "
                        f"GDAL: {error}"
                    )

                translated = None

                self._set_band_descriptions(
                    output_tif,
                    [
                        entry["display_name"]
                        for entry in entries
                    ],
                    feedback,
                )

                self._set_band_metadata(
                    output_tif,
                    entries,
                    mins,
                    maxs,
                    feedback,
                )

                created.append(
                    output_tif
                )

            definition = {
                "version": "0.4.6",
                "band_set_name": band_set_name,
                "satellite_dataset": sensor,
                "input_rasters": len(rasters),
                "output_band_count": band_count,
                "output_format": [
                    "VRT",
                    "GeoTIFF",
                    "Both",
                ][output_format],
                "crs": reference["crs"],
                "width": reference["width"],
                "height": reference["height"],
                "resolution": {
                    "x": reference["xres"],
                    "y": reference["yres"],
                },
                "bands": [],
            }

            for entry, min_value, max_value in zip(
                entries,
                mins,
                maxs,
            ):
                definition["bands"].append(
                    {
                        **entry,
                        "min": min_value,
                        "max": max_value,
                    }
                )

            with open(
                output_json,
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    definition,
                    file,
                    indent=4,
                    ensure_ascii=False,
                )

            loaded = 0

            if load_outputs:
                root = (
                    QgsProject.instance()
                    .layerTreeRoot()
                )

                group = root.findGroup(
                    group_name
                )

                if group is None:
                    group = root.addGroup(
                        group_name
                    )

                for output in created:
                    if self._load_output(
                        output,
                        group,
                        sensor,
                        entries,
                        mins,
                        maxs,
                        feedback,
                    ):
                        loaded += 1

            report_lines = [
                "REMOTE SENSE TOOLKIT — BAND SET REPORT",
                "=======================================",
                f"Band Set name: {band_set_name}",
                f"Satellite / dataset: {sensor}",
                f"Input rasters: {len(rasters)}",
                f"Output bands: {band_count}",
                f"Output format: "
                f"{['VRT', 'GeoTIFF', 'Both'][output_format]}",
                f"QGIS group: {group_name}",
                f"CRS: {reference['crs']}",
                f"Size: "
                f"{reference['width']} × "
                f"{reference['height']} pixels",
                f"Resolution: "
                f"{reference['xres']:.6f} × "
                f"{reference['yres']:.6f}",
                "",
                "BAND ORDER AND DISPLAY RANGE",
                "---------------------------------------",
            ]

            for entry, min_value, max_value in zip(
                entries,
                mins,
                maxs,
            ):
                report_lines.append(
                    f"{entry['order']}. "
                    f"{entry['display_name']} <- "
                    f"{entry['source_layer']} "
                    f"(source band "
                    f"{entry['source_band']}) | "
                    f"Min={min_value:g}, "
                    f"Max={max_value:g}"
                )

            report_lines.extend(
                [
                    "",
                    "OUTPUTS",
                    "---------------------------------------",
                    *[
                        str(path)
                        for path in created
                    ],
                    "",
                    f"Band Set definition: "
                    f"{output_json}",
                    f"Loaded layers: {loaded}",
                    "",
                    "=======================================",
                    "Band Set creation completed.",
                ]
            )

            report = "\n".join(
                report_lines
            )

            feedback.pushInfo(report)

            return {
                self.REPORT: report
            }

        finally:
            shutil.rmtree(
                str(source_dir),
                ignore_errors=True,
            )