# -*- coding: utf-8 -*-
"""
perfil_dialog.py
Diálogo principal del plugin Perfil Longitudinal MDT.
Versión extendida con pestañas para:
  • Perfil longitudinal
  • Perfiles transversales
  • Exportación MDT con buffer
  • Curvas de nivel
"""

import os
import math
import tempfile
import traceback

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
    QSpinBox, QGroupBox, QProgressBar,
    QFileDialog, QCheckBox, QMessageBox, QTabWidget, QWidget,
    QFrame, QComboBox, QRadioButton, QButtonGroup, QLayout,
)
from qgis.PyQt.QtCore import QThread, pyqtSignal, QUrl, QSettings
from qgis.PyQt.QtGui import QDesktopServices


AXIS_FORMATS = (
    "Todos los formatos compatibles (*.dxf *.shp *.kml *.kmz *.gpkg *.gml *.gpx *.geojson *.json);;"
    "DXF - AutoCAD (*.dxf *.DXF);;"
    "SHP - Shapefile (*.shp *.SHP);;"
    "KML / KMZ - Google Earth (*.kml *.kmz *.KML *.KMZ);;"
    "GeoPackage (*.gpkg *.GPKG);;"
    "GML - Geography Markup Language (*.gml *.GML);;"
    "GPX - GPS Exchange (*.gpx *.GPX);;"
    "GeoJSON (*.geojson *.json)")


def _next_profile_name(output_dir, base="perfil"):
    i = 1
    while True:
        candidate = os.path.join(output_dir, f"{base}{i}.dxf")
        if not os.path.exists(candidate):
            return f"{base}{i}"
        i += 1


# ─────────────────────────────────────────────────────────────────────────────
#  Tema claro / oscuro
# ─────────────────────────────────────────────────────────────────────────────
# Antes la hoja de estilos usaba "palette(...)" para adaptarse al tema del
# sistema, pero QGIS no siempre sincroniza su paleta con el modo claro/oscuro
# de Windows, lo que dejaba textos ilegibles en uno de los dos modos
# (p.ej. textos oscuros sobre fondo oscuro). Ahora se definen dos temas
# completos con colores explícitos y un botón en el propio diálogo para
# alternar entre ellos, independientemente del tema del sistema.

_THEMES = {
    'dark': dict(
        bg='#22232e', panel='#2b2d3a', border='#454860', fg='#e8e9f0',
        fg_disabled='#6b6e80',
        field_bg='#1b1c25', field_fg='#f0f1f6',
        field_bg_disabled='#262833', field_fg_disabled='#6b6e80',
        tab_bg='#262834', accent='#2471A3', muted='#a4a7bd', warn='#ff7a6b',
        button_bg='#343750', button_bg_hover='#3d4060', theme_btn_bg='#343750',
        check_border='#8489a8',
    ),
    'light': dict(
        bg='#f4f4f8', panel='#ffffff', border='#c7c9d6', fg='#1c1d27',
        fg_disabled='#9a9cab',
        field_bg='#ffffff', field_fg='#1c1d27',
        field_bg_disabled='#ececf2', field_fg_disabled='#9a9cab',
        tab_bg='#e7e8ef', accent='#1A5276', muted='#5b5d6c', warn='#c0392b',
        button_bg='#e9e9f0', button_bg_hover='#dadce6', theme_btn_bg='#e9e9f0',
        check_border='#6b6e80',
    ),
}

_QSS_TEMPLATE = """
QWidget {{
    background: {bg};
    color: {fg};
    font-size: 9pt;
}}
QDialog {{ background: {bg}; }}
QGroupBox {{
    font-weight: bold;
    border: 1px solid {border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 6px;
    background: {panel};
    color: {fg};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {fg};
}}
QGroupBox:disabled {{ color: {fg_disabled}; }}
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 3px;
    background: {panel};
}}
QTabBar::tab {{
    padding: 6px 14px;
    font-weight: bold;
    background: {tab_bg};
    color: {fg};
    border: 1px solid {border};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background: {panel};
    border-bottom: 2px solid {accent};
}}
QLabel {{ background: transparent; color: {fg}; }}
QCheckBox {{ background: transparent; color: {fg}; spacing: 6px; }}
QCheckBox:disabled {{ color: {fg_disabled}; }}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1.5px solid {check_border};
    border-radius: 3px;
    background: {field_bg};
}}
QCheckBox::indicator:hover {{
    border: 1.5px solid {accent};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border: 1.5px solid {accent};
}}
QCheckBox::indicator:checked:hover {{
    background: {accent};
    border: 1.5px solid {check_border};
}}
QCheckBox::indicator:disabled {{
    background: {field_bg_disabled};
    border: 1.5px solid {border};
}}
QLineEdit, QSpinBox, QDoubleSpinBox {{
    padding: 2px 4px;
    border: 1px solid {border};
    border-radius: 3px;
    background: {field_bg};
    color: {field_fg};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background: {field_bg_disabled};
    color: {field_fg_disabled};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {accent};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid {border};
    border-bottom: 1px solid {border};
    border-top-right-radius: 3px;
    background: {button_bg};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border-left: 1px solid {border};
    border-top: 1px solid {border};
    border-bottom-right-radius: 3px;
    background: {button_bg};
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {button_bg_hover};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {fg};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {fg};
}}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
    border-bottom-color: {fg_disabled};
    border-top-color: {fg_disabled};
}}
QPushButton {{
    background: {button_bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 5px 12px;
}}
QPushButton:hover {{ background: {button_bg_hover}; }}
QPushButton#btn_run {{
    background: #1A5276;
    color: white;
    font-weight: bold;
    padding: 8px 22px;
    border-radius: 5px;
    font-size: 10pt;
    border: none;
}}
QPushButton#btn_run:hover  {{ background: #2471A3; }}
QPushButton#btn_run:disabled {{ background: {border}; color: {fg_disabled}; }}
QPushButton#btn_donate {{
    background: #E67E22;
    color: white;
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 5px;
    font-size: 9pt;
    border: none;
}}
QPushButton#btn_donate:hover {{ background: #CA6F1E; }}
QPushButton#btn_close {{
    padding: 8px 16px;
    border-radius: 5px;
    font-size: 10pt;
}}
QPushButton#btn_theme {{
    padding: 5px 12px;
    border-radius: 14px;
    font-size: 9pt;
    background: {theme_btn_bg};
    border: 1px solid {border};
    color: {fg};
}}
QPushButton#btn_theme:hover {{ background: {button_bg_hover}; }}
QProgressBar {{
    border: 1px solid {border};
    border-radius: 4px;
    text-align: center;
    height: 18px;
    background: {field_bg};
    color: {fg};
}}
QProgressBar::chunk {{ background: #2471A3; border-radius: 3px; }}
QLabel#lbl_title {{
    font-size: 13pt;
    font-weight: bold;
    padding: 4px 0;
    color: {fg};
}}
QLabel#lbl_info {{
    font-size: 8pt;
    color: {muted};
}}
QLabel#lbl_warn {{
    font-size: 8pt;
    color: {warn};
    font-weight: bold;
}}
"""


def _build_stylesheet(theme):
    colors = _THEMES.get(theme, _THEMES['dark'])
    return _QSS_TEMPLATE.format(**colors)


# ─────────────────────────────────────────────────────────────────────────────
#  Idioma de la interfaz (ES / EN)
#  Igual que en CartoDXF: se traducen rótulos, botones, cabeceras, pestañas
#  y mensajes que el usuario ve a simple vista. Los tooltips largos y muy
#  detallados se mantienen en español para no disparar el alcance.
#  El toggle de idioma reconstruye la interfaz (_build_ui) leyendo el nuevo
#  diccionario, por lo que no hace falta un método de "retraducción" widget
#  a widget: el estado de los campos se guarda antes y se restaura después
#  (ver _snapshot_state / _restore_state).
# ─────────────────────────────────────────────────────────────────────────────

_STRINGS = {
    'es': dict(
        window_title='ProfileMaster',
        header_title='🗻  ProfileMaster',
        subtitle='Perfil longitudinal · Transversales · MDT buffer · Curvas de nivel',
        btn_lang='EN',
        btn_lang_tooltip='Switch interface to English',

        grp1_title='1. Datos de entrada',
        lbl_mdt='MDT:',
        rdo_folder='Carpeta',
        rdo_layer_loaded='Capa cargada',
        placeholder_folder='Carpeta con los MDTs (GeoTIFF, ASC, IMG, BIL, FLT, DEM, HGT)',
        tooltip_refresh_mdt='Actualizar lista de capas ráster cargadas',
        chk_rescan='Forzar re-escaneo de MDTs (ignorar caché)',
        lbl_axis='Eje (vectorial):',
        rdo_file='Archivo',
        placeholder_axis='DXF, SHP, KML/KMZ, GeoPackage, GML, GPX, GeoJSON',
        tooltip_refresh_axis='Actualizar lista de capas vectoriales cargadas',
        lbl_outdir='Carpeta de salida:',
        placeholder_outdir='Carpeta donde se guardarán los archivos generados',
        no_raster_layers='(no hay capas ráster cargadas)',
        no_line_layers='(no hay capas lineales cargadas)',

        tab_longitudinal='📈 Longitudinal',
        tab_transversales='📐 Transversales',
        tab_buffer='🗺 Buffer MDT',
        tab_curvas='〰 Curvas de nivel',

        chk_gen_longitudinal='✅  Generar perfil longitudinal',
        grp_longitudinal='Parámetros del perfil longitudinal',
        lbl_interval='Intervalo segmentación:',
        lbl_hscale='Escala horizontal  1:',
        lbl_vscale='Escala vertical      1:',
        lbl_textos_guitarra='Textos guitarra:',
        chk_text_vertical='Vertical (90°)',
        lbl_datos_guitarra='Datos guitarra:',
        chk_use_equidistant='Mostrar a equidistancia',
        lbl_intervalo_corto='Intervalo:',
        lbl_plano_comparacion='Plano comparación:',
        chk_automatico='Automático',
        lbl_cp_info='ℹ  Automático: múltiplo de 5 por debajo del mínimo del terreno − 5 m',
        lbl_marcas_pk='Marcas PK (equidistancia):',
        chk_gen_eje3d_eq='Generar también eje 3D limpio (sin marcas ni texto)',

        chk_gen_transversales='✅  Generar perfiles transversales',
        grp_trans='Parámetros de transversales',
        lbl_trans_spacing='Distancia entre transversales:',
        lbl_trans_left='Ancho a izquierda:',
        lbl_trans_right='Ancho a derecha:',
        lbl_trans_step='Paso muestreo transversal:',
        sep_escalas_trans='── Escalas del DXF de transversales ──────────────────────',
        lbl_trans_info=(
            'Salida: <perfil>_transversales.dxf — cuadrícula de secciones con\n'
            'terreno, eje, PK, plano de comparación y tabla de cotas.'
        ),
        sep_plano_comparacion='── Plano de comparación ──────────────────────────────────',
        lbl_plano_por_seccion='Plano por sección:',
        chk_trans_cplane_auto='Relativo (0.5 m bajo el mínimo de cada sección)',
        sep_mini_guitarra='── Mini-guitarra de cada transversal ─────────────────────',
        lbl_equidist_guitarra='Equidistancia guitarra:',

        chk_gen_mdt_buffer='✅  Exportar MDT con buffer (GeoTIFF)',
        grp_mdt_buf='Parámetros del buffer MDT',
        lbl_buffer_todas='Buffer (todas las direcciones):',
        lbl_buf_info=(
            'GeoTIFF recortado al bounding box del eje + buffer,\n'
            'fusionando todas las teselas MDT en un único ráster comprimido (LZW).'
        ),

        chk_gen_curvas='✅  Generar curvas de nivel (DXF)',
        grp_curvas='Parámetros de curvas de nivel',
        lbl_curvas_eq='Equidistancia curvas normales:',
        lbl_curvas_maestra='Equidistancia curvas maestras:',
        lbl_curvas_smooth='Suavizado (iteraciones Chaikin):',
        lbl_curvas_min_longitud='Longitud mínima de curva (m):',
        chk_curvas_simplify='Reducir vértices en tramos rectos (simplificado)',
        chk_curvas_simplify_tooltip=(
            'Aplica el algoritmo de Douglas-Peucker antes del suavizado:\n'
            'elimina vértices redundantes en los tramos donde la curva es\n'
            'prácticamente recta, sin cambiar su forma más allá de la\n'
            'tolerancia indicada. Es el mismo tipo de "reducción de vértices"\n'
            'que usan programas como Global Mapper, y reduce mucho el peso\n'
            'del DXF sin perder precisión visible en las curvas.\n\n'
            'Control anti-solape: tras simplificar y suavizar, cada curva se\n'
            'compara con la de la cota adyacente; si llegaran a tocarse, se\n'
            'reintenta automáticamente con una tolerancia menor (o, en el\n'
            'peor caso, se exporta sin simplificar) para garantizar que las\n'
            'curvas nunca se crucen entre sí.'
        ),
        lbl_curvas_simplify_tol='Tolerancia de simplificado:',
        sp_curvas_simplify_tol_tooltip=(
            'Distancia máxima (en metros) que un vértice eliminado puede\n'
            'desviarse de la línea original. Valores más altos = menos\n'
            'vértices pero más riesgo de perder detalle o de que curvas muy\n'
            'próximas entre sí lleguen a tocarse; se recomienda no superar\n'
            'una fracción de la equidistancia normal.'
        ),
        lbl_buf_req=(
            '⚠  Requiere MDT buffer. Si no está generado, se crea\n'
            '   automáticamente con el buffer de la pestaña Buffer MDT.'
        ),
        lbl_curvas_out=(
            'Salida: curvas_nivel.dxf — capas CURVAS_NORMALES,\n'
            'CURVAS_MAESTRAS (etiquetadas) y CURVAS_TEXTOS.'
        ),

        status_ready='Listo.',
        btn_run='▶  Generar',
        btn_donate='☕  Invítame a un café',
        btn_donate_tooltip='Si este plugin te resulta útil, apoya su desarrollo.',
        btn_close='Cerrar',

        dlg_select_mdt_folder='Seleccionar carpeta de MDTs',
        dlg_select_axis_file='Seleccionar archivo de eje',
        dlg_select_outdir='Seleccionar carpeta de salida',

        warn_missing_title='Falta dato',
        warn_no_raster_layer=(
            'No hay ninguna capa ráster (MDT) cargada en QGIS.\n'
            "Carga el MDT en el proyecto o usa el modo 'Carpeta'."
        ),
        warn_no_folder='Especifica la carpeta de MDTs.',
        warn_invalid_folder_title='Carpeta no válida',
        warn_folder_not_exist='La carpeta de MDTs no existe:\n{path}',
        warn_no_line_layer=(
            'No hay ninguna capa vectorial lineal cargada en QGIS.\n'
            "Carga el eje en el proyecto o usa el modo 'Archivo'."
        ),
        warn_no_axis='Especifica el archivo de eje.',
        warn_invalid_file_title='Archivo no válido',
        warn_axis_not_exist='El archivo de eje no existe:\n{path}',
        warn_no_outdir='Especifica la carpeta de salida.',
        warn_cannot_create_outdir='No se puede crear la carpeta de salida:\n{err}',
        warn_nothing_selected_title='Nada seleccionado',
        warn_nothing_selected=(
            'Activa al menos una pestaña (Longitudinal, Transversales, '
            'Buffer MDT o Curvas de nivel).'
        ),
        ask_curvas_no_buffer_title='Curvas de nivel sin buffer',
        ask_curvas_no_buffer=(
            'Las curvas de nivel requieren un MDT buffer.\n\n'
            '¿Deseas generar automáticamente el MDT buffer con el valor configurado '
            "en la pestaña 'Buffer MDT'?\n\n"
            "(No se guardará como archivo separado si 'Buffer MDT' no está activo.)"
        ),

        status_n_geometries='Se detectaron {n} geometrías en el eje.',
        status_error='❌  Error durante el proceso.',
        error_title='Error',
        status_done_ok='✅  {n} perfil(es)  |  PC={cp}  |  {cache}',
        status_done_warn='⚠️ {n} perfil(es)  |  PC={cp}  |  {cache}  |  hubo errores, revisa el resumen',
        cache_hit='caché',
        cache_miss='escaneo nuevo',
        result_title_warn='Completado con errores',
        result_title_ok='Proceso completado',
        result_mdt_buffer_error='⚠ MDT buffer: {err}',
        result_curvas_error='⚠ Curvas de nivel: {err}',
    ),
    'en': dict(
        window_title='ProfileMaster',
        header_title='🗻  ProfileMaster',
        subtitle='Longitudinal profile · Cross-sections · DTM buffer · Contour lines',
        btn_lang='ES',
        btn_lang_tooltip='Cambiar la interfaz a español',

        grp1_title='1. Input data',
        lbl_mdt='DTM:',
        rdo_folder='Folder',
        rdo_layer_loaded='Loaded layer',
        placeholder_folder='Folder with the DTMs (GeoTIFF, ASC, IMG, BIL, FLT, DEM, HGT)',
        tooltip_refresh_mdt='Refresh the list of loaded raster layers',
        chk_rescan='Force DTM re-scan (ignore cache)',
        lbl_axis='Axis (vector):',
        rdo_file='File',
        placeholder_axis='DXF, SHP, KML/KMZ, GeoPackage, GML, GPX, GeoJSON',
        tooltip_refresh_axis='Refresh the list of loaded vector layers',
        lbl_outdir='Output folder:',
        placeholder_outdir='Folder where the generated files will be saved',
        no_raster_layers='(no raster layers loaded)',
        no_line_layers='(no line layers loaded)',

        tab_longitudinal='📈 Longitudinal',
        tab_transversales='📐 Cross-sections',
        tab_buffer='🗺 DTM buffer',
        tab_curvas='〰 Contour lines',

        chk_gen_longitudinal='✅  Generate longitudinal profile',
        grp_longitudinal='Longitudinal profile parameters',
        lbl_interval='Segmentation interval:',
        lbl_hscale='Horizontal scale  1:',
        lbl_vscale='Vertical scale      1:',
        lbl_textos_guitarra='Data-table text:',
        chk_text_vertical='Vertical (90°)',
        lbl_datos_guitarra='Data-table rows:',
        chk_use_equidistant='Show at fixed spacing',
        lbl_intervalo_corto='Interval:',
        lbl_plano_comparacion='Comparison plane:',
        chk_automatico='Automatic',
        lbl_cp_info='ℹ  Automatic: multiple of 5 below the terrain minimum − 5 m',
        lbl_marcas_pk='Chainage marks (spacing):',
        chk_gen_eje3d_eq='Also generate a clean 3D axis (no marks or text)',

        chk_gen_transversales='✅  Generate cross-sections',
        grp_trans='Cross-section parameters',
        lbl_trans_spacing='Spacing between cross-sections:',
        lbl_trans_left='Width to the left:',
        lbl_trans_right='Width to the right:',
        lbl_trans_step='Cross-section sampling step:',
        sep_escalas_trans='── Cross-section DXF scales ─────────────────────────────',
        lbl_trans_info=(
            'Output: <profile>_transversales.dxf — grid of sections with\n'
            'terrain, axis, chainage, comparison plane and elevation table.'
        ),
        sep_plano_comparacion='── Comparison plane ──────────────────────────────────────',
        lbl_plano_por_seccion='Plane per section:',
        chk_trans_cplane_auto='Relative (0.5 m below the minimum of each section)',
        sep_mini_guitarra='── Mini data-table for each cross-section ────────────────',
        lbl_equidist_guitarra='Data-table spacing:',

        chk_gen_mdt_buffer='✅  Export DTM with buffer (GeoTIFF)',
        grp_mdt_buf='DTM buffer parameters',
        lbl_buffer_todas='Buffer (all directions):',
        lbl_buf_info=(
            'GeoTIFF clipped to the axis bounding box + buffer, merging all\n'
            'DTM tiles into a single LZW-compressed raster.'
        ),

        chk_gen_curvas='✅  Generate contour lines (DXF)',
        grp_curvas='Contour line parameters',
        lbl_curvas_eq='Normal contour spacing:',
        lbl_curvas_maestra='Master contour spacing:',
        lbl_curvas_smooth='Smoothing (Chaikin iterations):',
        lbl_curvas_min_longitud='Minimum contour length (m):',
        chk_curvas_simplify='Reduce vertices on straight stretches (simplify)',
        chk_curvas_simplify_tooltip=(
            'Applies the Douglas-Peucker algorithm before smoothing: removes\n'
            'redundant vertices where the contour is essentially straight,\n'
            'without changing its shape beyond the given tolerance. This is\n'
            'the same kind of "vertex reduction" used by programs like Global\n'
            'Mapper, and it greatly reduces the DXF file size without any\n'
            'visible loss of detail in the contours.\n\n'
            'Anti-overlap safeguard: after simplifying and smoothing, each\n'
            'contour is checked against the adjacent elevation level; if they\n'
            'would end up touching, it automatically retries with a smaller\n'
            'tolerance (or, as a last resort, exports without simplification)\n'
            'to guarantee that contours never cross each other.'
        ),
        lbl_curvas_simplify_tol='Simplification tolerance:',
        sp_curvas_simplify_tol_tooltip=(
            'Maximum distance (in meters) a removed vertex may deviate from\n'
            'the original line. Higher values = fewer vertices but more risk\n'
            'of losing detail, or of very close contours touching each other;\n'
            "it's recommended to keep it below a fraction of the normal\n"
            'contour spacing.'
        ),
        lbl_buf_req=(
            '⚠  Requires a DTM buffer. If it has not been generated yet, it\n'
            "   is created automatically using the 'DTM buffer' tab settings."
        ),
        lbl_curvas_out=(
            'Output: curvas_nivel.dxf — layers CURVAS_NORMALES,\n'
            'CURVAS_MAESTRAS (labeled) and CURVAS_TEXTOS.'
        ),

        status_ready='Ready.',
        btn_run='▶  Generate',
        btn_donate='☕  Buy me a coffee',
        btn_donate_tooltip='If this plugin is useful to you, support its development.',
        btn_close='Close',

        dlg_select_mdt_folder='Select DTM folder',
        dlg_select_axis_file='Select axis file',
        dlg_select_outdir='Select output folder',

        warn_missing_title='Missing data',
        warn_no_raster_layer=(
            'There is no raster layer (DTM) loaded in QGIS.\n'
            "Load the DTM in the project or use 'Folder' mode."
        ),
        warn_no_folder='Specify the DTM folder.',
        warn_invalid_folder_title='Invalid folder',
        warn_folder_not_exist='The DTM folder does not exist:\n{path}',
        warn_no_line_layer=(
            'There is no line vector layer loaded in QGIS.\n'
            "Load the axis in the project or use 'File' mode."
        ),
        warn_no_axis='Specify the axis file.',
        warn_invalid_file_title='Invalid file',
        warn_axis_not_exist='The axis file does not exist:\n{path}',
        warn_no_outdir='Specify the output folder.',
        warn_cannot_create_outdir='Could not create the output folder:\n{err}',
        warn_nothing_selected_title='Nothing selected',
        warn_nothing_selected=(
            'Enable at least one tab (Longitudinal, Cross-sections, '
            'DTM buffer or Contour lines).'
        ),
        ask_curvas_no_buffer_title='Contour lines without buffer',
        ask_curvas_no_buffer=(
            'Contour lines require a DTM buffer.\n\n'
            'Do you want to automatically generate the DTM buffer using the value '
            "configured in the 'DTM buffer' tab?\n\n"
            "(It won't be saved as a separate file unless 'DTM buffer' is enabled.)"
        ),

        status_n_geometries='{n} geometries detected in the axis.',
        status_error='❌  Error during the process.',
        error_title='Error',
        status_done_ok='✅  {n} profile(s)  |  CP={cp}  |  {cache}',
        status_done_warn='⚠️ {n} profile(s)  |  CP={cp}  |  {cache}  |  there were errors, check the summary',
        cache_hit='cache',
        cache_miss='new scan',
        result_title_warn='Completed with errors',
        result_title_ok='Process completed',
        result_mdt_buffer_error='⚠ DTM buffer: {err}',
        result_curvas_error='⚠ Contour lines: {err}',
    ),
}


def _count_profiles_in_file(axis_path):
    try:
        from osgeo import ogr
        ds = ogr.Open(axis_path)
        if ds is None:
            return 1
        count = 0
        for li in range(ds.GetLayerCount()):
            layer = ds.GetLayerByIndex(li)
            layer.ResetReading()
            for feat in layer:
                geom = feat.GetGeometryRef()
                if geom is None:
                    continue
                t = geom.GetGeometryType()
                from osgeo import ogr as _ogr
                if t in (_ogr.wkbLineString, _ogr.wkbLineString25D,
                         _ogr.wkbMultiLineString, _ogr.wkbMultiLineString25D):
                    count += 1
        ds = None
        return max(count, 1)
    except Exception:
        return 1


# ─────────────────────────────────────────────────────────────────────────────
#  Worker unificado
# ─────────────────────────────────────────────────────────────────────────────

class ProfileWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params

    def _sanitize_dxf_text(self, text):
        import unicodedata
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ASCII', 'ignore').decode('ASCII')
        text = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in text)
        return text

    def run(self):
        try:
            from .mdt_cache import load_or_build_cache, get_affected_mdts, invalidate_cache
            from .eje_utils import (
                read_all_axes_from_file, get_axis_bbox,
                segment_axis, MDTSampler, drape_points,
                interpolate_missing_z, export_all_axes_3d_dxf,
            )

            p = self.params
            folder = p['folder']
            axis_path = p['axis_path']
            interval = p['interval']
            h_scale = p['h_scale']
            v_scale = p['v_scale']
            comp_plane_value = p['comparison_plane']       # None = automático por eje
            trans_comp_value = p.get('trans_comparison_plane', None)  # None = relativo por sección
            output_dir = p['output_dir']
            profile_base = p['profile_base']
            force_rescan = p.get('force_rescan', False)
            text_vertical = p.get('text_vertical', True)
            gen_eje3d_eq = p.get('gen_eje3d_equidistante', False)
            eq_int = p.get('eje3d_equidistancia', 1.0)

            # ── 1. Caché MDTs ─────────────────────────────────────────────
            self.progress.emit(5, "Cargando caché de MDTs...")
            if force_rescan:
                invalidate_cache(folder)

            def cache_progress(pct):
                self.progress.emit(5 + int(pct * 0.15),
                                   f"Escaneando MDTs... {pct}%")

            mdts, from_cache = load_or_build_cache(folder, cache_progress)
            cache_msg = "caché existente" if from_cache else "nuevo escaneo"
            self.progress.emit(20, f"MDTs cargados: {len(mdts)} modelos ({cache_msg})")

            # ── 2. Leer ejes ──────────────────────────────────────────────
            self.progress.emit(22, "Leyendo ejes...")
            mdt_paths_all = [m['path'] for m in mdts]
            all_axes = read_all_axes_from_file(axis_path, mdt_paths=mdt_paths_all)
            n_axes = len(all_axes)
            self.progress.emit(25, f"{n_axes} eje(s) detectado(s)")

            base_num = int(profile_base.replace('perfil', '') or '1')
            all_results = []
            all_axes_3d = []

            for eje_idx, vertices_2d in enumerate(all_axes):
                current_base = f'perfil{base_num + eje_idx}'
                eje_label = current_base
                pct_start = 25 + eje_idx * (70 // n_axes)
                pct_end = 25 + (eje_idx + 1) * (70 // n_axes)

                self.progress.emit(pct_start,
                                   f"Procesando eje {eje_idx + 1}/{n_axes}: {current_base}...")

                output_perfil_dxf = os.path.join(output_dir, f"{current_base}.dxf")
                output_csv = os.path.join(output_dir, f"{current_base}.csv")

                bbox = get_axis_bbox(vertices_2d)
                affected = get_affected_mdts(mdts, bbox)
                if not affected:
                    self.progress.emit(pct_start + 2,
                                       f"⚠ {current_base}: ningún MDT intersecta.")
                    continue

                segmented, orig_indices = segment_axis(vertices_2d, interval)
                mdt_paths = [m['path'] for m in affected]
                sampler = MDTSampler(mdt_paths)

                def _drape_p(pct):
                    self.progress.emit(
                        pct_start + int(pct * (pct_end - pct_start) / 100),
                        f"Planchando {current_base}... {pct}%")

                terrain_3d = drape_points(segmented, sampler, _drape_p)
                terrain_3d = interpolate_missing_z(terrain_3d)

                # ── Transversales (si activado) ───────────────────────────
                if p.get('gen_transversales', False):
                    self.progress.emit(pct_end - 5,
                                       f"Generando transversales {current_base}...")
                    try:
                        from .transversal_dxf import export_transversales_dxf
                        out_trans = os.path.join(
                            output_dir, f"{current_base}_transversales.dxf")

                        def _trans_p(pct_t, msg):
                            self.progress.emit(
                                pct_start + int(pct_t * (pct_end - pct_start) / 100),
                                msg)

                        export_transversales_dxf(
                            vertices_2d=vertices_2d,
                            sampler=sampler,
                            spacing=p['trans_spacing'],
                            dist_left=p['trans_dist_left'],
                            dist_right=p['trans_dist_right'],
                            sample_step=p['trans_sample_step'],
                            output_path=out_trans,
                            h_scale=p.get('trans_h_scale', 500),
                            v_scale=p.get('trans_v_scale', 100),
                            axis_name=eje_label,
                            # None → plano automático por sección (0.5 m bajo el mínimo)
                            comparison_plane=trans_comp_value,
                            guitarra_interval=p.get('trans_guitarra_interval', 5.0),
                            progress_callback=_trans_p,
                        )
                    except Exception as e_t:
                        self.progress.emit(pct_end - 2,
                                           f"⚠ Error en transversales: {e_t}")

                sampler.close()

                zs_valid = [pt[2] for pt in terrain_3d if pt[2] is not None]
                if not zs_valid:
                    continue

                # Plano de comparación del perfil longitudinal
                if comp_plane_value is None:
                    comp_plane_final = math.floor(min(zs_valid) / 5) * 5 - 5
                else:
                    comp_plane_final = comp_plane_value

                from .perfil_dxf import export_profile_dxf, export_profile_csv
                try:
                    export_profile_dxf(
                        terrain_points=terrain_3d,
                        original_indices=orig_indices,
                        comparison_plane=comp_plane_final,
                        h_scale=h_scale,
                        v_scale=v_scale,
                        output_path=output_perfil_dxf,
                        title=(
                            f"{eje_label} - "
                            f"{self._sanitize_dxf_text(os.path.splitext(os.path.basename(axis_path))[0])}  "
                            f"[PC={comp_plane_final:.2f} m  H1:{h_scale}  V1:{v_scale}]"
                        ),
                        text_vertical=text_vertical,
                        use_equidistant=p.get('use_equidistant', False),
                        equidistant_interval=p.get('equidistant_interval', 100.0),
                    )
                except PermissionError:
                    raise PermissionError(
                        f"No se puede escribir:\n{output_perfil_dxf}\n\n"
                        "Cierra el DXF en AutoCAD y vuelve a intentarlo.")

                export_profile_csv(
                    terrain_points=terrain_3d,
                    original_indices=orig_indices,
                    output_path=output_csv,
                    axis_name=eje_label,
                    use_equidistant=p.get('use_equidistant', False),
                    equidistant_interval=p.get('equidistant_interval', 100.0),
                )

                orig_3d = [terrain_3d[i] for i in orig_indices]
                all_axes_3d.append((eje_label, orig_3d))

                all_results.append({
                    'label': eje_label,
                    'terrain_3d': terrain_3d,
                    'orig_indices': orig_indices,
                    'output_perfil_dxf': output_perfil_dxf,
                    'output_csv': output_csv,
                    'comp_plane_final': comp_plane_final,
                    'n_mdts': len(affected),
                    'vertices_2d': vertices_2d,
                })

            if not all_results:
                self.error.emit(
                    "No se generó ningún perfil.\n\n"
                    "Posibles causas:\n"
                    "• El eje queda fuera del MDT.\n"
                    "• CRS del eje y del MDT no coinciden.\n"
                    "• El archivo de eje no contiene geometrías lineales.")
                return

            # ── Sampler para las marcas de equidistancia del eje 3D ───────
            # Se usa tanto en el eje 3D de vértices originales (que ahora
            # también lleva marcas extra en los PK redondos según
            # 'eje3d_equidistancia', p.ej. 0+000, 0+100, 0+200... si es
            # 100 m) como, opcionalmente, en el eje 3D limpio equidistante.
            all_mdt_paths = [m['path'] for m in mdts]
            eje3d_sampler = MDTSampler(all_mdt_paths)

            try:
                # ── DXF ejes 3D (vértices originales + marcas de PK) ──────
                output_dxf3d = os.path.join(output_dir, "perfiles_ejes3d.dxf")
                try:
                    export_all_axes_3d_dxf(
                        all_axes_3d, output_dxf3d,
                        equidistant_interval=eq_int,
                        sampler=eje3d_sampler,
                    )
                except PermissionError:
                    raise PermissionError(
                        f"No se puede escribir:\n{output_dxf3d}\nCiérralo y reintenta.")

                # ── DXF eje 3D con vértices INTERPOLADOS a equidistancia (limpio) ─
                output_dxf3d_eq = None
                if gen_eje3d_eq:
                    seg_int = p.get('interval', 1.0)
                    output_dxf3d_eq = os.path.join(
                        output_dir, f"perfiles_ejes3d_eq{seg_int:.1f}m.dxf")
                    self.progress.emit(
                        93, f"Generando eje 3D equidistante: vértice cada {seg_int} m...")
                    try:
                        export_all_axes_3d_dxf(
                            all_axes_3d,
                            output_dxf3d_eq,
                            equidistant_interval=seg_int,
                            sampler=eje3d_sampler,
                            clean_equidistant=True,
                        )
                    except PermissionError:
                        raise PermissionError(
                            f"No se puede escribir:\n{output_dxf3d_eq}")
            finally:
                eje3d_sampler.close()

            # ── Exportar MDT con buffer ────────────────────────────────────
            output_mdt_buffer = None
            mdt_buffer_error = None
            if p.get('gen_mdt_buffer', False):
                buf = p.get('mdt_buffer_m', 100.0)
                self.progress.emit(95, f"Exportando MDT con buffer {buf} m (siguiendo trazado)...")
                try:
                    from .mdt_export import export_mdt_buffer
                    output_mdt_buffer = os.path.join(output_dir, "mdt_buffer.tif")
                    all_verts = [r['vertices_2d'] for r in all_results]

                    def _mdt_p(pct, msg):
                        self.progress.emit(95 + int(pct * 0.03), msg)

                    export_mdt_buffer(
                        vertices_2d=all_verts,
                        mdt_list=mdts,
                        buffer_m=buf,
                        output_path=output_mdt_buffer,
                        progress_callback=_mdt_p,
                    )
                except Exception as e_m:
                    mdt_buffer_error = f"{type(e_m).__name__}: {e_m}"
                    self.progress.emit(96, f"⚠ Error MDT buffer: {mdt_buffer_error}")
                    output_mdt_buffer = None

            # ── Curvas de nivel ───────────────────────────────────────────
            output_curvas = None
            curvas_error = None
            if p.get('gen_curvas', False):
                self.progress.emit(97, "Generando curvas de nivel...")
                temp_geotiff = None
                try:
                    from .mdt_export import export_mdt_buffer, export_curvas_nivel

                    geotiff_src = output_mdt_buffer
                    if not geotiff_src or not os.path.exists(geotiff_src):
                        # La pestaña 'Buffer MDT' no está activa: se recorta
                        # un MDT SOLO para calcular las curvas, en un
                        # archivo temporal que se borra al terminar. Así
                        # nunca queda un .tif de más en la carpeta de salida
                        # si el usuario no pidió exportar el buffer.
                        buf_curvas = p.get('mdt_buffer_m', 100.0)
                        # tempfile.mkstemp() CREA el archivo en el momento de
                        # llamarlo (queda un .tif de 0 bytes en disco). Si
                        # luego export_mdt_buffer() encuentra ese archivo ya
                        # existente e intenta borrarlo con el driver GDAL,
                        # falla porque no es un GeoTIFF válido (0 bytes) y
                        # eso se reportaba erróneamente como "bloqueado por
                        # QGIS". Por eso aquí se cierra y se borra de
                        # inmediato: solo interesa reservar el NOMBRE del
                        # temporal, no el archivo en sí.
                        fd, temp_geotiff = tempfile.mkstemp(
                            suffix='.tif', prefix='profilemaster_buffer_')
                        os.close(fd)
                        try:
                            os.remove(temp_geotiff)
                        except OSError:
                            pass
                        geotiff_src = temp_geotiff
                        all_verts = [r['vertices_2d'] for r in all_results]

                        def _mdt_p2(pct, msg):
                            self.progress.emit(97, msg)

                        export_mdt_buffer(
                            vertices_2d=all_verts,
                            mdt_list=mdts,
                            buffer_m=buf_curvas,
                            output_path=geotiff_src,
                            progress_callback=_mdt_p2,
                        )

                    output_curvas = os.path.join(output_dir, "curvas_nivel.dxf")

                    def _curvas_p(pct, msg):
                        self.progress.emit(97 + int(pct * 0.02), msg)

                    export_curvas_nivel(
                        geotiff_path=geotiff_src,
                        output_dxf_path=output_curvas,
                        equidistancia=p.get('curvas_equidistancia', 1.0),
                        equidistancia_maestra=p.get('curvas_maestra', 5.0),
                        smooth_iterations=p.get('curvas_smooth', 2),
                        min_longitud=p.get('curvas_min_longitud', 30.0),
                        simplify=p.get('curvas_simplify', True),
                        simplify_tolerance=p.get('curvas_simplify_tolerance', 0.25),
                        progress_callback=_curvas_p,
                    )
                except Exception as e_c:
                    curvas_error = f"{type(e_c).__name__}: {e_c}"
                    self.progress.emit(98, f"⚠ Error curvas: {curvas_error}")
                    output_curvas = None
                finally:
                    # El MDT recortado usado SOLO para calcular las curvas de
                    # nivel es siempre desechable: si la pestaña 'Buffer MDT'
                    # no está activa, este .tif temporal (y su posible
                    # sidecar .aux.xml de estadísticas que GDAL puede crear
                    # junto a él) NUNCA debe sobrevivir a esta ejecución.
                    if temp_geotiff:
                        for tmp_f in (temp_geotiff, temp_geotiff + '.aux.xml'):
                            if os.path.exists(tmp_f):
                                try:
                                    os.remove(tmp_f)
                                except OSError:
                                    pass

            self.progress.emit(99, f"{len(all_results)} perfil(es) generado(s)")

            self.finished.emit({
                'all_results': all_results,
                'output_dxf3d': output_dxf3d,
                'output_dxf3d_eq': output_dxf3d_eq,
                'output_mdt_buffer': output_mdt_buffer,
                'output_curvas': output_curvas,
                'mdt_buffer_error': mdt_buffer_error,
                'curvas_error': curvas_error,
                'n_axes': len(all_results),
                'from_cache': from_cache,
                'profile_base': profile_base,
                'output_dir': output_dir,
                'comp_plane_final': all_results[0]['comp_plane_final'],
                'h_scale': h_scale,
                'v_scale': v_scale,
            })

        except PermissionError as e:
            self.error.emit(str(e))
        except (ModuleNotFoundError, ImportError) as e:
            if 'ezdxf' in str(e):
                self.error.emit(
                    "No se pudo instalar 'ezdxf' automáticamente.\n\n"
                    "Instálala desde OSGeo4W Shell (como Administrador):\n"
                    "  python -m pip install ezdxf\n\n"
                    f"(Detalle: {e})"
                )
            else:
                self.error.emit(f"Error de módulo: {e}\n\n{traceback.format_exc()}")
        except ValueError as e:
            self.error.emit(str(e))
        except RuntimeError as e:
            msg = str(e)
            _gdal_markers = ('OGR Error', 'GDAL', 'PROJ', 'CPLE_',
                             'Corrupt data', 'Unsupported SRS', 'tmerc',
                             'Invalid latitude')
            if any(m in msg for m in _gdal_markers):
                self.error.emit(
                    "Error al leer los datos geográficos (CRS / proyección).\n\n"
                    f"Detalle: {msg}\n\n"
                    "Revisa que el eje y los MDTs tengan el mismo CRS.")
            else:
                self.error.emit(
                    f"Error inesperado: {type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        except Exception as e:
            self.error.emit(
                f"Error inesperado: {type(e).__name__}: {e}\n\n{traceback.format_exc()}")


# ─────────────────────────────────────────────────────────────────────────────
#  Diálogo principal con pestañas
# ─────────────────────────────────────────────────────────────────────────────

class PerfilLongitudinalDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._result = None

        self._settings = QSettings()
        saved_theme = self._settings.value("PerfilLongitudinalMDT/theme", None)
        if saved_theme in ('dark', 'light'):
            self._theme = saved_theme
        else:
            # Autodetección a partir del color de fondo actual de Qt/QGIS,
            # solo como punto de partida; el botón de la cabecera permite
            # cambiarlo manualmente en cualquier momento.
            bg_lightness = self.palette().window().color().lightness()
            self._theme = 'dark' if bg_lightness < 128 else 'light'

        saved_lang = self._settings.value("PerfilLongitudinalMDT/lang", None)
        if saved_lang in ('es', 'en'):
            self._lang = saved_lang
        else:
            sys_lang = QSettings().value("locale/userLocale", "") or ""
            self._lang = 'es' if str(sys_lang).lower().startswith('es') else 'en'
        self.strings = _STRINGS[self._lang]

        self.setWindowTitle(self.strings['window_title'])
        self._build_ui()

        # El mínimo se recalcula a partir de lo que el propio contenido
        # necesita (en vez de un valor fijo 680x640) para que la ventana no
        # se pueda encoger por debajo de lo que hace falta para mostrar sin
        # solaparse ni sus 4 pestañas ni el resto de controles.
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.resize(720, 760)

    # ─────────────────────────────────────────────────────────────────────────
    #  UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        s = self.strings
        main = QVBoxLayout(self)
        main.setSpacing(8)
        main.setContentsMargins(12, 12, 12, 12)

        # ── Estilo: tema claro/oscuro con colores explícitos (ver botón 🌙/☀️) ──
        self.setStyleSheet(_build_stylesheet(self._theme))

        # ── Cabecera ──────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title = QLabel(s['header_title'])
        title.setObjectName("lbl_title")
        header_row.addWidget(title)
        header_row.addStretch()

        self.btn_lang = QPushButton()
        self.btn_lang.setObjectName("btn_theme")
        self.btn_lang.clicked.connect(self._toggle_lang)
        header_row.addWidget(self.btn_lang)

        self.btn_theme = QPushButton()
        self.btn_theme.setObjectName("btn_theme")
        self.btn_theme.clicked.connect(self._toggle_theme)
        header_row.addWidget(self.btn_theme)
        main.addLayout(header_row)

        sub = QLabel(s['subtitle'])
        sub.setObjectName("lbl_info")
        main.addWidget(sub)

        # ── 1. Datos de entrada (siempre visibles) ────────────────────────
        grp1 = QGroupBox(s['grp1_title'])
        g1 = QGridLayout(grp1)
        g1.setSpacing(6)

        # ── MDT: modo carpeta vs capa cargada ────────────────────────────
        g1.addWidget(QLabel(s['lbl_mdt']), 0, 0)
        mdt_mode_row = QHBoxLayout()
        self._rdo_mdt_folder = QRadioButton(s['rdo_folder'])
        self._rdo_mdt_layer = QRadioButton(s['rdo_layer_loaded'])
        self._rdo_mdt_folder.setChecked(True)
        self._bg_mdt = QButtonGroup(self)
        self._bg_mdt.addButton(self._rdo_mdt_folder, 0)
        self._bg_mdt.addButton(self._rdo_mdt_layer, 1)
        mdt_mode_row.addWidget(self._rdo_mdt_folder)
        mdt_mode_row.addWidget(self._rdo_mdt_layer)
        mdt_mode_row.addStretch()
        g1.addLayout(mdt_mode_row, 0, 1, 1, 2)

        # Carpeta MDT
        self.le_folder = QLineEdit()
        self.le_folder.setPlaceholderText(s['placeholder_folder'])
        g1.addWidget(self.le_folder, 1, 1)
        self._btn_browse_folder = QPushButton("…")
        self._btn_browse_folder.setMaximumWidth(32)
        self._btn_browse_folder.clicked.connect(self._browse_folder)
        g1.addWidget(self._btn_browse_folder, 1, 2)

        # Capa MDT (combo)
        self._cmb_mdt_layer = QComboBox()
        self._cmb_mdt_layer.setVisible(False)
        g1.addWidget(self._cmb_mdt_layer, 2, 1)
        self._btn_refresh_mdt = QPushButton("↺")
        self._btn_refresh_mdt.setMaximumWidth(32)
        self._btn_refresh_mdt.setToolTip(s['tooltip_refresh_mdt'])
        self._btn_refresh_mdt.setVisible(False)
        self._btn_refresh_mdt.clicked.connect(self._refresh_mdt_layers)
        g1.addWidget(self._btn_refresh_mdt, 2, 2)

        self._bg_mdt.idToggled.connect(self._toggle_mdt_mode)

        self.chk_rescan = QCheckBox(s['chk_rescan'])
        g1.addWidget(self.chk_rescan, 3, 0, 1, 3)

        # ── Eje: modo archivo vs capa cargada ────────────────────────────
        g1.addWidget(QLabel(s['lbl_axis']), 4, 0)
        eje_mode_row = QHBoxLayout()
        self._rdo_eje_file = QRadioButton(s['rdo_file'])
        self._rdo_eje_layer = QRadioButton(s['rdo_layer_loaded'])
        self._rdo_eje_file.setChecked(True)
        self._bg_eje = QButtonGroup(self)
        self._bg_eje.addButton(self._rdo_eje_file, 0)
        self._bg_eje.addButton(self._rdo_eje_layer, 1)
        eje_mode_row.addWidget(self._rdo_eje_file)
        eje_mode_row.addWidget(self._rdo_eje_layer)
        eje_mode_row.addStretch()
        g1.addLayout(eje_mode_row, 4, 1, 1, 2)

        # Archivo eje
        self.le_axis = QLineEdit()
        self.le_axis.setPlaceholderText(s['placeholder_axis'])
        g1.addWidget(self.le_axis, 5, 1)
        self._btn_browse_axis = QPushButton("…")
        self._btn_browse_axis.setMaximumWidth(32)
        self._btn_browse_axis.clicked.connect(self._browse_axis)
        g1.addWidget(self._btn_browse_axis, 5, 2)

        # Capa eje (combo)
        self._cmb_eje_layer = QComboBox()
        self._cmb_eje_layer.setVisible(False)
        g1.addWidget(self._cmb_eje_layer, 6, 1)
        self._btn_refresh_eje = QPushButton("↺")
        self._btn_refresh_eje.setMaximumWidth(32)
        self._btn_refresh_eje.setToolTip(s['tooltip_refresh_axis'])
        self._btn_refresh_eje.setVisible(False)
        self._btn_refresh_eje.clicked.connect(self._refresh_eje_layers)
        g1.addWidget(self._btn_refresh_eje, 6, 2)

        self._bg_eje.idToggled.connect(self._toggle_eje_mode)

        # ── Carpeta de salida ─────────────────────────────────────────────
        g1.addWidget(QLabel(s['lbl_outdir']), 7, 0)
        self.le_outdir = QLineEdit()
        self.le_outdir.setPlaceholderText(s['placeholder_outdir'])
        g1.addWidget(self.le_outdir, 7, 1)
        b3 = QPushButton("…")
        b3.setMaximumWidth(32)
        b3.clicked.connect(self._browse_outdir)
        g1.addWidget(b3, 7, 2)

        main.addWidget(grp1)

        # Populate layer combos on startup
        self._refresh_mdt_layers()
        self._refresh_eje_layers()

        # ── Pestañas ──────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tab_longitudinal(), s['tab_longitudinal'])
        self.tabs.addTab(self._build_tab_transversales(), s['tab_transversales'])
        self.tabs.addTab(self._build_tab_mdt_buffer(), s['tab_buffer'])
        self.tabs.addTab(self._build_tab_curvas(), s['tab_curvas'])

        main.addWidget(self.tabs)

        # ── Progreso ──────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        main.addWidget(self.progress_bar)

        self.lbl_status = QLabel(s['status_ready'])
        self.lbl_status.setObjectName("lbl_info")
        main.addWidget(self.lbl_status)

        # ── Botones ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self.btn_run = QPushButton(s['btn_run'])
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._run)
        btn_row.addWidget(self.btn_run)

        btn_row.addStretch()

        btn_donate = QPushButton(s['btn_donate'])
        btn_donate.setObjectName("btn_donate")
        btn_donate.setToolTip(s['btn_donate_tooltip'])
        btn_donate.clicked.connect(self._open_donate)
        btn_row.addWidget(btn_donate)

        btn_close = QPushButton(s['btn_close'])
        btn_close.setObjectName("btn_close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)

        main.addLayout(btn_row)

        self._update_theme_button()
        self._update_lang_button()

    # ── PESTAÑA 1: Longitudinal ───────────────────────────────────────────

    def _build_tab_longitudinal(self):
        s = self.strings
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Activar longitudinal
        self.chk_gen_longitudinal = QCheckBox(s['chk_gen_longitudinal'])
        self.chk_gen_longitudinal.setChecked(True)
        self.chk_gen_longitudinal.setStyleSheet("font-weight:bold;")
        self.chk_gen_longitudinal.toggled.connect(self._toggle_longitudinal_group)
        layout.addWidget(self.chk_gen_longitudinal)

        self.grp_longitudinal = QGroupBox(s['grp_longitudinal'])

        g = QGridLayout(self.grp_longitudinal)
        g.setSpacing(6)

        g.addWidget(QLabel(s['lbl_interval']), 0, 0)
        self.sp_interval = QDoubleSpinBox()
        self.sp_interval.setRange(0.1, 100.0)
        self.sp_interval.setValue(1.0)
        self.sp_interval.setSingleStep(0.5)
        self.sp_interval.setSuffix(" m")
        g.addWidget(self.sp_interval, 0, 1)

        g.addWidget(QLabel(s['lbl_hscale']), 1, 0)
        self.sp_hscale = QSpinBox()
        self.sp_hscale.setRange(50, 50000)
        self.sp_hscale.setValue(1000)
        self.sp_hscale.setSingleStep(500)
        g.addWidget(self.sp_hscale, 1, 1)

        g.addWidget(QLabel(s['lbl_vscale']), 2, 0)
        self.sp_vscale = QSpinBox()
        self.sp_vscale.setRange(10, 5000)
        self.sp_vscale.setValue(100)
        self.sp_vscale.setSingleStep(50)
        g.addWidget(self.sp_vscale, 2, 1)

        g.addWidget(QLabel(s['lbl_textos_guitarra']), 3, 0)
        self.chk_text_vertical = QCheckBox(s['chk_text_vertical'])
        self.chk_text_vertical.setChecked(True)
        g.addWidget(self.chk_text_vertical, 3, 1)

        g.addWidget(QLabel(s['lbl_datos_guitarra']), 4, 0)
        eq_row = QHBoxLayout()
        self.chk_use_equidistant = QCheckBox(s['chk_use_equidistant'])
        self.chk_use_equidistant.toggled.connect(self._toggle_equidistant)
        eq_row.addWidget(self.chk_use_equidistant)
        self.sp_equidistant = QDoubleSpinBox()
        self.sp_equidistant.setRange(1.0, 10000.0)
        self.sp_equidistant.setValue(100.0)
        self.sp_equidistant.setDecimals(1)
        self.sp_equidistant.setSuffix(" m")
        self.sp_equidistant.setEnabled(False)
        eq_row.addWidget(QLabel(s['lbl_intervalo_corto']))
        eq_row.addWidget(self.sp_equidistant)
        eq_row.addStretch()
        g.addLayout(eq_row, 4, 1)

        g.addWidget(QLabel(s['lbl_plano_comparacion']), 5, 0)
        cp_row = QHBoxLayout()
        self.chk_cplane_auto = QCheckBox(s['chk_automatico'])
        self.chk_cplane_auto.setChecked(True)
        self.chk_cplane_auto.toggled.connect(self._toggle_cplane)
        cp_row.addWidget(self.chk_cplane_auto)
        self.sp_cplane = QDoubleSpinBox()
        self.sp_cplane.setRange(-9999.0, 99999.0)
        self.sp_cplane.setValue(0.0)
        self.sp_cplane.setDecimals(2)
        self.sp_cplane.setSuffix(" m")
        self.sp_cplane.setEnabled(False)
        cp_row.addWidget(self.sp_cplane)
        cp_row.addStretch()
        g.addLayout(cp_row, 5, 1)

        lbl_cp = QLabel(s['lbl_cp_info'])
        lbl_cp.setObjectName("lbl_info")
        lbl_cp.setWordWrap(True)
        g.addWidget(lbl_cp, 6, 0, 1, 2)

        # ── Eje 3D equidistante ───────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        g.addWidget(sep, 7, 0, 1, 2)

        eq3d_row = QHBoxLayout()
        eq3d_row.addWidget(QLabel(s['lbl_marcas_pk']))
        self.sp_eje3d_equidistancia = QDoubleSpinBox()
        self.sp_eje3d_equidistancia.setRange(0.1, 1000.0)
        self.sp_eje3d_equidistancia.setValue(100.0)
        self.sp_eje3d_equidistancia.setDecimals(1)
        self.sp_eje3d_equidistancia.setSuffix(" m")
        self.sp_eje3d_equidistancia.setToolTip(
            "Equidistancia de las marcas de PK redondo en el eje 3D.\n"
            "Ej: 100 m → marcas en 0+100, 0+200, 0+300...")
        eq3d_row.addWidget(self.sp_eje3d_equidistancia)
        eq3d_row.addStretch()
        g.addLayout(eq3d_row, 8, 0, 1, 2)

        self.chk_gen_eje3d_eq = QCheckBox(s['chk_gen_eje3d_eq'])
        self.chk_gen_eje3d_eq.setToolTip(
            "DXF adicional con la polilínea 3D planchada sobre el MDT,\n"
            "con un vértice cada intervalo de segmentación. Sin texto ni marcas.")
        g.addWidget(self.chk_gen_eje3d_eq, 9, 0, 1, 2)

        layout.addWidget(self.grp_longitudinal)
        layout.addStretch()
        return w

    # ── PESTAÑA 2: Transversales ──────────────────────────────────────────

    def _build_tab_transversales(self):
        s = self.strings
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chk_gen_transversales = QCheckBox(s['chk_gen_transversales'])
        self.chk_gen_transversales.setChecked(False)
        self.chk_gen_transversales.setStyleSheet("font-weight:bold;")
        self.chk_gen_transversales.toggled.connect(self._toggle_transversales_group)
        layout.addWidget(self.chk_gen_transversales)

        self.grp_trans = QGroupBox(s['grp_trans'])

        self.grp_trans.setEnabled(False)
        g = QGridLayout(self.grp_trans)
        g.setSpacing(6)

        g.addWidget(QLabel(s['lbl_trans_spacing']), 0, 0)
        self.sp_trans_spacing = QDoubleSpinBox()
        self.sp_trans_spacing.setRange(1.0, 10000.0)
        self.sp_trans_spacing.setValue(20.0)
        self.sp_trans_spacing.setDecimals(1)
        self.sp_trans_spacing.setSuffix(" m")
        self.sp_trans_spacing.setToolTip("Distancia entre secciones transversales a lo largo del eje.")
        g.addWidget(self.sp_trans_spacing, 0, 1)

        g.addWidget(QLabel(s['lbl_trans_left']), 1, 0)
        self.sp_trans_left = QDoubleSpinBox()
        self.sp_trans_left.setRange(1.0, 5000.0)
        self.sp_trans_left.setValue(10.0)
        self.sp_trans_left.setDecimals(1)
        self.sp_trans_left.setSuffix(" m")
        self.sp_trans_left.setToolTip("Metros a muestrear a la izquierda del eje.")
        g.addWidget(self.sp_trans_left, 1, 1)

        g.addWidget(QLabel(s['lbl_trans_right']), 2, 0)
        self.sp_trans_right = QDoubleSpinBox()
        self.sp_trans_right.setRange(1.0, 5000.0)
        self.sp_trans_right.setValue(10.0)
        self.sp_trans_right.setDecimals(1)
        self.sp_trans_right.setSuffix(" m")
        self.sp_trans_right.setToolTip("Metros a muestrear a la derecha del eje. Puede ser distinto al de izquierda.")
        g.addWidget(self.sp_trans_right, 2, 1)

        g.addWidget(QLabel(s['lbl_trans_step']), 3, 0)
        self.sp_trans_step = QDoubleSpinBox()
        self.sp_trans_step.setRange(0.1, 100.0)
        self.sp_trans_step.setValue(1.0)
        self.sp_trans_step.setDecimals(2)
        self.sp_trans_step.setSuffix(" m")
        self.sp_trans_step.setToolTip("Resolución del muestreo perpendicular al eje.")
        g.addWidget(self.sp_trans_step, 3, 1)

        sep = QLabel(s['sep_escalas_trans'])

        g.addWidget(sep, 4, 0, 1, 2)

        g.addWidget(QLabel(s['lbl_hscale']), 5, 0)
        self.sp_trans_hscale = QSpinBox()
        self.sp_trans_hscale.setRange(50, 10000)
        self.sp_trans_hscale.setValue(500)
        self.sp_trans_hscale.setSingleStep(100)
        g.addWidget(self.sp_trans_hscale, 5, 1)

        g.addWidget(QLabel(s['lbl_vscale']), 6, 0)
        self.sp_trans_vscale = QSpinBox()
        self.sp_trans_vscale.setRange(10, 2000)
        self.sp_trans_vscale.setValue(100)
        self.sp_trans_vscale.setSingleStep(50)
        g.addWidget(self.sp_trans_vscale, 6, 1)

        lbl_info = QLabel(s['lbl_trans_info'])
        lbl_info.setObjectName("lbl_info")
        lbl_info.setWordWrap(True)
        g.addWidget(lbl_info, 7, 0, 1, 2)

        sep2 = QLabel(s['sep_plano_comparacion'])
        g.addWidget(sep2, 8, 0, 1, 2)

        g.addWidget(QLabel(s['lbl_plano_por_seccion']), 9, 0)
        trans_cp_row = QHBoxLayout()
        self.chk_trans_cplane_auto = QCheckBox(s['chk_trans_cplane_auto'])
        self.chk_trans_cplane_auto.setChecked(True)
        self.chk_trans_cplane_auto.setToolTip(
            "Cada transversal usa su propio plano: redondeado a 0.5 m por\n"
            "debajo del punto más bajo del terreno EN ESA SECCIÓN (margen\n"
            "pequeño y fijo, sin huecos grandes entre el plano y el terreno).")
        self.chk_trans_cplane_auto.toggled.connect(self._toggle_trans_cplane)
        trans_cp_row.addWidget(self.chk_trans_cplane_auto)
        self.sp_trans_cplane = QDoubleSpinBox()
        self.sp_trans_cplane.setRange(-9999.0, 99999.0)
        self.sp_trans_cplane.setValue(0.0)
        self.sp_trans_cplane.setDecimals(2)
        self.sp_trans_cplane.setSuffix(" m")
        self.sp_trans_cplane.setEnabled(False)
        self.sp_trans_cplane.setToolTip("Plano fijo igual para todas las transversales.")
        trans_cp_row.addWidget(self.sp_trans_cplane)
        trans_cp_row.addStretch()
        g.addLayout(trans_cp_row, 9, 1)

        sep3 = QLabel(s['sep_mini_guitarra'])
        g.addWidget(sep3, 10, 0, 1, 2)

        g.addWidget(QLabel(s['lbl_equidist_guitarra']), 11, 0)
        self.sp_trans_guitarra_eq = QDoubleSpinBox()
        self.sp_trans_guitarra_eq.setRange(0.1, 1000.0)
        self.sp_trans_guitarra_eq.setValue(5.0)
        self.sp_trans_guitarra_eq.setDecimals(1)
        self.sp_trans_guitarra_eq.setSuffix(" m")
        self.sp_trans_guitarra_eq.setToolTip(
            "Se dibuja una columna en la mini-guitarra (con la cota del terreno)\n"
            "cada esta distancia, a izquierda y derecha del eje, hasta llegar al\n"
            "ancho configurado arriba (izquierda/derecha).\n"
            "Ejemplos: 5 m → marca cada 5 m; 10 m → cada 10 m; 1 m → cada 1 m.\n"
            "El propio eje (distancia 0) ya se marca aparte con un círculo y su cota.")
        g.addWidget(self.sp_trans_guitarra_eq, 11, 1)

        layout.addWidget(self.grp_trans)
        layout.addStretch()
        return w

    # ── PESTAÑA 3: Buffer MDT ─────────────────────────────────────────────

    def _build_tab_mdt_buffer(self):
        s = self.strings
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chk_gen_mdt_buffer = QCheckBox(s['chk_gen_mdt_buffer'])
        self.chk_gen_mdt_buffer.setChecked(False)
        self.chk_gen_mdt_buffer.setStyleSheet("font-weight:bold;")
        self.chk_gen_mdt_buffer.toggled.connect(self._toggle_mdt_buffer_group)
        layout.addWidget(self.chk_gen_mdt_buffer)

        self.grp_mdt_buf = QGroupBox(s['grp_mdt_buf'])

        self.grp_mdt_buf.setEnabled(False)
        g = QGridLayout(self.grp_mdt_buf)
        g.setSpacing(6)

        g.addWidget(QLabel(s['lbl_buffer_todas']), 0, 0)
        self.sp_mdt_buffer = QDoubleSpinBox()
        self.sp_mdt_buffer.setRange(1.0, 100000.0)
        self.sp_mdt_buffer.setValue(100.0)
        self.sp_mdt_buffer.setDecimals(0)
        self.sp_mdt_buffer.setSuffix(" m")
        self.sp_mdt_buffer.setToolTip(
            "Buffer cuadrado aplicado al bbox del eje.\n"
            "Se aplica también en sentido longitudinal (inicio y fin)\n"
            "para asegurar cobertura completa en todas las direcciones."
        )
        g.addWidget(self.sp_mdt_buffer, 0, 1)

        lbl_buf = QLabel(s['lbl_buf_info'])
        lbl_buf.setObjectName("lbl_info")
        lbl_buf.setWordWrap(True)
        g.addWidget(lbl_buf, 1, 0, 1, 2)

        layout.addWidget(self.grp_mdt_buf)
        layout.addStretch()
        return w

    # ── PESTAÑA 4: Curvas de nivel ────────────────────────────────────────

    def _build_tab_curvas(self):
        s = self.strings
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chk_gen_curvas = QCheckBox(s['chk_gen_curvas'])
        self.chk_gen_curvas.setChecked(False)
        self.chk_gen_curvas.setStyleSheet("font-weight:bold;")
        self.chk_gen_curvas.toggled.connect(self._toggle_curvas_group)
        layout.addWidget(self.chk_gen_curvas)

        self.grp_curvas = QGroupBox(s['grp_curvas'])

        self.grp_curvas.setEnabled(False)
        g = QGridLayout(self.grp_curvas)
        g.setSpacing(6)

        g.addWidget(QLabel(s['lbl_curvas_eq']), 0, 0)
        self.sp_curvas_eq = QDoubleSpinBox()
        self.sp_curvas_eq.setRange(0.1, 100.0)
        self.sp_curvas_eq.setValue(1.0)
        self.sp_curvas_eq.setDecimals(2)
        self.sp_curvas_eq.setSuffix(" m")
        g.addWidget(self.sp_curvas_eq, 0, 1)

        g.addWidget(QLabel(s['lbl_curvas_maestra']), 1, 0)
        self.sp_curvas_maestra = QDoubleSpinBox()
        self.sp_curvas_maestra.setRange(0.5, 1000.0)
        self.sp_curvas_maestra.setValue(5.0)
        self.sp_curvas_maestra.setDecimals(1)
        self.sp_curvas_maestra.setSuffix(" m")
        self.sp_curvas_maestra.setToolTip(
            "Múltiplo de la equidistancia normal para curvas maestras\n"
            "(líneas de mayor grosor y con etiqueta de cota).")
        g.addWidget(self.sp_curvas_maestra, 1, 1)

        g.addWidget(QLabel(s['lbl_curvas_smooth']), 2, 0)
        self.sp_curvas_smooth = QSpinBox()
        self.sp_curvas_smooth.setRange(0, 8)
        self.sp_curvas_smooth.setValue(2)
        self.sp_curvas_smooth.setToolTip(
            "Iteraciones del algoritmo de suavizado Chaikin.\n"
            "0 = sin suavizar (escalones del píxel visibles)\n"
            "1-2 = suave (recomendado)\n"
            "3-4 = muy suave (puede alejarse del terreno real)\n"
            "Cada iteración duplica el número de vértices.")
        g.addWidget(self.sp_curvas_smooth, 2, 1)

        g.addWidget(QLabel(s['lbl_curvas_min_longitud']), 3, 0)
        self.sp_curvas_min_longitud = QDoubleSpinBox()
        self.sp_curvas_min_longitud.setRange(0.0, 10000.0)
        self.sp_curvas_min_longitud.setValue(30.0)
        self.sp_curvas_min_longitud.setDecimals(1)
        self.sp_curvas_min_longitud.setSuffix(" m")
        self.sp_curvas_min_longitud.setToolTip(
            "Longitud mínima de una curva para ser exportada.\n"
            "Las curvas (abiertas o cerradas) más cortas se descartan,\n"
            "evitando minicurvas antiestéticas en zonas planas o bordes.\n"
            "0 = exportar todas sin filtro.")
        g.addWidget(self.sp_curvas_min_longitud, 3, 1)

        # ── Reducción de vértices (Douglas-Peucker) ──────────────────────
        # GDAL ContourGenerate saca prácticamente un vértice por cada celda
        # del ráster que cruza la curva, lo que multiplica el peso del DXF
        # frente a programas como Global Mapper (que aplican su propia
        # reducción de vértices por defecto). Esta opción simplifica los
        # tramos rectos ANTES del suavizado Chaikin, sin alterar la forma
        # de la curva más allá de la tolerancia indicada.
        self.chk_curvas_simplify = QCheckBox(s['chk_curvas_simplify'])
        self.chk_curvas_simplify.setChecked(True)
        self.chk_curvas_simplify.setToolTip(s['chk_curvas_simplify_tooltip'])
        self.chk_curvas_simplify.toggled.connect(self._toggle_curvas_simplify)
        g.addWidget(self.chk_curvas_simplify, 4, 0, 1, 2)

        self.lbl_curvas_simplify_tol = QLabel(s['lbl_curvas_simplify_tol'])
        g.addWidget(self.lbl_curvas_simplify_tol, 5, 0)
        self.sp_curvas_simplify_tol = QDoubleSpinBox()
        self.sp_curvas_simplify_tol.setRange(0.01, 100.0)
        self.sp_curvas_simplify_tol.setValue(0.25)
        self.sp_curvas_simplify_tol.setDecimals(2)
        self.sp_curvas_simplify_tol.setSingleStep(0.05)
        self.sp_curvas_simplify_tol.setSuffix(" m")
        self.sp_curvas_simplify_tol.setToolTip(s['sp_curvas_simplify_tol_tooltip'])
        g.addWidget(self.sp_curvas_simplify_tol, 5, 1)

        lbl_buf_req = QLabel(s['lbl_buf_req'])
        lbl_buf_req.setObjectName("lbl_warn")
        lbl_buf_req.setWordWrap(True)
        g.addWidget(lbl_buf_req, 6, 0, 1, 2)

        lbl_out = QLabel(s['lbl_curvas_out'])
        lbl_out.setObjectName("lbl_info")
        lbl_out.setWordWrap(True)
        g.addWidget(lbl_out, 7, 0, 1, 2)

        layout.addWidget(self.grp_curvas)
        layout.addStretch()
        return w

    # ─────────────────────────────────────────────────────────────────────────
    #  Toggle slots
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_longitudinal_group(self, checked):
        self.grp_longitudinal.setEnabled(checked)

    def _toggle_transversales_group(self, checked):
        self.grp_trans.setEnabled(checked)

    def _toggle_mdt_buffer_group(self, checked):
        self.grp_mdt_buf.setEnabled(checked)

    def _toggle_curvas_group(self, checked):
        self.grp_curvas.setEnabled(checked)

    def _toggle_curvas_simplify(self, checked):
        self.lbl_curvas_simplify_tol.setEnabled(checked)
        self.sp_curvas_simplify_tol.setEnabled(checked)

    def _toggle_trans_cplane(self, auto_checked):
        self.sp_trans_cplane.setEnabled(not auto_checked)
        if not auto_checked:
            self.sp_trans_cplane.setFocus()

    def _toggle_cplane(self, auto_checked):
        self.sp_cplane.setEnabled(not auto_checked)

        if not auto_checked:
            self.sp_cplane.setFocus()

    def _toggle_equidistant(self, use_eq):
        self.sp_equidistant.setEnabled(use_eq)

        if use_eq:
            self.sp_equidistant.setFocus()

    def _toggle_theme(self):
        self._theme = 'light' if self._theme == 'dark' else 'dark'
        self.setStyleSheet(_build_stylesheet(self._theme))
        self._settings.setValue("PerfilLongitudinalMDT/theme", self._theme)
        self._update_theme_button()

    def _update_theme_button(self):
        if self._theme == 'dark':
            if self._lang == 'es':
                self.btn_theme.setText("☀️  Modo claro")
                self.btn_theme.setToolTip("Cambiar a modo claro (fondos claros, textos oscuros)")
            else:
                self.btn_theme.setText("☀️  Light mode")
                self.btn_theme.setToolTip("Switch to light mode (light background, dark text)")
        else:
            if self._lang == 'es':
                self.btn_theme.setText("🌙  Modo oscuro")
                self.btn_theme.setToolTip("Cambiar a modo oscuro (fondos oscuros, textos claros)")
            else:
                self.btn_theme.setText("🌙  Dark mode")
                self.btn_theme.setToolTip("Switch to dark mode (dark background, light text)")

    # ─────────────────────────────────────────────────────────────────────────
    #  Idioma
    # ─────────────────────────────────────────────────────────────────────────

    # Widgets de entrada cuyo valor se conserva al cambiar de idioma
    # (el toggle reconstruye la interfaz entera desde cero, así que hace
    # falta guardar y restaurar el estado a mano). tipo: 'text' (QLineEdit),
    # 'check' (QCheckBox/QRadioButton), 'value' (QSpinBox/QDoubleSpinBox),
    # 'combo' (QComboBox, por índice).
    _STATE_WIDGETS = [
        ('_rdo_mdt_folder', 'check'), ('_rdo_mdt_layer', 'check'),
        ('le_folder', 'text'), ('_cmb_mdt_layer', 'combo'),
        ('chk_rescan', 'check'),
        ('_rdo_eje_file', 'check'), ('_rdo_eje_layer', 'check'),
        ('le_axis', 'text'), ('_cmb_eje_layer', 'combo'),
        ('le_outdir', 'text'),
        ('chk_gen_longitudinal', 'check'),
        ('sp_interval', 'value'), ('sp_hscale', 'value'), ('sp_vscale', 'value'),
        ('chk_text_vertical', 'check'),
        ('chk_use_equidistant', 'check'), ('sp_equidistant', 'value'),
        ('chk_cplane_auto', 'check'), ('sp_cplane', 'value'),
        ('sp_eje3d_equidistancia', 'value'),
        ('chk_gen_eje3d_eq', 'check'),
        ('chk_gen_transversales', 'check'),
        ('sp_trans_spacing', 'value'), ('sp_trans_left', 'value'),
        ('sp_trans_right', 'value'), ('sp_trans_step', 'value'),
        ('sp_trans_hscale', 'value'), ('sp_trans_vscale', 'value'),
        ('chk_trans_cplane_auto', 'check'), ('sp_trans_cplane', 'value'),
        ('sp_trans_guitarra_eq', 'value'),
        ('chk_gen_mdt_buffer', 'check'), ('sp_mdt_buffer', 'value'),
        ('chk_gen_curvas', 'check'), ('sp_curvas_eq', 'value'),
        ('sp_curvas_maestra', 'value'), ('sp_curvas_smooth', 'value'),
        ('sp_curvas_min_longitud', 'value'),
        ('chk_curvas_simplify', 'check'), ('sp_curvas_simplify_tol', 'value'),
    ]

    def _snapshot_state(self):
        snap = {}
        for name, kind in self._STATE_WIDGETS:
            w = getattr(self, name, None)
            if w is None:
                continue
            if kind == 'text':
                snap[name] = w.text()
            elif kind == 'check':
                snap[name] = w.isChecked()
            elif kind == 'value':
                snap[name] = w.value()
            elif kind == 'combo':
                snap[name] = w.currentIndex()
        snap['_tab_index'] = getattr(self, 'tabs', None) and self.tabs.currentIndex()
        return snap

    def _restore_state(self, snap):
        for name, kind in self._STATE_WIDGETS:
            w = getattr(self, name, None)
            if w is None or name not in snap:
                continue
            value = snap[name]
            if kind == 'text':
                w.setText(value)
            elif kind == 'check':
                w.setChecked(value)
            elif kind == 'value':
                w.setValue(value)
            elif kind == 'combo':
                if 0 <= value < w.count():
                    w.setCurrentIndex(value)
        tab_index = snap.get('_tab_index')
        if tab_index is not None and hasattr(self, 'tabs'):
            self.tabs.setCurrentIndex(tab_index)

    def _toggle_lang(self):
        self._lang = 'en' if self._lang == 'es' else 'es'
        self._settings.setValue("PerfilLongitudinalMDT/lang", self._lang)
        self.strings = _STRINGS[self._lang]

        snap = self._snapshot_state()

        # Vacía el layout actual reasignándolo a un widget "de usar y tirar"
        # que Qt destruirá junto con todos sus hijos; así _build_ui() puede
        # crear un QVBoxLayout(self) nuevo sin chocar con el anterior.
        old_layout = self.layout()
        if old_layout is not None:
            QWidget().setLayout(old_layout)

        self.setWindowTitle(self.strings['window_title'])
        self._build_ui()
        self._restore_state(snap)

    def _update_lang_button(self):
        self.btn_lang.setText(f"🌐  {self.strings['btn_lang']}")
        self.btn_lang.setToolTip(self.strings['btn_lang_tooltip'])

    # ─────────────────────────────────────────────────────────────────────────
    #  Exploradores
    # ─────────────────────────────────────────────────────────────────────────

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, self.strings['dlg_select_mdt_folder'])
        if path:
            self.le_folder.setText(path)

    def _browse_axis(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.strings['dlg_select_axis_file'], "", AXIS_FORMATS)
        if path:
            self.le_axis.setText(path)

    def _browse_outdir(self):
        path = QFileDialog.getExistingDirectory(self, self.strings['dlg_select_outdir'])
        if path:
            self.le_outdir.setText(path)

    # ─────────────────────────────────────────────────────────────────────────
    #  Capas cargadas en QGIS
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_mdt_mode(self, btn_id, checked):
        """Alterna entre modo carpeta y capa cargada para el MDT."""
        if not checked:
            return
        use_layer = (btn_id == 1)
        self.le_folder.setVisible(not use_layer)
        self._btn_browse_folder.setVisible(not use_layer)
        self._cmb_mdt_layer.setVisible(use_layer)
        self._btn_refresh_mdt.setVisible(use_layer)
        # La caché no aplica cuando se usa una capa ya cargada
        self.chk_rescan.setEnabled(not use_layer)

    def _toggle_eje_mode(self, btn_id, checked):
        """Alterna entre modo archivo y capa cargada para el eje."""
        if not checked:
            return
        use_layer = (btn_id == 1)
        self.le_axis.setVisible(not use_layer)
        self._btn_browse_axis.setVisible(not use_layer)
        self._cmb_eje_layer.setVisible(use_layer)
        self._btn_refresh_eje.setVisible(use_layer)

    def _refresh_mdt_layers(self):
        """Rellena el combo con las capas ráster cargadas en el proyecto QGIS."""
        try:
            from qgis.core import QgsProject, QgsMapLayer
        except ImportError:
            return
        self._cmb_mdt_layer.clear()
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if layer.type() == QgsMapLayer.RasterLayer:
                source = layer.source().split("|")[0]
                self._cmb_mdt_layer.addItem(layer.name(), source)
        if self._cmb_mdt_layer.count() == 0:
            self._cmb_mdt_layer.addItem(self.strings['no_raster_layers'], "")

    def _refresh_eje_layers(self):
        """Rellena el combo con las capas vectoriales lineales cargadas en QGIS."""
        try:
            from qgis.core import QgsProject, QgsMapLayer, QgsWkbTypes
        except ImportError:
            return
        self._cmb_eje_layer.clear()
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer:
                geom_type = layer.geometryType()
                # 1 = Line geometry type in QGIS
                if geom_type == QgsWkbTypes.LineGeometry:
                    source = layer.source().split("|")[0]
                    self._cmb_eje_layer.addItem(layer.name(), source)
        if self._cmb_eje_layer.count() == 0:
            self._cmb_eje_layer.addItem(self.strings['no_line_layers'], "")

    def _get_mdt_folder(self):
        """Devuelve la carpeta MDT según el modo seleccionado."""
        if self._rdo_mdt_layer.isChecked():
            # Cuando la fuente es una capa, devolvemos la carpeta que la contiene
            source = self._cmb_mdt_layer.currentData() or ""
            if source:
                return os.path.dirname(source)
            return ""
        return self.le_folder.text().strip()

    def _get_axis_path(self):
        """Devuelve la ruta del eje según el modo seleccionado."""
        if self._rdo_eje_layer.isChecked():
            return self._cmb_eje_layer.currentData() or ""
        return self.le_axis.text().strip()

    # ─────────────────────────────────────────────────────────────────────────
    #  Validación
    # ─────────────────────────────────────────────────────────────────────────

    def _validate(self):
        s = self.strings
        folder = self._get_mdt_folder()
        axis = self._get_axis_path()
        outdir = self.le_outdir.text().strip()

        # Validación MDT
        if self._rdo_mdt_layer.isChecked():
            mdt_source = self._cmb_mdt_layer.currentData() or ""
            if not mdt_source:
                QMessageBox.warning(self, s['warn_missing_title'], s['warn_no_raster_layer'])
                return False
        else:
            if not folder:
                QMessageBox.warning(self, s['warn_missing_title'], s['warn_no_folder'])
                return False
            if not os.path.isdir(folder):
                QMessageBox.warning(self, s['warn_invalid_folder_title'],
                                    s['warn_folder_not_exist'].format(path=folder))
                return False

        # Validación eje
        if self._rdo_eje_layer.isChecked():
            eje_source = self._cmb_eje_layer.currentData() or ""
            if not eje_source:
                QMessageBox.warning(self, s['warn_missing_title'], s['warn_no_line_layer'])
                return False
        else:
            if not axis:
                QMessageBox.warning(self, s['warn_missing_title'], s['warn_no_axis'])
                return False
            if not os.path.isfile(axis):
                QMessageBox.warning(self, s['warn_invalid_file_title'],
                                    s['warn_axis_not_exist'].format(path=axis))
                return False
        if not outdir:
            QMessageBox.warning(self, s['warn_missing_title'], s['warn_no_outdir'])
            return False
        if not os.path.isdir(outdir):
            try:
                os.makedirs(outdir, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, s['warn_invalid_folder_title'],
                                    s['warn_cannot_create_outdir'].format(err=e))
                return False

        # Validar que al menos una opción está activa
        if not any([
            self.chk_gen_longitudinal.isChecked(),
            self.chk_gen_transversales.isChecked(),
            self.chk_gen_mdt_buffer.isChecked(),
            self.chk_gen_curvas.isChecked(),
        ]):
            QMessageBox.warning(self, s['warn_nothing_selected_title'], s['warn_nothing_selected'])
            return False

        # Curvas requieren buffer (se genera automáticamente si no está activado)
        if self.chk_gen_curvas.isChecked() and not self.chk_gen_mdt_buffer.isChecked():
            reply = QMessageBox.question(
                self,
                s['ask_curvas_no_buffer_title'],
                s['ask_curvas_no_buffer'],
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return False

        return True

    # ─────────────────────────────────────────────────────────────────────────
    #  Ejecutar
    # ─────────────────────────────────────────────────────────────────────────

    def _release_locked_outputs(self, output_dir):
        """
        En Windows, GDAL no puede sobrescribir un GeoTIFF (u otro fichero)
        que ya esté abierto como capa en el proyecto QGIS: el archivo queda
        bloqueado por el propio QGIS y la exportación falla con
        "Permission denied", aunque la carpeta de salida tenga permisos de
        escritura normales (es lo que le pasaba a perfiles anteriores que
        revisaban el mdt_buffer.tif en el lienzo y luego volvían a generar).

        Para evitarlo, antes de lanzar el worker (en el hilo principal,
        donde es seguro tocar QgsProject) descargamos del proyecto
        cualquier capa cuya fuente apunte dentro de la carpeta de salida.
        """
        if not output_dir:
            return
        try:
            from qgis.core import QgsProject
        except ImportError:
            return

        output_dir_norm = os.path.normcase(os.path.normpath(output_dir))
        project = QgsProject.instance()
        to_remove = []
        for layer_id, layer in project.mapLayers().items():
            try:
                source = layer.source().split('|')[0]
                source_norm = os.path.normcase(os.path.normpath(source))
            except Exception:
                continue
            if source_norm == output_dir_norm or source_norm.startswith(
                output_dir_norm + os.sep
            ):
                to_remove.append(layer_id)

        if to_remove:
            project.removeMapLayers(to_remove)

    def _run(self):
        s = self.strings
        if not self._validate():
            return

        self.btn_run.setEnabled(False)
        self.progress_bar.setValue(0)
        self._result = None

        cp = None if self.chk_cplane_auto.isChecked() else self.sp_cplane.value()
        outdir = self.le_outdir.text().strip()
        axis_path = self._get_axis_path()

        n_profiles = _count_profiles_in_file(axis_path)
        profile_base = _next_profile_name(outdir)

        if n_profiles > 1:
            self.lbl_status.setText(s['status_n_geometries'].format(n=n_profiles))

        params = {
            # Entrada
            'folder': self._get_mdt_folder(),
            'axis_path': axis_path,
            'output_dir': outdir,
            'profile_base': profile_base,
            'force_rescan': self.chk_rescan.isChecked(),

            # Longitudinal
            'gen_longitudinal': self.chk_gen_longitudinal.isChecked(),
            'interval': self.sp_interval.value(),
            'h_scale': self.sp_hscale.value(),
            'v_scale': self.sp_vscale.value(),
            'comparison_plane': cp,
            'text_vertical': self.chk_text_vertical.isChecked(),
            'use_equidistant': self.chk_use_equidistant.isChecked(),
            'equidistant_interval': self.sp_equidistant.value(),

            # Eje 3D equidistante adicional
            'gen_eje3d_equidistante': self.chk_gen_eje3d_eq.isChecked(),
            'eje3d_equidistancia': self.sp_eje3d_equidistancia.value(),

            # Transversales
            'gen_transversales': self.chk_gen_transversales.isChecked(),
            'trans_spacing': self.sp_trans_spacing.value(),
            'trans_dist_left': self.sp_trans_left.value(),
            'trans_dist_right': self.sp_trans_right.value(),
            'trans_sample_step': self.sp_trans_step.value(),
            'trans_h_scale': self.sp_trans_hscale.value(),
            'trans_v_scale': self.sp_trans_vscale.value(),
            'trans_guitarra_interval': self.sp_trans_guitarra_eq.value(),

            # Buffer MDT
            'gen_mdt_buffer': self.chk_gen_mdt_buffer.isChecked(),
            'mdt_buffer_m': self.sp_mdt_buffer.value(),

            # Plano de comparación transversales (None = relativo por sección)
            'trans_comparison_plane': (
                None if self.chk_trans_cplane_auto.isChecked()
                else self.sp_trans_cplane.value()
            ),

            # Curvas de nivel
            'gen_curvas': self.chk_gen_curvas.isChecked(),
            'curvas_equidistancia': self.sp_curvas_eq.value(),
            'curvas_maestra': self.sp_curvas_maestra.value(),
            'curvas_smooth': self.sp_curvas_smooth.value(),
            'curvas_min_longitud': self.sp_curvas_min_longitud.value(),
            'curvas_simplify': self.chk_curvas_simplify.isChecked(),
            'curvas_simplify_tolerance': self.sp_curvas_simplify_tol.value(),
        }

        self._release_locked_outputs(outdir)

        self.worker = ProfileWorker(params)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    # ─────────────────────────────────────────────────────────────────────────
    #  Slots worker
    # ─────────────────────────────────────────────────────────────────────────

    def _on_progress(self, pct, msg):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(msg)

    def _on_finished(self, result):
        s = self.strings
        self._result = result
        self.progress_bar.setValue(100)

        outdir = result['output_dir']
        n_axes = result.get('n_axes', 1)
        cache_txt = s['cache_hit'] if result['from_cache'] else s['cache_miss']
        cp_txt = f"{result['comp_plane_final']:.2f} m"

        mdt_buffer_error = result.get('mdt_buffer_error')
        curvas_error = result.get('curvas_error')
        had_partial_error = bool(mdt_buffer_error or curvas_error)

        status_key = 'status_done_warn' if had_partial_error else 'status_done_ok'
        self.lbl_status.setText(s[status_key].format(n=n_axes, cp=cp_txt, cache=cache_txt))
        self.btn_run.setEnabled(True)

        if self.chk_cplane_auto.isChecked():
            self.sp_cplane.setValue(result['comp_plane_final'])

        all_res = result.get('all_results', [])
        lines = []

        if mdt_buffer_error:
            lines.append(s['result_mdt_buffer_error'].format(err=mdt_buffer_error))
        if curvas_error:
            lines.append(s['result_curvas_error'].format(err=curvas_error))
        if mdt_buffer_error or curvas_error:
            lines.append("")

        lines.append(f"{outdir}")
        lines.append("")

        for r in all_res:
            lbl = r['label']
            lines.append(f"  {lbl}.dxf  /  {lbl}.csv")
            trans_path = os.path.join(outdir, f"{lbl}_transversales.dxf")
            if os.path.exists(trans_path):
                lines.append(f"  {lbl}_transversales.dxf")

        lines.append("  perfiles_ejes3d.dxf")
        if result.get('output_dxf3d_eq'):
            lines.append(f"  {os.path.basename(result['output_dxf3d_eq'])}")
        if result.get('output_mdt_buffer'):
            lines.append("  mdt_buffer.tif")
        if result.get('output_curvas'):
            lines.append("  curvas_nivel.dxf")

        title = s['result_title_warn'] if had_partial_error else s['result_title_ok']
        if had_partial_error:
            QMessageBox.warning(self, title, "\n".join(lines))
        else:
            QMessageBox.information(self, title, "\n".join(lines))

    def _on_error(self, msg):
        s = self.strings
        self.progress_bar.setValue(0)
        self.lbl_status.setText(s['status_error'])
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, s['error_title'], msg)

    # ─────────────────────────────────────────────────────────────────────────
    #  Donativo
    # ─────────────────────────────────────────────────────────────────────────

    def _open_donate(self):
        url = QUrl("https://www.paypal.com/donate/?hosted_button_id=UF9SYUY42GWTG")
        QDesktopServices.openUrl(url)
