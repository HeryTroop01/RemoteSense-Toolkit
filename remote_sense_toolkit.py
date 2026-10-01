# =============================================================================
# RemoteSense Toolkit
# -----------------------------------------------------------------------------
# File       : remote_sense_toolkit.py
# Module     : Plugin Core
# Version    : 1.0.0
# Author     : Punithan
# Project    : RemoteSense Toolkit
#
# Description:
#     Main QGIS plugin entry point.
#
#     This module initializes the RemoteSense Toolkit interface, creates the
#     plugin menu and toolbar, registers the Processing provider, and manages
#     the lifecycle of the main RemoteSense Toolkit dialog.
#
# Dependencies:
#     - QGIS / PyQGIS
#     - RemoteSense Toolkit GUI
#     - RemoteSense Toolkit Processing Provider
#
# Status     : Stable
# =============================================================================

from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .remote_sense_toolkit_dialog import RemoteSenseToolkitDialog
from .processing.remote_sense_provider import RemoteSenseProvider


class RemoteSenseToolkit:
    """Main QGIS plugin class."""

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.menu = self.tr("&RemoteSense Toolkit")
        self.toolbar = None
        self.dialog = None
        self.provider = None

    def tr(self, message):
        """Translate a plugin user-interface message."""
        return QCoreApplication.translate("RemoteSenseToolkit", message)

    def initGui(self):
        """Initialize the RemoteSense Toolkit menu, toolbar, and provider."""

        icon_path = Path(__file__).parent / "icon.png"

        action = QAction(
            QIcon(str(icon_path)),
            self.tr("RemoteSense Toolkit"),
            self.iface.mainWindow()
        )

        action.setObjectName("remoteSenseToolkitAction")
        action.setStatusTip(self.tr("Open RemoteSense Toolkit"))
        action.triggered.connect(self.run)

        self.iface.addPluginToMenu(self.menu, action)

        self.toolbar = self.iface.addToolBar(
            self.tr("RemoteSense Toolkit")
        )
        self.toolbar.setObjectName("RemoteSenseToolkitToolbar")
        self.toolbar.addAction(action)

        self.actions.append(action)

        # Register the Processing provider through QGIS's Processing registry.
        #
        # Provider registration is intentionally isolated from the main plugin
        # initialization. If Processing is unavailable or provider
        # initialization fails, the main plugin can still load.
        self.provider = None

        try:
            provider = RemoteSenseProvider()
            registry = QgsApplication.processingRegistry()

            if registry is not None and registry.addProvider(provider):
                self.provider = provider

        except Exception:
            self.provider = None

    def unload(self):
        """Remove plugin actions, toolbar, and Processing provider."""

        if self.provider is not None:
            try:
                QgsApplication.processingRegistry().removeProvider(
                    self.provider
                )
            except Exception:
                pass
            finally:
                self.provider = None

        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None

        self.actions.clear()

    def run(self):
        """Open the main RemoteSense Toolkit dialog."""

        if self.dialog is None:
            self.dialog = RemoteSenseToolkitDialog(self.iface)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()