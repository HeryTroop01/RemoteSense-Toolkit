# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : remote_sense_toolkit_dialog.py
# Module     : Main Plugin Dialog and AOI Creation Interface
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Provides the main RemoteSense Toolkit dialog and the interactive AOI
#     creation workflow.
#
#     Includes:
#         - Environment information and validation
#         - Interactive rectangle AOI creation
#         - Current map extent AOI creation
#         - Existing polygon layer AOI creation
#         - AOI layer grouping and attribute generation
#
# Status     : Stable
# =============================================================================

from pathlib import Path
import sys

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)

from qgis.gui import (
    QgsMapToolEmitPoint,
    QgsRubberBand,
)


FORM_CLASS, _ = uic.loadUiType(
    str(
        Path(__file__).parent
        / "remote_sense_toolkit_dialog_base.ui"
    )
)


class AOICanvasTool(QgsMapToolEmitPoint):
    """Interactive rectangle drawing tool for AOI creation."""

    def __init__(self, canvas, finished_callback):
        super().__init__(canvas)

        self.canvas = canvas
        self.finished_callback = finished_callback
        self.start_point = None

        self.rubber_band = QgsRubberBand(
            canvas,
            QgsWkbTypes.PolygonGeometry,
        )
        self.rubber_band.setColor(
            QColor(255, 0, 0, 180)
        )
        self.rubber_band.setFillColor(
            QColor(255, 0, 0, 40)
        )
        self.rubber_band.setWidth(2)

    def canvasPressEvent(self, event):
        """Start rectangle drawing or cancel with right-click."""

        if event.button() == Qt.LeftButton:
            self.start_point = self.toMapCoordinates(
                event.pos()
            )

            self.rubber_band.reset(
                QgsWkbTypes.PolygonGeometry
            )

            self.rubber_band.addPoint(
                self.start_point,
                False,
            )
            self.rubber_band.addPoint(
                self.start_point,
                False,
            )
            self.rubber_band.addPoint(
                self.start_point,
                False,
            )
            self.rubber_band.addPoint(
                self.start_point,
                True,
            )

        elif event.button() == Qt.RightButton:
            self.cancel()

    def canvasMoveEvent(self, event):
        """Update the rubber-band rectangle while the mouse moves."""

        if self.start_point is None:
            return

        current = self.toMapCoordinates(
            event.pos()
        )

        xmin = min(
            self.start_point.x(),
            current.x(),
        )
        xmax = max(
            self.start_point.x(),
            current.x(),
        )
        ymin = min(
            self.start_point.y(),
            current.y(),
        )
        ymax = max(
            self.start_point.y(),
            current.y(),
        )

        from qgis.core import QgsPointXY

        rect_points = [
            QgsPointXY(xmin, ymin),
            QgsPointXY(xmin, ymax),
            QgsPointXY(xmax, ymax),
            QgsPointXY(xmax, ymin),
            QgsPointXY(xmin, ymin),
        ]

        self.rubber_band.reset(
            QgsWkbTypes.PolygonGeometry
        )

        for point in rect_points:
            self.rubber_band.addPoint(
                point,
                False,
            )

        self.rubber_band.closePoints()

    def canvasReleaseEvent(self, event):
        """Finish rectangle drawing when the left mouse button is released."""

        if (
            event.button() != Qt.LeftButton
            or self.start_point is None
        ):
            return

        end_point = self.toMapCoordinates(
            event.pos()
        )

        xmin = min(
            self.start_point.x(),
            end_point.x(),
        )
        xmax = max(
            self.start_point.x(),
            end_point.x(),
        )
        ymin = min(
            self.start_point.y(),
            end_point.y(),
        )
        ymax = max(
            self.start_point.y(),
            end_point.y(),
        )

        if xmax <= xmin or ymax <= ymin:
            self.cancel()
            return

        from qgis.core import QgsRectangle

        extent = QgsRectangle(
            xmin,
            ymin,
            xmax,
            ymax,
        )

        self.rubber_band.reset(
            QgsWkbTypes.PolygonGeometry
        )

        self.finished_callback(extent)
        self.start_point = None

    def cancel(self):
        """Cancel the current AOI drawing operation."""

        self.start_point = None

        self.rubber_band.reset(
            QgsWkbTypes.PolygonGeometry
        )

        self.canvas.unsetMapTool(self)


class AOICreationDialog(QDialog):
    """
    Custom AOI creation workflow.

    Supports drawing an AOI directly on the QGIS map canvas, using the
    current map extent, or copying geometry from an existing polygon layer.
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent)

        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.map_tool = None

        self.setWindowTitle(
            "Create AOI / Study Area"
        )
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)

        # ---------------------------------------------------------------------
        # TITLE
        # ---------------------------------------------------------------------

        title = QLabel(
            "Create AOI / Study Area"
        )
        title.setStyleSheet(
            "font-size: 15pt; font-weight: bold;"
        )
        layout.addWidget(title)

        layout.addWidget(
            QLabel(
                "Choose how to create the study area. "
                "The Draw on Map option uses a dedicated canvas tool."
            )
        )

        # ---------------------------------------------------------------------
        # AOI SOURCE
        # ---------------------------------------------------------------------

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [
                "Draw rectangle on map",
                "Use current map extent",
                "Use existing polygon layer",
            ]
        )

        layout.addWidget(
            QLabel("AOI source:")
        )
        layout.addWidget(
            self.mode_combo
        )

        # ---------------------------------------------------------------------
        # AOI NAME
        # ---------------------------------------------------------------------

        layout.addWidget(
            QLabel("AOI name:")
        )

        self.name_edit = QLineEdit(
            "Study_Area"
        )
        layout.addWidget(
            self.name_edit
        )

        # ---------------------------------------------------------------------
        # QGIS GROUP
        # ---------------------------------------------------------------------

        layout.addWidget(
            QLabel("QGIS layer group:")
        )

        self.group_edit = QLineEdit(
            "AOI"
        )
        layout.addWidget(
            self.group_edit
        )

        # ---------------------------------------------------------------------
        # STATUS
        # ---------------------------------------------------------------------

        self.status_label = QLabel(
            "Ready."
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(
            self.status_label
        )

        # ---------------------------------------------------------------------
        # DRAW BUTTON
        # ---------------------------------------------------------------------

        self.draw_button = QPushButton(
            "Draw AOI on Map"
        )
        self.draw_button.clicked.connect(
            self.start_drawing
        )
        layout.addWidget(
            self.draw_button
        )

        # ---------------------------------------------------------------------
        # DIALOG BUTTONS
        # ---------------------------------------------------------------------

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            self.create_aoi
        )
        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )

        self.selected_extent = None
        self.existing_layer = None

    def start_drawing(self):
        """Activate the map canvas AOI drawing tool."""

        self.status_label.setText(
            "Draw mode active: click and drag a rectangle on the QGIS map. "
            "Right-click cancels drawing."
        )

        self.hide()

        self.map_tool = AOICanvasTool(
            self.canvas,
            self.drawing_finished,
        )

        self.canvas.setMapTool(
            self.map_tool
        )

    def drawing_finished(self, extent):
        """Receive the completed AOI extent from the canvas tool."""

        self.selected_extent = extent

        self.canvas.unsetMapTool(
            self.map_tool
        )
        self.map_tool = None

        self.status_label.setText(
            f"AOI selected: "
            f"{extent.width():.2f} × "
            f"{extent.height():.2f} map units."
        )

        self.show()
        self.raise_()
        self.activateWindow()

    def create_aoi(self):
        """Create the requested AOI layer and add it to the QGIS project."""

        name = (
            self.name_edit.text().strip()
            or "Study_Area"
        )

        group_name = (
            self.group_edit.text().strip()
            or "AOI"
        )

        mode = self.mode_combo.currentText()

        # ---------------------------------------------------------------------
        # DRAWN RECTANGLE
        # ---------------------------------------------------------------------

        if mode == "Draw rectangle on map":
            if self.selected_extent is None:
                QMessageBox.warning(
                    self,
                    "AOI not selected",
                    "Click 'Draw AOI on Map' and draw a rectangle first.",
                )
                return

            extent = self.selected_extent

        # ---------------------------------------------------------------------
        # CURRENT MAP EXTENT
        # ---------------------------------------------------------------------

        elif mode == "Use current map extent":
            extent = self.canvas.extent()

        # ---------------------------------------------------------------------
        # EXISTING POLYGON LAYER
        # ---------------------------------------------------------------------

        else:
            layers = [
                layer
                for layer in self.canvas.layers()
                if isinstance(layer, QgsVectorLayer)
                and QgsWkbTypes.geometryType(
                    layer.wkbType()
                )
                == QgsWkbTypes.PolygonGeometry
            ]

            if not layers:
                QMessageBox.warning(
                    self,
                    "No polygon layer",
                    "No polygon vector layer is currently loaded.",
                )
                return

            layer_names = [
                layer.name()
                for layer in layers
            ]

            selected, ok = self._choose_layer(
                layer_names
            )

            if not ok:
                return

            self.existing_layer = layers[selected]

        # ---------------------------------------------------------------------
        # DETERMINE GEOMETRY AND CRS
        # ---------------------------------------------------------------------

        if mode != "Use existing polygon layer":
            geometry = QgsGeometry.fromRect(
                extent
            )
            crs = (
                self.canvas
                .mapSettings()
                .destinationCrs()
            )
        else:
            source = self.existing_layer
            crs = source.crs()
            geometry = None

        # ---------------------------------------------------------------------
        # CREATE MEMORY LAYER
        # ---------------------------------------------------------------------

        output = QgsVectorLayer(
            f"Polygon?crs={crs.authid()}",
            name,
            "memory",
        )

        provider = output.dataProvider()

        provider.addAttributes(
            [
                QgsField(
                    "source",
                    10,
                ),
                QgsField(
                    "area_m2",
                    6,
                    "double",
                ),
                QgsField(
                    "area_km2",
                    6,
                    "double",
                ),
            ]
        )

        output.updateFields()

        # ---------------------------------------------------------------------
        # COPY EXISTING POLYGON GEOMETRIES
        # ---------------------------------------------------------------------

        if mode == "Use existing polygon layer":
            for feature in self.existing_layer.getFeatures():
                if (
                    feature.hasGeometry()
                    and not feature.geometry().isEmpty()
                ):
                    geom = feature.geometry()
                    area_m2 = geom.area()

                    new_feature = QgsFeature(
                        output.fields()
                    )

                    new_feature.setGeometry(
                        geom
                    )
                    new_feature["source"] = (
                        "existing polygon"
                    )
                    new_feature["area_m2"] = (
                        area_m2
                    )
                    new_feature["area_km2"] = (
                        area_m2 / 1_000_000.0
                    )

                    provider.addFeature(
                        new_feature
                    )

        # ---------------------------------------------------------------------
        # CREATE SINGLE AOI GEOMETRY
        # ---------------------------------------------------------------------

        else:
            area_m2 = geometry.area()

            feature = QgsFeature(
                output.fields()
            )

            feature.setGeometry(
                geometry
            )
            feature["source"] = mode
            feature["area_m2"] = area_m2
            feature["area_km2"] = (
                area_m2 / 1_000_000.0
            )

            provider.addFeature(
                feature
            )

        output.updateExtents()

        # ---------------------------------------------------------------------
        # ADD OUTPUT TO AOI GROUP
        # ---------------------------------------------------------------------

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

        QgsProject.instance().addMapLayer(
            output,
            False,
        )

        group.addLayer(
            output
        )

        # ---------------------------------------------------------------------
        # VALIDATE OUTPUT
        # ---------------------------------------------------------------------

        if output.featureCount() == 0:
            QMessageBox.warning(
                self,
                "AOI creation failed",
                "No valid polygon geometry was produced.",
            )

            QgsProject.instance().removeMapLayer(
                output.id()
            )
            return

        area = sum(
            feature["area_m2"] or 0
            for feature in output.getFeatures()
        )

        # ---------------------------------------------------------------------
        # UPDATE MAP CANVAS
        # ---------------------------------------------------------------------

        self.iface.mapCanvas().setExtent(
            output.extent()
        )
        self.iface.mapCanvas().refresh()

        # ---------------------------------------------------------------------
        # SUCCESS MESSAGE
        # ---------------------------------------------------------------------

        QMessageBox.information(
            self,
            "AOI created",
            f"AOI: {name}\n"
            f"Group: {group_name}\n"
            f"CRS: {crs.authid()}\n"
            f"Features: {output.featureCount()}\n"
            f"Area: {area:,.2f} m²\n"
            f"Area: {area / 1_000_000.0:,.6f} km²",
        )

        self.accept()

    def _choose_layer(self, names):
        """Show the polygon-layer selection dialog."""

        from qgis.PyQt.QtWidgets import QInputDialog

        if not names:
            return None, False

        return QInputDialog.getItem(
            self,
            "Select Polygon Layer",
            "Polygon layer:",
            names,
            0,
            False,
        )

    def reject(self):
        """Clean up the active map tool before closing the dialog."""

        if self.map_tool is not None:
            self.canvas.unsetMapTool(
                self.map_tool
            )
            self.map_tool = None

        super().reject()


class RemoteSenseToolkitDialog(
    QDialog,
    FORM_CLASS,
):
    """Main RemoteSense Toolkit plugin dialog."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)

        self.iface = iface
        self.setupUi(self)

        # ---------------------------------------------------------------------
        # UI SIGNALS
        # ---------------------------------------------------------------------

        self.btnCheck.clicked.connect(
            self.check_environment
        )

        self.btnClose.clicked.connect(
            self.reject
        )

        self.btnCreateAOI.clicked.connect(
            self.open_create_aoi
        )

        # ---------------------------------------------------------------------
        # ENVIRONMENT INFORMATION
        # ---------------------------------------------------------------------

        self.lblQgisVersion.setText(
            Qgis.QGIS_VERSION
        )

        self.lblPythonVersion.setText(
            sys.version.split()[0]
        )

    def open_create_aoi(self):
        """Open the custom AOI creation dialog."""

        dialog = AOICreationDialog(
            self.iface,
            self,
        )

        dialog.exec_()

    def check_environment(self):
        """Check the current QGIS environment and loaded layer counts."""

        layers = (
            self.iface
            .mapCanvas()
            .layers()
        )

        raster_count = sum(
            1
            for layer in layers
            if layer.type()
            == layer.RasterLayer
        )

        vector_count = sum(
            1
            for layer in layers
            if layer.type()
            == layer.VectorLayer
        )

        message = (
            "RemoteSense Toolkit is installed correctly.\n\n"
            f"QGIS version: {Qgis.QGIS_VERSION}\n"
            f"Python: {sys.version.split()[0]}\n"
            f"Raster layers loaded: {raster_count}\n"
            f"Vector layers loaded: {vector_count}"
        )

        self.lblStatus.setText(
            "Environment check completed successfully."
        )

        QMessageBox.information(
            self,
            "RemoteSense Toolkit",
            message,
        )