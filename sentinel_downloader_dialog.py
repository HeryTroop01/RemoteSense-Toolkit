# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : sentinel_downloader_dialog.py
# Module     : Module 07 — Satellite Data Explorer & Downloader
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Provides the interactive QGIS interface for searching, inspecting,
#     previewing, authenticating, downloading, and optionally loading
#     satellite-data assets from the Copernicus Data Space Ecosystem (CDSE).
#
# Supported missions:
#     - Sentinel-2
#     - Sentinel-1 GRD
#
# Data source:
#     - Copernicus Data Space Ecosystem (CDSE)
#
# Security:
#     - CDSE credentials may be stored through Windows Credential Manager.
#     - OAuth access tokens remain memory-only and are never persisted.
#
# Status     : Stable
# =============================================================================

import json
import os
import ctypes
from ctypes import wintypes
import requests
from urllib.parse import quote, urlparse, unquote

from qgis.PyQt.QtCore import Qt, QDate, QThread, QTimer, pyqtSignal, QByteArray
from qgis.PyQt.QtGui import QImage, QPixmap

from qgis.PyQt.QtWidgets import (
    QVBoxLayout,
    QFormLayout,
    QFileDialog,
    QGroupBox,
    QLabel,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QInputDialog,
    QLineEdit,
    QProgressBar,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
)

from qgis import gui

from qgis.core import (
    QgsProject,
    QgsMapLayerType,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsRasterLayer,
)


class WindowsCredentialLocker:
    """Small Windows Credential Manager wrapper for CDSE credentials.

    Only the CDSE email and password are stored. OAuth access tokens are
    deliberately never persisted. Windows Credential Manager protects the
    credential data using the Windows account security boundary.
    """

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    TARGET = "RemoteSenseToolkit/CDSE"

    class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
        _fields_ = [
            ("Keyword", wintypes.LPWSTR),
            ("Flags", wintypes.DWORD),
            ("ValueSize", wintypes.DWORD),
            ("Value", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows Credential Manager is available only on Windows.")

        self.advapi32 = ctypes.WinDLL("Advapi32.dll")
        self.advapi32.CredWriteW.argtypes = [
            ctypes.POINTER(self.CREDENTIALW), wintypes.DWORD
        ]
        self.advapi32.CredWriteW.restype = wintypes.BOOL
        self.advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(self.CREDENTIALW))
        ]
        self.advapi32.CredReadW.restype = wintypes.BOOL
        self.advapi32.CredDeleteW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD
        ]
        self.advapi32.CredDeleteW.restype = wintypes.BOOL
        self.advapi32.CredFree.argtypes = [ctypes.c_void_p]
        self.advapi32.CredFree.restype = None

    def save(self, username, password):
        username = str(username).strip()
        password = str(password)
        blob = password.encode("utf-8")
        blob_buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)

        credential = self.CREDENTIALW()
        credential.Flags = 0
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = self.TARGET
        credential.Comment = "RemoteSense Toolkit CDSE credentials"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(
            blob_buffer, ctypes.POINTER(ctypes.c_ubyte)
        )
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = username

        if not self.advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError()

    def load(self):
        credential_ptr = ctypes.POINTER(self.CREDENTIALW)()
        ok = self.advapi32.CredReadW(
            self.TARGET,
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential_ptr),
        )
        if not ok:
            error = ctypes.get_last_error()
            # ERROR_NOT_FOUND: no saved credential is normal.
            if error == 1168:
                return None
            raise ctypes.WinError(error)

        try:
            credential = credential_ptr.contents
            username = credential.UserName or ""
            size = int(credential.CredentialBlobSize)
            password = None
            if size and credential.CredentialBlob:
                raw = ctypes.string_at(credential.CredentialBlob, size)
                password = raw.decode("utf-8")
            return username, password
        finally:
            self.advapi32.CredFree(credential_ptr)

    def delete(self):
        ok = self.advapi32.CredDeleteW(
            self.TARGET,
            self.CRED_TYPE_GENERIC,
            0,
        )
        if not ok:
            error = ctypes.get_last_error()
            # Treat a missing entry as already cleared.
            if error == 1168:
                return
            raise ctypes.WinError(error)


class SentinelDownloadWorker(QThread):
    """Background worker for downloads. No Qt GUI operations are performed here."""

    progress = pyqtSignal(int, int, str, int, int)
    asset_finished = pyqtSignal(str, str)
    asset_failed = pyqtSignal(str, str)
    finished_all = pyqtSignal(object, object)

    def __init__(self, assets, scene_folder, token, download_url_func,
                 filename_func, parent=None):
        super().__init__(parent)
        self.assets = assets
        self.scene_folder = scene_folder
        self.token = token
        self.download_url_func = download_url_func
        self.filename_func = filename_func
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        downloaded = []
        failed = []
        headers = {"Authorization": f"Bearer {self.token}"}

        for index, (asset_id, asset) in enumerate(self.assets, start=1):
            if self._cancel_requested:
                failed.append((asset_id, "Download cancelled."))
                break

            href = asset.get("href", "")
            if not href:
                error = "Asset has no download URL."
                failed.append((asset_id, error))
                self.asset_failed.emit(asset_id, error)
                continue

            try:
                download_url = self.download_url_func(href)
                filename = self.filename_func(asset_id, href)
                destination = os.path.join(
                    self.scene_folder,
                    filename
                )

                session = requests.Session()
                session.headers.update(headers)

                response = session.get(
                    download_url,
                    stream=True,
                    timeout=(30, 300),
                    allow_redirects=False,
                )

                redirect_count = 0
                while response.status_code in (
                    301, 302, 303, 307, 308
                ):
                    location = response.headers.get("Location")
                    if not location:
                        response.raise_for_status()

                    response.close()
                    redirect_count += 1

                    if redirect_count > 10:
                        raise RuntimeError(
                            "Too many redirects while downloading asset."
                        )

                    response = session.get(
                        location,
                        stream=True,
                        timeout=(30, 300),
                        allow_redirects=False,
                    )

                response.raise_for_status()

                total = int(
                    response.headers.get("Content-Length", 0)
                )
                received = 0

                try:
                    with open(destination, "wb") as output_file:
                        for chunk in response.iter_content(
                            chunk_size=1024 * 1024
                        ):
                            if self._cancel_requested:
                                break

                            if not chunk:
                                continue

                            output_file.write(chunk)
                            received += len(chunk)

                            percent = (
                                int(received * 100 / total)
                                if total > 0 else 0
                            )

                            self.progress.emit(
                                index,
                                len(self.assets),
                                asset_id,
                                percent,
                                received,
                            )
                finally:
                    response.close()
                    session.close()

                if self._cancel_requested:
                    try:
                        os.remove(destination)
                    except OSError:
                        pass

                    error = "Download cancelled."
                    failed.append((asset_id, error))
                    self.asset_failed.emit(asset_id, error)
                    break

                downloaded.append((asset_id, destination))
                self.asset_finished.emit(
                    asset_id,
                    destination
                )

            except requests.exceptions.RequestException as exc:
                error = str(exc)
                failed.append((asset_id, error))
                self.asset_failed.emit(asset_id, error)

            except OSError as exc:
                error = str(exc)
                failed.append((asset_id, error))
                self.asset_failed.emit(asset_id, error)

            except Exception as exc:
                error = str(exc)
                failed.append((asset_id, error))
                self.asset_failed.emit(asset_id, error)

        self.finished_all.emit(downloaded, failed)


class SentinelDownloaderDialog(
    gui.QgsProcessingAlgorithmDialogBase
):
    """
    RemoteSense Toolkit
    Module 07 — Sentinel Dataset Downloader

    Current functionality:
    - Sentinel-2 search criteria
    - AOI selection
    - CDSE STAC search
    - Scene results
    - Scene selection
    - STAC asset inspection
    - Download output-folder selection UI
    - Download button UI (download implementation pending)
    """

    STAC_URL = (
        "https://stac.dataspace.copernicus.eu/v1/search"
    )

    COLLECTIONS = {
        "Sentinel-2 Level-2A": "sentinel-2-l2a",
        "Sentinel-2 Level-1C": "sentinel-2-l1c",
        "Sentinel-1 GRD": "sentinel-1-grd",
    }

    def __init__(self, algorithm, parent=None):

        super().__init__(
            parent,
            flags=Qt.WindowFlags(),
            mode=gui.QgsProcessingAlgorithmDialogBase.DialogMode.Single,
        )

        self.setAlgorithm(algorithm)
        self.setModal(True)
        self.output_folder = None
        self.download_worker = None
        self._product_uuid_cache = {}

        self.setWindowTitle(
            "RemoteSense Toolkit — Satellite Data Explorer & Downloader"
        )

        self.resize(1200, 850)

        # Search results
        self.search_results = []

        # Currently selected STAC scene
        self.selected_scene = None

        # Assets belonging to selected scene
        self.scene_assets = {}

        self.panel = gui.QgsPanelWidget()

        layout = self.build_dialog()

        # The Browse button is created inside build_dialog().
        # Connect it only after the UI has been built.
        self.browse_button.clicked.connect(
            self.select_output_folder
        )

        self.panel.setLayout(layout)

        self.setMainWidget(self.panel)

        self.cancelButton().clicked.connect(
            self.reject
        )

    # =========================================================
    # BUILD DIALOG
    # =========================================================

    def build_dialog(self):

        layout = QVBoxLayout()

        # -----------------------------------------------------
        # TITLE
        # -----------------------------------------------------

        title = QLabel(
            "Satellite Data Explorer & Downloader"
        )

        title.setStyleSheet(
            "font-size: 18pt; font-weight: bold;"
        )

        subtitle = QLabel(
            "Search and inspect Sentinel datasets from "
            "Copernicus Data Space Ecosystem (CDSE)"
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)

        # -----------------------------------------------------
        # DATA SOURCE
        # -----------------------------------------------------

        source_group = QGroupBox(
            "Data Source"
        )

        source_layout = QFormLayout()

        self.source_combo = QComboBox()

        self.source_combo.addItem(
            "Copernicus Data Space Ecosystem (CDSE)"
        )

        source_layout.addRow(
            "Data source:",
            self.source_combo
        )

        source_group.setLayout(
            source_layout
        )

        layout.addWidget(
            source_group
        )

        # -----------------------------------------------------
        # SEARCH CRITERIA
        # -----------------------------------------------------

        search_group = QGroupBox(
            "Search Criteria"
        )

        search_layout = QFormLayout()

        self.mission_combo = QComboBox()

        self.mission_combo.addItems([
            "Sentinel-2",
            "Sentinel-1",
        ])

        search_layout.addRow(
            "Mission:",
            self.mission_combo
        )

        self.mission_combo.currentIndexChanged.connect(
            self.update_mission_controls
        )

        self.product_combo = QComboBox()

        self.product_combo.addItems([
            "Sentinel-2 Level-2A",
            "Sentinel-2 Level-1C",
        ])

        search_layout.addRow(
            "Product:",
            self.product_combo
        )

        self.s1_mode_combo = QComboBox()
        self.s1_mode_combo.addItems(["Any", "IW", "SM", "EW", "WV"])
        search_layout.addRow("S-1 acquisition mode:", self.s1_mode_combo)

        self.s1_polarization_combo = QComboBox()
        self.s1_polarization_combo.addItems([
            "Any", "VV + VH", "HH + HV", "VV", "VH", "HH", "HV"
        ])
        search_layout.addRow("S-1 polarization:", self.s1_polarization_combo)

        self.s1_orbit_combo = QComboBox()
        self.s1_orbit_combo.addItems(["Any", "Ascending", "Descending"])
        search_layout.addRow("S-1 orbit direction:", self.s1_orbit_combo)

        self.start_date = QDateEdit()

        self.start_date.setCalendarPopup(
            True
        )

        self.start_date.setDate(
            QDate.currentDate().addMonths(-1)
        )

        search_layout.addRow(
            "Start date:",
            self.start_date
        )

        self.end_date = QDateEdit()

        self.end_date.setCalendarPopup(
            True
        )

        self.end_date.setDate(
            QDate.currentDate()
        )

        search_layout.addRow(
            "End date:",
            self.end_date
        )

        self.cloud_spin = QDoubleSpinBox()

        self.cloud_spin.setRange(
            0.0,
            100.0
        )

        self.cloud_spin.setDecimals(
            2
        )

        self.cloud_spin.setValue(
            20.0
        )

        self.cloud_spin.setSuffix(
            " %"
        )

        search_layout.addRow(
            "Maximum cloud cover:",
            self.cloud_spin
        )

        self.max_results = QSpinBox()

        self.max_results.setRange(
            1,
            100
        )

        self.max_results.setValue(
            20
        )

        search_layout.addRow(
            "Maximum results:",
            self.max_results
        )

        self.update_mission_controls()

        search_group.setLayout(
            search_layout
        )

        layout.addWidget(
            search_group
        )

        # -----------------------------------------------------
        # AOI
        # -----------------------------------------------------

        aoi_group = QGroupBox(
            "Area of Interest"
        )

        aoi_layout = QFormLayout()

        self.aoi_mode = QComboBox()

        self.aoi_mode.addItems([
            "Current map canvas extent",
            "Existing polygon layer",
            "No AOI",
        ])

        aoi_layout.addRow(
            "AOI mode:",
            self.aoi_mode
        )

        self.aoi_layer_combo = QComboBox()

        aoi_layout.addRow(
            "AOI layer:",
            self.aoi_layer_combo
        )

        aoi_group.setLayout(
            aoi_layout
        )

        layout.addWidget(
            aoi_group
        )

        self.populate_aoi_layers()

        self.aoi_mode.currentIndexChanged.connect(
            self.update_aoi_layer_state
        )

        self.update_aoi_layer_state()

        # -----------------------------------------------------
        # SEARCH BUTTONS
        # -----------------------------------------------------

        button_layout = QHBoxLayout()

        self.search_button = QPushButton(
            "Search Satellite Scenes"
        )

        self.clear_button = QPushButton(
            "Clear"
        )

        button_layout.addWidget(
            self.search_button
        )

        button_layout.addWidget(
            self.clear_button
        )

        layout.addLayout(
            button_layout
        )

        self.search_button.clicked.connect(
            self.search_scenes
        )

        self.clear_button.clicked.connect(
            self.clear_search
        )

        # -----------------------------------------------------
        # STATUS
        # -----------------------------------------------------

        self.status_label = QLabel(
            "Ready — configure the search criteria."
        )

        layout.addWidget(
            self.status_label
        )

        # -----------------------------------------------------
        # SEARCH RESULTS
        # -----------------------------------------------------

        results_group = QGroupBox(
            "Search Results"
        )

        results_layout = QVBoxLayout()

        self.results_table = QTableWidget()

        self.results_table.setColumnCount(
            8
        )

        self.results_table.setHorizontalHeaderLabels([
            "Select",
            "Product",
            "Date / Time",
            "Cloud %",
            "Tile",
            "Orbit",
            "Level",
            "Scene ID",
        ])

        self.results_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )

        self.results_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

        self.results_table.horizontalHeader().setSectionResizeMode(
            7,
            QHeaderView.Stretch
        )
        self.results_table.itemChanged.connect(
            self.update_inspect_button_state
        )

        results_layout.addWidget(
            self.results_table
        )

        # -----------------------------------------------------
        # INSPECT BUTTON
        # -----------------------------------------------------

        self.inspect_button = QPushButton(
            "Inspect Selected Scene Assets"
        )

        self.inspect_button.setEnabled(
            False
        )

        results_layout.addWidget(
            self.inspect_button
        )

        self.inspect_button.clicked.connect(
            self.inspect_selected_scene
        )

        self.preview_button = QPushButton(
            "Preview Selected Scene"
        )
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(
            self.preview_selected_scene
        )
        results_layout.addWidget(self.preview_button)

        results_group.setLayout(
            results_layout
        )

        layout.addWidget(
            results_group
        )

        # -----------------------------------------------------
        # SELECTED SCENE
        # -----------------------------------------------------

        scene_group = QGroupBox(
            "Selected Scene"
        )

        scene_layout = QFormLayout()

        self.selected_scene_label = QLabel(
            "No scene selected."
        )

        self.selected_scene_label.setWordWrap(
            True
        )

        scene_layout.addRow(
            "Scene:",
            self.selected_scene_label
        )

        scene_group.setLayout(
            scene_layout
        )

        layout.addWidget(
            scene_group
        )

        # -----------------------------------------------------
        # ASSET RESULTS
        # -----------------------------------------------------

        asset_group = QGroupBox(
            "Scene Assets"
        )

        asset_layout = QVBoxLayout()

        self.asset_table = QTableWidget()

        self.asset_table.setColumnCount(
            6
        )

        self.asset_table.setHorizontalHeaderLabels([
            "Select",
            "Asset ID",
            "Category",
            "Resolution",
            "Media Type",
            "Title",
        ])

        self.asset_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )

        self.asset_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.asset_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

        self.asset_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch
        )

        asset_layout.addWidget(
            self.asset_table
        )

        asset_group.setLayout(
            asset_layout
        )

                # -----------------------------------------------------
        # DOWNLOAD CONTROLS
        # -----------------------------------------------------

        download_group = QGroupBox(
            "Download"
        )

        download_layout = QFormLayout()

        self.output_folder_label = QLabel(
            "No output folder selected."
        )

        self.output_folder_label.setWordWrap(
            True
        )

        self.browse_button = QPushButton(
            "Browse..."
        )

        folder_layout = QHBoxLayout()

        folder_layout.addWidget(
            self.output_folder_label
        )

        folder_layout.addWidget(
            self.browse_button
        )

        download_layout.addRow(
            "Output folder:",
            folder_layout
        )

        self.load_into_qgis_checkbox = QCheckBox(
            "Load downloaded assets into QGIS"
        )
        self.load_into_qgis_checkbox.setChecked(False)

        download_layout.addRow(
            "",
            self.load_into_qgis_checkbox
        )

        self.download_status_label = QLabel(
            "Ready."
        )
        self.download_status_label.setWordWrap(True)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setTextVisible(True)

        self.download_detail_label = QLabel(
            "No download in progress."
        )
        self.download_detail_label.setWordWrap(True)

        download_layout.addRow(
            "Status:",
            self.download_status_label
        )

        download_layout.addRow(
            "Progress:",
            self.download_progress
        )

        download_layout.addRow(
            "Details:",
            self.download_detail_label
        )

        self.download_button = QPushButton(
            "Download Selected Assets"
        )

        self.download_button.setEnabled(
            False
        )

        self.download_button.clicked.connect(
            self.download_selected_assets
        )

        self.asset_table.itemChanged.connect(
            self.update_download_button_state
        )

        download_layout.addRow(
            "",
            self.download_button
        )

        download_group.setLayout(
            download_layout
        )

        layout.addWidget(
            download_group
        )

        layout.addWidget(
            asset_group
        )

        return layout

    # =========================================================
    # AOI LAYERS
    # =========================================================

    def populate_aoi_layers(self):

        self.aoi_layer_combo.clear()

        project = QgsProject.instance()

        for layer in project.mapLayers().values():

            if layer.type() != QgsMapLayerType.VectorLayer:
                continue

            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                continue

            self.aoi_layer_combo.addItem(
                layer.name(),
                layer.id()
            )

    # =========================================================
    # AOI STATE
    # =========================================================

    def update_aoi_layer_state(self):

        use_layer = (
            self.aoi_mode.currentText()
            == "Existing polygon layer"
        )

        self.aoi_layer_combo.setEnabled(
            use_layer
        )

    # =========================================================
    # GET AOI GEOMETRY
    # =========================================================

    def get_aoi_geometry(self):

        mode = self.aoi_mode.currentText()

        # -----------------------------------------------------
        # NO AOI
        # -----------------------------------------------------

        if mode == "No AOI":
            return None

        # -----------------------------------------------------
        # CURRENT MAP CANVAS
        # -----------------------------------------------------

        if mode == "Current map canvas extent":

            canvas = self.iface.mapCanvas()

            extent = canvas.extent()

            crs = canvas.mapSettings().destinationCrs()

            wgs84 = QgsCoordinateReferenceSystem(
                "EPSG:4326"
            )

            transform = QgsCoordinateTransform(
                crs,
                wgs84,
                QgsProject.instance()
            )

            geometry = QgsGeometry.fromRect(
                extent
            )

            geometry.transform(
                transform
            )

            return json.loads(
                geometry.asJson()
            )

        # -----------------------------------------------------
        # EXISTING POLYGON LAYER
        # -----------------------------------------------------

        layer_id = (
            self.aoi_layer_combo.currentData()
        )

        if not layer_id:
            return None

        layer = (
            QgsProject.instance()
            .mapLayer(layer_id)
        )

        if layer is None:
            return None

        if layer.type() != QgsMapLayerType.VectorLayer:
            return None

        wgs84 = QgsCoordinateReferenceSystem(
            "EPSG:4326"
        )

        transform = QgsCoordinateTransform(
            layer.crs(),
            wgs84,
            QgsProject.instance()
        )

        combined_geometry = None

        for feature in layer.getFeatures():

            geometry = feature.geometry()

            if geometry.isEmpty():
                continue

            geometry = QgsGeometry(
                geometry
            )

            geometry.transform(
                transform
            )

            if combined_geometry is None:

                combined_geometry = geometry

            else:

                combined_geometry = (
                    combined_geometry.combine(
                        geometry
                    )
                )

        if combined_geometry is None:
            return None

        return json.loads(
            combined_geometry.asJson()
        )

    # =========================================================
    # MISSION CONTROLS
    # =========================================================

    def update_mission_controls(self):
        # During dialog construction, mission controls can be updated
        # before all dependent widgets have been created.
        if not hasattr(self, "search_button"):
            return

        mission = self.mission_combo.currentText()
        is_s1 = mission == "Sentinel-1"

        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        if is_s1:
            self.product_combo.addItem("Sentinel-1 GRD")
        else:
            self.product_combo.addItems([
                "Sentinel-2 Level-2A",
                "Sentinel-2 Level-1C",
            ])
        self.product_combo.blockSignals(False)

        self.s1_mode_combo.setEnabled(is_s1)
        self.s1_polarization_combo.setEnabled(is_s1)
        self.s1_orbit_combo.setEnabled(is_s1)
        self.cloud_spin.setEnabled(not is_s1)
        self.search_button.setText(
            "Search Sentinel-1 Scenes" if is_s1 else "Search Sentinel-2 Scenes"
        )

    # =========================================================
    # SEARCH
    # =========================================================

    def search_scenes(self):

        self.results_table.setRowCount(
            0
        )

        self.asset_table.setRowCount(
            0
        )

        self.search_results = []

        self.selected_scene = None

        self.scene_assets = {}

        self.selected_scene_label.setText(
            "No scene selected."
        )

        self.inspect_button.setEnabled(
            False
        )

        # -----------------------------------------------------
        # DATE VALIDATION
        # -----------------------------------------------------

        start = self.start_date.date()

        end = self.end_date.date()

        if start > end:

            QMessageBox.warning(
                self,
                "Invalid date range",
                "Start date must be earlier than "
                "or equal to the end date."
            )

            return

        # -----------------------------------------------------
        # COLLECTION
        # -----------------------------------------------------

        mission = self.mission_combo.currentText()

        product_name = (
            self.product_combo.currentText()
        )

        collection = self.COLLECTIONS.get(
            product_name
        )

        if not collection:

            QMessageBox.warning(
                self,
                "Invalid product",
                "Unable to determine the CDSE "
                "STAC collection."
            )

            return

        # -----------------------------------------------------
        # DATETIME
        # -----------------------------------------------------

        datetime_range = (
            f"{start.toString('yyyy-MM-dd')}"
            f"T00:00:00Z/"
            f"{end.toString('yyyy-MM-dd')}"
            f"T23:59:59Z"
        )

        # -----------------------------------------------------
        # CLOUD
        # -----------------------------------------------------

        max_cloud = (
            self.cloud_spin.value()
        )

        # -----------------------------------------------------
        # MAX RESULTS
        # -----------------------------------------------------

        max_results = (
            self.max_results.value()
        )

        # -----------------------------------------------------
        # AOI
        # -----------------------------------------------------

        try:

            aoi_geometry = (
                self.get_aoi_geometry()
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "AOI error",
                f"Could not prepare the AOI:\n\n{exc}"
            )

            return

        # -----------------------------------------------------
        # STAC PAYLOAD
        # -----------------------------------------------------

        payload = {
            "collections": [collection],
            "datetime": datetime_range,
            "limit": max_results,
        }

        if mission == "Sentinel-1":
            # The selected STAC collection is already sentinel-1-grd,
            # so no additional product:type filter is required.
            query = {}
            mode = self.s1_mode_combo.currentText()
            if mode != "Any":
                query["sar:instrument_mode"] = {"eq": mode}

            polarization = self.s1_polarization_combo.currentText()
            if polarization != "Any":
                query["sar:polarizations"] = {
                    "eq": polarization.split(" + ")
                }

            orbit = self.s1_orbit_combo.currentText()
            if orbit != "Any":
                query["sat:orbit_state"] = {"eq": orbit.lower()}
            payload["query"] = query
        else:
            payload["query"] = {
                "eo:cloud_cover": {"lte": max_cloud}
            }

        if aoi_geometry is not None:

            payload["intersects"] = (
                aoi_geometry
            )

        # -----------------------------------------------------
        # SEARCH
        # -----------------------------------------------------

        self.status_label.setText(
            "Searching CDSE STAC..."
        )

        self.search_button.setEnabled(
            False
        )

        try:

            response = requests.post(
                self.STAC_URL,
                json=payload,
                timeout=60
            )

            response.raise_for_status()

            data = response.json()

            features = data.get(
                "features",
                []
            )

            self.search_results = features

            self.populate_results(
                features
            )

            count = len(features)

            self.status_label.setText(
                f"{count} {mission} scene(s) found."
            )

        except requests.exceptions.Timeout:

            QMessageBox.critical(
                self,
                "CDSE search timeout",
                "The CDSE STAC server did not "
                "respond within 60 seconds."
            )

            self.status_label.setText(
                "Search timed out."
            )

        except requests.exceptions.RequestException as exc:

            QMessageBox.critical(
                self,
                "CDSE search error",
                f"Could not query CDSE STAC:\n\n{exc}"
            )

            self.status_label.setText(
                "CDSE search failed."
            )

        except ValueError as exc:

            QMessageBox.critical(
                self,
                "Invalid response",
                f"CDSE returned invalid JSON:\n\n{exc}"
            )

            self.status_label.setText(
                "Invalid CDSE response."
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "Unexpected error",
                f"Unexpected error during search:\n\n{exc}"
            )

            self.status_label.setText(
                "Unexpected search error."
            )

        finally:

            self.search_button.setEnabled(
                True
            )

    # =========================================================
    # POPULATE SEARCH RESULTS
    # =========================================================

    def populate_results(
        self,
        features
    ):

        self.results_table.setRowCount(
            len(features)
        )

        for row, feature in enumerate(
            features
        ):

            properties = feature.get(
                "properties",
                {}
            )

            scene_id = feature.get(
                "id",
                ""
            )

            datetime_value = properties.get(
                "datetime",
                ""
            )

            if not datetime_value:
                datetime_value = feature.get(
                    "datetime",
                    ""
                )

            cloud = properties.get(
                "eo:cloud_cover"
            )

            if cloud is None:
                cloud_text = "—"
            else:
                cloud_text = (
                    f"{float(cloud):.2f}"
                )

            tile = self.extract_tile(
                scene_id,
                properties
            )

            orbit = self.extract_orbit(
                scene_id,
                properties
            )

            level = properties.get(
                "processing:level",
                ""
            )

            if not level:

                level = (
                    "L2A"
                    if "L2A" in scene_id
                    else "L1C"
                )

            # Checkbox

            check_item = QTableWidgetItem()

            check_item.setCheckState(
                Qt.Unchecked
            )

            check_item.setData(
                Qt.UserRole,
                feature
            )

            self.results_table.setItem(
                row,
                0,
                check_item
            )

            self.results_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    self.mission_combo.currentText()
                )
            )

            self.results_table.setItem(
                row,
                2,
                QTableWidgetItem(
                    str(datetime_value)
                )
            )

            self.results_table.setItem(
                row,
                3,
                QTableWidgetItem(
                    cloud_text
                )
            )

            self.results_table.setItem(
                row,
                4,
                QTableWidgetItem(
                    tile
                )
            )

            self.results_table.setItem(
                row,
                5,
                QTableWidgetItem(
                    orbit
                )
            )

            self.results_table.setItem(
                row,
                6,
                QTableWidgetItem(
                    str(level)
                )
            )

            self.results_table.setItem(
                row,
                7,
                QTableWidgetItem(
                    scene_id
                )
            )

    # =========================================================
    # EXTRACT TILE
    # =========================================================

    def extract_tile(
        self,
        scene_id,
        properties
    ):

        for key in (
            "s2:mgrs_tile",
            "mgrs:tile",
            "grid:code",
        ):

            value = properties.get(
                key
            )

            if value:
                return str(value)

        parts = scene_id.split("_")

        for part in parts:

            if (
                part.startswith("T")
                and len(part) == 6
            ):
                return part

        return ""

    # =========================================================
    # EXTRACT ORBIT
    # =========================================================

    def extract_orbit(
        self,
        scene_id,
        properties
    ):

        for key in (
            "sat:relative_orbit",
            "relative_orbit",
            "s2:relative_orbit",
        ):

            value = properties.get(
                key
            )

            if value is not None:
                return str(value)

        parts = scene_id.split("_")

        for part in parts:

            if (
                part.startswith("R")
                and len(part) == 4
            ):
                return part[1:]

        return ""

    # =========================================================
    # INSPECT SELECTED SCENE
    # =========================================================

    def update_inspect_button_state(self, item):
        """Enable inspection when a scene is checked."""

        if item.column() != 0:
            return

        checked = False

        for row in range(
            self.results_table.rowCount()
        ):
            check_item = self.results_table.item(
                row,
                0
            )

            if (
                check_item is not None
                and check_item.checkState()
                == Qt.Checked
            ):
                checked = True
                break

        self.inspect_button.setEnabled(
            checked
        )
        self.preview_button.setEnabled(
            checked
        )

    def inspect_selected_scene(self):

        selected_feature = None

        # -----------------------------------------------------
        # Find checked scene
        # -----------------------------------------------------

        for row in range(
            self.results_table.rowCount()
        ):

            item = self.results_table.item(
                row,
                0
            )

            if (
                item is not None
                and item.checkState()
                == Qt.Checked
            ):

                selected_feature = (
                    item.data(
                        Qt.UserRole
                    )
                )

                break

        if selected_feature is None:

            QMessageBox.warning(
                self,
                "No scene selected",
                "Select one scene using the "
                "checkbox in the Search Results table."
            )

            return

        # -----------------------------------------------------
        # Store selected scene
        # -----------------------------------------------------

        self.selected_scene = (
            selected_feature
        )

        scene_id = selected_feature.get(
            "id",
            ""
        )

        self.selected_scene_label.setText(
            scene_id
        )

        # -----------------------------------------------------
        # Determine item URL
        # -----------------------------------------------------

        item_links = selected_feature.get(
            "links",
            []
        )

        item_url = None

        for link in item_links:

            if link.get("rel") == "self":

                item_url = link.get(
                    "href"
                )

                break

        # -----------------------------------------------------
        # Fallback URL
        # -----------------------------------------------------

        if not item_url:

            item_url = (
                "https://stac.dataspace.copernicus.eu/v1/"
                f"collections/"
                f"{self.COLLECTIONS.get(self.product_combo.currentText())}"
                f"/items/{scene_id}"
            )

        # -----------------------------------------------------
        # Fetch complete STAC item
        # -----------------------------------------------------

        self.status_label.setText(
            "Inspecting scene assets..."
        )

        self.inspect_button.setEnabled(
            False
        )

        try:

            response = requests.get(
                item_url,
                timeout=60
            )

            response.raise_for_status()

            item_data = response.json()

            assets = item_data.get(
                "assets",
                {}
            )

            self.scene_assets = assets

            self.populate_asset_table(
                assets
            )

            self.status_label.setText(
                f"{len(assets)} asset(s) found for selected scene."
            )

        except requests.exceptions.Timeout:

            QMessageBox.critical(
                self,
                "Asset inspection timeout",
                "CDSE did not respond within 60 seconds."
            )

            self.status_label.setText(
                "Asset inspection timed out."
            )

        except requests.exceptions.RequestException as exc:

            QMessageBox.critical(
                self,
                "Asset inspection error",
                f"Could not retrieve scene assets:\n\n{exc}"
            )

            self.status_label.setText(
                "Asset inspection failed."
            )

        except ValueError as exc:

            QMessageBox.critical(
                self,
                "Invalid STAC response",
                f"CDSE returned invalid JSON:\n\n{exc}"
            )

            self.status_label.setText(
                "Invalid asset response."
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "Unexpected error",
                f"Unexpected asset inspection error:\n\n{exc}"
            )

            self.status_label.setText(
                "Asset inspection failed."
            )

        finally:

            self.inspect_button.setEnabled(
                True
            )

    # =========================================================
    # PREVIEW SELECTED SCENE
    # =========================================================

    def preview_selected_scene(self):
        """Display the best thumbnail/quicklook exposed by the STAC item."""
        selected_feature = None
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                selected_feature = item.data(Qt.UserRole)
                break

        if selected_feature is None:
            QMessageBox.warning(self, "No scene selected",
                "Select one scene using the checkbox in the Search Results table.")
            return

        scene_id = selected_feature.get("id", "")
        item_url = next((l.get("href") for l in selected_feature.get("links", [])
                         if l.get("rel") == "self"), None)
        if not item_url:
            collection = self.COLLECTIONS.get(self.product_combo.currentText())
            item_url = ("https://stac.dataspace.copernicus.eu/v1/"
                         f"collections/{collection}/items/{scene_id}")

        self.preview_button.setEnabled(False)
        self.status_label.setText("Preparing scene preview...")
        try:
            response = requests.get(item_url, timeout=60)
            response.raise_for_status()
            item_data = response.json()
            asset_id, asset = self.find_preview_asset(item_data.get("assets", {}))
            if asset is None:
                QMessageBox.information(self, "Preview unavailable",
                    "This dataset does not expose a usable thumbnail or quicklook "
                    "through its STAC item.")
                self.status_label.setText("No catalogue preview is available for this scene.")
                return

            href = asset.get("href", "")
            if not href:
                raise RuntimeError("The preview asset has no URL.")
            headers = {}
            token = getattr(self, "access_token", None)
            if token:
                headers["Authorization"] = f"Bearer {token}"
            image_response = requests.get(href, headers=headers, timeout=60)
            image_response.raise_for_status()
            image = QImage.fromData(QByteArray(image_response.content))
            if image.isNull():
                raise RuntimeError("The preview URL did not return a supported image.")
            self.show_preview_dialog(scene_id, item_data, asset_id, image)
            self.status_label.setText(f"Preview displayed: {asset_id}")
        except requests.exceptions.Timeout:
            QMessageBox.critical(self, "Preview timeout",
                "CDSE did not respond within 60 seconds while retrieving the preview.")
            self.status_label.setText("Preview request timed out.")
        except requests.exceptions.RequestException as exc:
            QMessageBox.critical(self, "Preview error",
                f"Could not retrieve the dataset preview:\n\n{exc}")
            self.status_label.setText("Preview retrieval failed.")
        except Exception as exc:
            QMessageBox.critical(self, "Preview error",
                f"Could not display the dataset preview:\n\n{exc}")
            self.status_label.setText("Preview failed.")
        finally:
            self.preview_button.setEnabled(True)

    def find_preview_asset(self, assets):
        """Find a preview asset without mission-specific assumptions."""
        priority_roles = ("thumbnail", "overview", "quicklook", "browse", "preview")
        for role in priority_roles:
            for asset_id, asset in assets.items():
                roles = [str(r).lower() for r in asset.get("roles", [])]
                if role in roles:
                    return asset_id, asset
        for asset_id, asset in assets.items():
            aid = asset_id.lower()
            title = str(asset.get("title", "")).lower()
            media = str(asset.get("type", "")).lower()
            href = str(asset.get("href", "")).lower()
            if ("thumbnail" in aid or "quicklook" in aid or "browse" in aid
                    or "preview" in aid or "thumbnail" in title
                    or media in ("image/jpeg", "image/png")
                    or href.endswith((".jpg", ".jpeg", ".png"))):
                return asset_id, asset
        return None, None

    def show_preview_dialog(self, scene_id, item_data, asset_id, image):
        """Show preview image and basic catalogue metadata."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Dataset Preview — {scene_id}")
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)
        title = QLabel(scene_id)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 13pt; font-weight: bold;")
        layout.addWidget(title)
        props = item_data.get("properties", {})
        instrument = props.get("instruments", "—")
        if isinstance(instrument, list):
            instrument = ", ".join(str(x) for x in instrument)
        info = QLabel(
            f"Preview asset: {asset_id}\n"
            f"Acquisition: {props.get('datetime', '—')}\n"
            f"Platform: {props.get('platform', '—')}\n"
            f"Instrument: {instrument}"
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setMinimumSize(640, 480)
        image_label.setStyleSheet("border: 1px solid palette(mid); background: palette(base);")
        pixmap = QPixmap.fromImage(image)
        image_label.setPixmap(pixmap.scaled(820, 560, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(image_label, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec_()

    # =========================================================
    # POPULATE ASSET TABLE
    # =========================================================

    def populate_asset_table(
        self,
        assets
    ):

        self.asset_table.setRowCount(
            0
        )

        # Sort asset names
        asset_items = sorted(
            assets.items(),
            key=lambda x: x[0]
        )

        self.asset_table.setRowCount(
            len(asset_items)
        )

        for row, (asset_id, asset) in enumerate(
            asset_items
        ):

            media_type = asset.get(
                "type",
                ""
            )

            title = asset.get(
                "title",
                ""
            )

            href = asset.get(
                "href",
                ""
            )

            category = self.get_asset_category(
                asset_id,
                media_type,
                href
            )

            resolution = self.get_asset_resolution(
                asset_id
            )

            # -------------------------------------------------
            # Checkbox
            # -------------------------------------------------

            check_item = QTableWidgetItem()

            # Default-select the standard 10 m bands
            if (
                self.mission_combo.currentText() == "Sentinel-1"
                and asset_id.lower() in ("vv", "vh")
            ) or (
                self.mission_combo.currentText() == "Sentinel-2"
                and asset_id in (
                    "B02_10m", "B03_10m", "B04_10m", "B08_10m"
                )
            ):

                check_item.setCheckState(
                    Qt.Checked
                )

            else:

                check_item.setCheckState(
                    Qt.Unchecked
                )

            check_item.setData(
                Qt.UserRole,
                asset_id
            )

            self.asset_table.setItem(
                row,
                0,
                check_item
            )

            # -------------------------------------------------
            # Asset ID
            # -------------------------------------------------

            self.asset_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    asset_id
                )
            )

            # -------------------------------------------------
            # Category
            # -------------------------------------------------

            self.asset_table.setItem(
                row,
                2,
                QTableWidgetItem(
                    category
                )
            )

            # -------------------------------------------------
            # Resolution
            # -------------------------------------------------

            self.asset_table.setItem(
                row,
                3,
                QTableWidgetItem(
                    resolution
                )
            )

            # -------------------------------------------------
            # Media type
            # -------------------------------------------------

            self.asset_table.setItem(
                row,
                4,
                QTableWidgetItem(
                    media_type
                )
            )

            # -------------------------------------------------
            # Title
            # -------------------------------------------------

            if not title:
                title = href

            self.asset_table.setItem(
                row,
                5,
                QTableWidgetItem(
                    title
                )
            )

    # =========================================================
    # ASSET CATEGORY
    # =========================================================

    def get_asset_category(
        self,
        asset_id,
        media_type,
        href
    ):

        asset_upper = asset_id.upper()

        if asset_id == "Product":
            return "Complete Product"

        if (
            asset_upper.startswith("B")
            and "_" in asset_id
        ):
            return "Spectral Band"

        if asset_upper.startswith(
            ("AOT", "WVP", "SCL")
        ):
            return "Auxiliary"

        if asset_upper.startswith(
            "TCI"
        ):
            return "Visualization"

        if (
            "thumbnail" in asset_upper
            or media_type == "image/jpeg"
        ):
            return "Visualization"

        if (
            "metadata" in asset_upper
            or "manifest" in asset_upper
            or "safe_manifest" in asset_upper
            or media_type in (
                "application/xml",
                "text/xml",
            )
        ):
            return "Metadata"

        return "Other"

    # =========================================================
    # ASSET RESOLUTION
    # =========================================================

    def get_asset_resolution(
        self,
        asset_id
    ):

        parts = asset_id.split("_")

        for part in parts:

            if part in (
                "10m",
                "20m",
                "60m",
            ):
                return part

        return ""
    # =========================================================
    # SELECT OUTPUT FOLDER
    # =========================================================

    def select_output_folder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select satellite-data download folder"
        )

        if not folder:
            return

        self.output_folder = folder

        self.output_folder_label.setText(
            folder
        )
        self.update_download_button_state()

    # =========================================================
    # DOWNLOAD STATE
    # =========================================================

    def update_download_button_state(self, item=None):
        """Enable download only when an output folder and asset are selected."""
        if self.download_button is None:
            return

        has_folder = bool(self.output_folder)
        has_asset = False

        for row in range(self.asset_table.rowCount()):
            check_item = self.asset_table.item(row, 0)
            if (
                check_item is not None
                and check_item.checkState() == Qt.Checked
            ):
                has_asset = True
                break

        self.download_button.setEnabled(has_folder and has_asset)

    # =========================================================
    # CDSE AUTHENTICATION
    # =========================================================

    def _get_cdse_credentials_dialog(self):
        """Show a GUI login dialog with optional secure credential storage."""
        saved = None
        try:
            saved = WindowsCredentialLocker().load()
        except Exception:
            saved = None

        dialog = QDialog(self)
        dialog.setWindowTitle("CDSE Login")
        dialog.setModal(True)

        layout = QFormLayout(dialog)

        email_edit = QLineEdit(dialog)
        password_edit = QLineEdit(dialog)
        password_edit.setEchoMode(QLineEdit.Password)

        remember_box = QCheckBox(
            "Remember credentials securely in Windows Credential Manager",
            dialog,
        )
        clear_button = QPushButton("Clear saved CDSE credentials", dialog)
        clear_button.setEnabled(saved is not None)

        if saved:
            email_edit.setText(saved[0])
            password_edit.setText(saved[1])
            remember_box.setChecked(True)

        layout.addRow("CDSE account email:", email_edit)
        layout.addRow("CDSE password:", password_edit)
        layout.addRow(remember_box)
        layout.addRow(clear_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=dialog,
        )
        layout.addRow(buttons)

        cleared = {"value": False}

        def clear_saved():
            try:
                WindowsCredentialLocker().delete()
                cleared["value"] = True
                email_edit.clear()
                password_edit.clear()
                remember_box.setChecked(False)
                clear_button.setEnabled(False)
                QMessageBox.information(
                    dialog,
                    "Credentials cleared",
                    "Saved CDSE credentials were removed from Windows Credential Manager.",
                )
            except Exception as exc:
                QMessageBox.warning(
                    dialog,
                    "Could not clear credentials",
                    f"Windows Credential Manager returned an error:\n\n{exc}",
                )

        clear_button.clicked.connect(clear_saved)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return None

        username = email_edit.text().strip()
        password = password_edit.text()
        if not username or not password:
            QMessageBox.warning(
                self,
                "CDSE Login",
                "Both the CDSE email and password are required.",
            )
            return None

        return username, password, remember_box.isChecked()

    def get_cdse_access_token(self):
        """Authenticate to CDSE; optionally store only the credentials securely."""
        credentials = self._get_cdse_credentials_dialog()
        if not credentials:
            return None

        username, password, remember = credentials

        token_url = (
            "https://identity.dataspace.copernicus.eu/"
            "auth/realms/CDSE/protocol/openid-connect/token"
        )

        payload = {
            "client_id": "cdse-public",
            "username": username,
            "password": password,
            "grant_type": "password",
        }

        try:
            response = requests.post(
                token_url,
                data=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError("CDSE did not return an access token.")

            if remember:
                try:
                    WindowsCredentialLocker().save(username, password)
                except Exception as exc:
                    QMessageBox.warning(
                        self,
                        "Credentials not saved",
                        "CDSE authentication succeeded, but the credentials "
                        f"could not be saved securely in Windows Credential Manager.\n\n{exc}",
                    )

            # Token remains memory-only and is never written to disk.
            return token

        except requests.exceptions.RequestException as exc:
            QMessageBox.critical(
                self,
                "CDSE authentication failed",
                f"Could not authenticate with CDSE:\n\n{exc}",
            )
        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                "CDSE authentication failed",
                f"CDSE login failed:\n\n{exc}",
            )

        return None

    # =========================================================
    # DOWNLOAD SELECTED ASSETS
    # =========================================================

    def download_selected_assets(self):
        """Authenticate on the GUI thread, then download in a worker thread."""
        if not self.output_folder:
            QMessageBox.warning(
                self,
                "Output folder required",
                "Select an output folder before downloading.",
            )
            return

        if not self.selected_scene:
            QMessageBox.warning(
                self,
                "No scene selected",
                "Inspect a satellite scene before downloading assets.",
            )
            return

        selected_assets = []
        for row in range(self.asset_table.rowCount()):
            check_item = self.asset_table.item(row, 0)

            if (
                check_item
                and check_item.checkState() == Qt.Checked
            ):
                asset_id = check_item.data(Qt.UserRole)
                asset = self.scene_assets.get(asset_id)

                if asset:
                    selected_assets.append(
                        (asset_id, asset)
                    )

        if not selected_assets:
            QMessageBox.warning(
                self,
                "No assets selected",
                "Select at least one asset to download.",
            )
            return

        # IMPORTANT:
        # Authentication and QInputDialog remain on QGIS's GUI thread.
        self.download_status_label.setText(
            "Waiting for CDSE login..."
        )
        self.download_detail_label.setText(
            "Enter your CDSE credentials in the login dialogs."
        )
        self.download_progress.setValue(0)

        token = self.get_cdse_access_token()

        if not token:
            self.download_status_label.setText(
                "CDSE login cancelled or failed."
            )
            self.download_detail_label.setText(
                "No download was started."
            )
            return

        scene_id = self.selected_scene.get(
            "id",
            "Satellite_Scene"
        )

        scene_folder = os.path.join(
            self.output_folder,
            scene_id
        )

        os.makedirs(
            scene_folder,
            exist_ok=True
        )

        self.download_button.setEnabled(False)
        self.load_into_qgis_checkbox.setEnabled(False)

        self.download_status_label.setText(
            f"Starting download: {len(selected_assets)} asset(s)..."
        )
        self.download_detail_label.setText(
            "CDSE authentication successful."
        )

        self.download_worker = SentinelDownloadWorker(
            selected_assets,
            scene_folder,
            token,
            self.asset_download_url,
            self.asset_filename,
            self,
        )

        self.download_worker.progress.connect(
            self.update_download_progress
        )

        self.download_worker.asset_finished.connect(
            self.download_asset_finished
        )

        self.download_worker.asset_failed.connect(
            self.download_asset_failed
        )

        # Capture the user's choice for this run.
        self._download_scene_id = scene_id
        self._download_scene_folder = scene_folder
        self._download_load_into_qgis = (
            self.load_into_qgis_checkbox.isChecked()
        )
        self._download_results = ([], [])

        # Store results first. Do not touch QGIS layer APIs until the
        # worker's QThread.finished signal confirms that the thread has
        # completely stopped.
        self.download_worker.finished_all.connect(
            self._store_download_results
        )
        self.download_worker.finished.connect(
            self._finalize_download_after_thread
        )

        self.download_worker.start()

    def _store_download_results(self, downloaded, failed):
        self._download_results = (downloaded, failed)

    def _finalize_download_after_thread(self):
        downloaded, failed = self._download_results

        scene_id = self._download_scene_id
        scene_folder = self._download_scene_folder
        load_into_qgis = self._download_load_into_qgis

        # Keep a reference until the thread has fully terminated.
        self._finished_download_worker = self.download_worker
        self.download_worker = None

        # Defer QGIS raster/layer operations to the next GUI event-loop
        # turn, after QThread.finished has already fired.
        QTimer.singleShot(
            0,
            lambda: self.download_finished(
                scene_id,
                scene_folder,
                downloaded,
                failed,
                load_into_qgis,
            )
        )

    def update_download_progress(
        self,
        index,
        total_assets,
        asset_id,
        percent,
        received,
    ):
        """Update the GUI from the worker's progress signal."""
        mb = received / (1024 * 1024)

        self.download_status_label.setText(
            f"Downloading {index}/{total_assets}: {asset_id}"
        )

        self.download_progress.setValue(percent)

        self.download_detail_label.setText(
            f"{mb:.1f} MB downloaded — {percent}%"
        )

    def download_asset_finished(
        self,
        asset_id,
        destination,
    ):
        self.download_status_label.setText(
            f"Completed: {asset_id}"
        )

        self.download_detail_label.setText(
            destination
        )

    def download_asset_failed(
        self,
        asset_id,
        error,
    ):
        self.download_status_label.setText(
            f"Failed: {asset_id}"
        )

        self.download_detail_label.setText(
            error
        )

    def download_finished(
        self,
        scene_id,
        scene_folder,
        downloaded,
        failed,
        load_into_qgis,
    ):
        """Completion handler runs on the QGIS GUI thread."""
        loaded = 0

        # Loading is explicitly opt-in.
        if load_into_qgis and downloaded:
            loaded = self.load_downloaded_assets(
                scene_id,
                downloaded,
            )

        self.load_into_qgis_checkbox.setEnabled(True)
        self.update_download_button_state()

        if failed:
            self.download_status_label.setText(
                f"Download complete — "
                f"{len(downloaded)} downloaded, "
                f"{len(failed)} failed."
            )
        else:
            self.download_status_label.setText(
                f"Download complete — "
                f"{len(downloaded)} asset(s) downloaded."
            )

        self.download_progress.setValue(
            100 if downloaded else 0
        )

        if load_into_qgis:
            load_detail = f"Loaded into QGIS: {loaded}"
        else:
            load_detail = "Loaded into QGIS: No (user opted out)"

        self.download_detail_label.setText(
            f"{load_detail} | Folder: {scene_folder}"
        )

        message = (
            f"Downloaded: {len(downloaded)}\n"
            f"{load_detail}\n"
            f"Failed: {len(failed)}\n\n"
            f"Folder: {scene_folder}"
        )

        if failed:
            message += (
                "\n\nFailed assets:\n"
                + "\n".join(
                    f"• {asset_id}: {error}"
                    for asset_id, error in failed
                )
            )

        QMessageBox.information(
            self,
            "Satellite-data download complete",
            message,
        )

        # The worker reference is stored on the dialog while the thread
        # finishes. Do not use an undefined local variable here.
        worker = getattr(self, "_finished_download_worker", None)
        if worker is not None:
            try:
                if worker.isRunning():
                    worker.quit()
                    worker.wait()
            except RuntimeError:
                # Qt object may already have been deleted after QThread.finished.
                pass
            finally:
                self._finished_download_worker = None

    def get_cdse_product_uuid(self, product_name):
        """Resolve a Sentinel-2 product name to its CDSE OData UUID."""
        product_name = (product_name or "").strip()

        if not product_name:
            raise ValueError("Empty Sentinel-2 product name.")

        odata_name = product_name
        if not odata_name.upper().endswith(".SAFE"):
            odata_name += ".SAFE"

        cached = self._product_uuid_cache.get(odata_name)
        if cached:
            return cached

        filter_value = odata_name.replace("'", "''")

        url = (
            "https://catalogue.dataspace.copernicus.eu/"
            "odata/v1/Products"
        )

        params = {
            "$filter": f"Name eq '{filter_value}'",
            "$select": "Id,Name",
            "$top": "1",
        }

        response = requests.get(
            url,
            params=params,
            timeout=60,
        )
        response.raise_for_status()

        products = response.json().get("value", [])

        if not products:
            raise RuntimeError(
                "CDSE OData could not find product:\n"
                f"{odata_name}\n\n"
                "The product may not yet be available in the "
                "CDSE OData catalogue."
            )

        product_uuid = products[0].get("Id")

        if not product_uuid:
            raise RuntimeError(
                f"CDSE returned {odata_name} without an OData UUID."
            )

        self._product_uuid_cache[odata_name] = product_uuid
        return product_uuid

    def asset_download_url(self, href):
        """Convert a CDSE STAC s3:// asset to an authenticated OData URL."""
        href = (href or "").strip()

        if not href:
            return href

        if href.lower().startswith(("http://", "https://")):
            return href

        if not href.lower().startswith("s3://"):
            raise ValueError(
                f"Unsupported asset URL scheme: {href}"
            )

        parsed = urlparse(href)

        if parsed.netloc.lower() != "eodata":
            raise ValueError(
                "Unsupported CDSE S3 bucket: "
                f"{parsed.netloc or 'unknown'}"
            )

        parts = [
            unquote(p)
            for p in parsed.path.split("/")
            if p
        ]

        safe_index = next(
            (
                i for i, part in enumerate(parts)
                if part.upper().endswith(".SAFE")
            ),
            None,
        )

        if safe_index is None:
            raise ValueError(
                "Could not determine the Sentinel-2 SAFE product "
                "from the asset URL."
            )

        product_safe = parts[safe_index]
        product_name = product_safe[:-5]

        product_uuid = self.get_cdse_product_uuid(
            product_name
        )

        relative_nodes = parts[safe_index:]

        url = (
            "https://download.dataspace.copernicus.eu/"
            f"odata/v1/Products({product_uuid})"
        )

        for node in relative_nodes:
            url += (
                "/Nodes("
                + quote(node, safe="._-")
                + ")"
            )

        return url + "/$value"

    def asset_filename(self, asset_id, href):
        """Create a safe local filename from the STAC asset."""
        path = href.split("?", 1)[0].rstrip("/")
        filename = os.path.basename(path)

        if not filename or filename in (".", ".."):
            filename = asset_id

        # Preserve useful JP2/TIF/XML/etc. extensions from the URL.
        if "." not in filename:
            filename = asset_id

        return filename

    def load_downloaded_assets(self, scene_id, downloaded):
        """Load downloaded raster assets and group them in the QGIS layer tree."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()

        toolkit_group = root.findGroup("RemoteSense Toolkit")
        if toolkit_group is None:
            toolkit_group = root.addGroup("RemoteSense Toolkit")

        raw_group = toolkit_group.findGroup("Raw")
        if raw_group is None:
            raw_group = toolkit_group.addGroup("Raw")

        downloaded_group = raw_group.findGroup("Downloaded")
        if downloaded_group is None:
            downloaded_group = raw_group.addGroup("Downloaded")

        sentinel_group = downloaded_group.findGroup("Sentinel-2")
        if sentinel_group is None:
            sentinel_group = downloaded_group.addGroup("Sentinel-2")

        scene_group = sentinel_group.findGroup(scene_id)
        if scene_group is None:
            scene_group = sentinel_group.addGroup(scene_id)

        loaded = 0

        raster_extensions = (
            ".tif", ".tiff", ".jp2", ".img", ".vrt"
        )

        for asset_id, filepath in downloaded:
            if not os.path.isfile(filepath):
                continue

            if not filepath.lower().endswith(raster_extensions):
                continue

            layer = QgsRasterLayer(
                filepath,
                asset_id,
                "gdal",
            )

            if not layer.isValid():
                continue

            project.addMapLayer(layer, False)
            scene_group.addLayer(layer)
            loaded += 1

        return loaded

    # =========================================================
    # CLEAR
    # =========================================================

    def clear_search(self):

        self.search_results = []

        self.selected_scene = None

        self.scene_assets = {}

        self.results_table.setRowCount(
            0
        )

        self.asset_table.setRowCount(
            0
        )

        self.selected_scene_label.setText(
            "No scene selected."
        )

        self.inspect_button.setEnabled(
            False
        )

        self.preview_button.setEnabled(False)

        self.status_label.setText(
            "Ready — configure the search criteria."
        )