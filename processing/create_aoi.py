# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : create_aoi.py
# Module     : Module 02 — AOI / Study Area
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Creates a reusable polygon Area of Interest (AOI) from either the
#     current QGIS map extent or an existing polygon layer.
#
#     The generated AOI is written to a Processing feature sink and includes
#     basic area and spatial-extent information in the processing report.
#
# AOI sources:
#     - Current map extent
#     - Existing polygon layer
#
# Output attributes:
#     - source
#     - area_m2
#     - area_km2
#
# Status     : Stable
# =============================================================================

from qgis.PyQt.QtCore import QCoreApplication, QVariant

from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)


class CreateAOIAlgorithm(QgsProcessingAlgorithm):
    """Create a reusable polygon AOI / study area."""

    INPUT_MODE = "INPUT_MODE"
    INPUT_LAYER = "INPUT_LAYER"
    INPUT_EXTENT = "INPUT_EXTENT"
    OUTPUT = "OUTPUT"
    REPORT = "REPORT"

    def tr(self, string):
        """Translate a user-interface string."""
        return QCoreApplication.translate("CreateAOIAlgorithm", string)

    def createInstance(self):
        """Create a new instance of the AOI processing algorithm."""
        return CreateAOIAlgorithm()

    def name(self):
        """Return the unique Processing algorithm identifier."""
        return "create_aoi"

    def displayName(self):
        """Return the algorithm name displayed in QGIS."""
        return self.tr("Create AOI / Study Area")

    def group(self):
        """Return the Processing Toolbox group name."""
        return self.tr("02 — AOI / Study Area")

    def groupId(self):
        """Return the unique Processing Toolbox group identifier."""
        return "02_aoi"

    def shortHelpString(self):
        """Return the algorithm help description."""
        return self.tr(
            "Creates a reusable polygon AOI from either the current map "
            "extent or an existing polygon layer."
        )

    def initAlgorithm(self, config=None):
        """Define the AOI inputs and output parameters."""

        self.addParameter(
            QgsProcessingParameterEnum(
                self.INPUT_MODE,
                self.tr("AOI source"),
                options=[
                    self.tr("Current map extent"),
                    self.tr("Existing polygon layer"),
                ],
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_LAYER,
                self.tr("Existing polygon layer"),
                [QgsProcessing.TypeVectorPolygon],
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterExtent(
                self.INPUT_EXTENT,
                self.tr("AOI extent"),
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr("AOI output"),
                QgsProcessing.TypeVectorPolygon,
                QgsWkbTypes.Polygon,
            )
        )

        self.addOutput(
            QgsProcessingOutputString(
                self.REPORT,
                self.tr("AOI report"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """Create the AOI, write the output layer, and generate a report."""

        mode = self.parameterAsInt(
            parameters,
            self.INPUT_MODE,
            context,
        )

        # Define the attributes written to every AOI feature.
        fields = QgsFields()

        fields.append(
            QgsField(
                "source",
                QVariant.String,
            )
        )

        fields.append(
            QgsField(
                "area_m2",
                QVariant.Double,
            )
        )

        fields.append(
            QgsField(
                "area_km2",
                QVariant.Double,
            )
        )

        source_crs = None
        geometries = []

        # ---------------------------------------------------------------------
        # MODE 1 — CURRENT MAP EXTENT
        # ---------------------------------------------------------------------

        if mode == 0:
            extent = self.parameterAsExtent(
                parameters,
                self.INPUT_EXTENT,
                context,
            )

            if extent.isNull() or not extent.isFinite():
                raise QgsProcessingException(
                    self.tr("A valid map extent is required.")
                )

            # The map extent is interpreted in the current project CRS.
            source_crs = QgsProject.instance().crs()

            # If the project CRS is invalid, attempt to obtain a valid CRS
            # from an existing project layer.
            if not source_crs.isValid():
                project = QgsProject.instance()

                for layer in project.mapLayers().values():
                    if isinstance(layer, QgsVectorLayer):
                        if layer.crs().isValid():
                            source_crs = layer.crs()
                            break

                    elif hasattr(layer, "crs"):
                        if layer.crs().isValid():
                            source_crs = layer.crs()
                            break

            if not source_crs.isValid():
                raise QgsProcessingException(
                    self.tr(
                        "No valid CRS could be determined. "
                        "Set the QGIS project CRS or load a "
                        "georeferenced raster first."
                    )
                )

            geometry = QgsGeometry.fromRect(extent)

            if geometry.isEmpty():
                raise QgsProcessingException(
                    self.tr("The generated AOI geometry is empty.")
                )

            geometries.append(geometry)
            source_name = "Current map extent"

        # ---------------------------------------------------------------------
        # MODE 2 — EXISTING POLYGON LAYER
        # ---------------------------------------------------------------------

        else:
            source_layer = self.parameterAsSource(
                parameters,
                self.INPUT_LAYER,
                context,
            )

            if source_layer is None:
                raise QgsProcessingException(
                    self.tr(
                        "Please select an existing polygon layer."
                    )
                )

            source_crs = source_layer.sourceCrs()

            if not source_crs.isValid():
                raise QgsProcessingException(
                    self.tr(
                        "The selected polygon layer does not have a valid CRS."
                    )
                )

            for feature in source_layer.getFeatures():
                if feedback.isCanceled():
                    break

                geometry = feature.geometry()

                if geometry.isNull() or geometry.isEmpty():
                    continue

                if not geometry.isGeosValid():
                    feedback.pushWarning(
                        self.tr(
                            "An invalid geometry was skipped."
                        )
                    )
                    continue

                geometries.append(
                    QgsGeometry(geometry)
                )

            if not geometries:
                raise QgsProcessingException(
                    self.tr(
                        "No valid polygon geometries were found."
                    )
                )

            source_name = "Existing polygon layer"

        # ---------------------------------------------------------------------
        # OUTPUT
        # ---------------------------------------------------------------------

        sink, destination_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.Polygon,
            source_crs,
        )

        if sink is None:
            raise QgsProcessingException(
                self.tr(
                    "Could not create the AOI output layer."
                )
            )

        # ---------------------------------------------------------------------
        # CREATE FEATURES
        # ---------------------------------------------------------------------

        total_area = 0.0

        for geometry in geometries:
            if feedback.isCanceled():
                break

            if geometry.isNull() or geometry.isEmpty():
                continue

            area = geometry.area()

            if area <= 0:
                continue

            feature = QgsFeature(fields)
            feature.setGeometry(geometry)

            feature.setAttribute(
                "source",
                source_name,
            )

            feature.setAttribute(
                "area_m2",
                area,
            )

            feature.setAttribute(
                "area_km2",
                area / 1_000_000.0,
            )

            sink.addFeature(
                feature,
                QgsFeatureSink.FastInsert,
            )

            total_area += area

        if total_area <= 0:
            raise QgsProcessingException(
                self.tr("The AOI has zero area.")
            )

        # ---------------------------------------------------------------------
        # REPORT
        # ---------------------------------------------------------------------

        extent = geometries[0].boundingBox()

        for geometry in geometries[1:]:
            extent.combineExtentWith(
                geometry.boundingBox()
            )

        report = (
            "REMOTE SENSE TOOLKIT — AOI REPORT\n"
            "====================================\n"
            f"Source: {source_name}\n"
            f"CRS: {source_crs.authid()}\n"
            f"Features: {len(geometries)}\n"
            f"Total area: {total_area:.3f} m²\n"
            f"Total area: {total_area / 1_000_000.0:.6f} km²\n"
            f"Extent width: {extent.width():.3f} map units\n"
            f"Extent height: {extent.height():.3f} map units\n"
            f"Extent xmin: {extent.xMinimum():.3f}\n"
            f"Extent ymin: {extent.yMinimum():.3f}\n"
            f"Extent xmax: {extent.xMaximum():.3f}\n"
            f"Extent ymax: {extent.yMaximum():.3f}\n"
            "===================================="
        )

        feedback.pushInfo(report)

        return {
            self.OUTPUT: destination_id,
            self.REPORT: report,
        }