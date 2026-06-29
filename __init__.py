# -*- coding: utf-8 -*-
"""
ProfileMaster - QGIS Plugin
Longitudinal profiles, cross-sections, 3D axis, DTM buffer and contour lines.
"""


def classFactory(iface):
    from .profile_master import ProfileMasterPlugin
    return ProfileMasterPlugin(iface)
