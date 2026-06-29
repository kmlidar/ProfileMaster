# -*- coding: utf-8 -*-
"""
profile_master.py
Main plugin class for QGIS – ProfileMaster
"""

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon


class ProfileMasterPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icons', 'icon.png')
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(
            icon,
            "ProfileMaster",
            self.iface.mainWindow()
        )
        self.action.setToolTip(
            "Longitudinal profiles, cross-sections, 3D axis, DTM buffer and contour lines"
        )
        self.action.triggered.connect(self.run)

        self.iface.addPluginToMenu("&ProfileMaster", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu("&ProfileMaster", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        from .perfil_dialog import PerfilLongitudinalDialog
        if self.dialog is None:
            self.dialog = PerfilLongitudinalDialog(self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
