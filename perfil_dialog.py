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
import traceback

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
    QSpinBox, QGroupBox, QProgressBar,
    QFileDialog, QCheckBox, QMessageBox, QTabWidget, QWidget,
    QFrame,
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
                try:
                    from .mdt_export import export_mdt_buffer, export_curvas_nivel

                    geotiff_src = output_mdt_buffer
                    if not geotiff_src or not os.path.exists(geotiff_src):
                        buf_curvas = p.get('mdt_buffer_m', 100.0)
                        geotiff_src = os.path.join(output_dir, "mdt_buffer_curvas.tif")
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
                        progress_callback=_curvas_p,
                    )
                except Exception as e_c:
                    curvas_error = f"{type(e_c).__name__}: {e_c}"
                    self.progress.emit(98, f"⚠ Error curvas: {curvas_error}")
                    output_curvas = None

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
        self.setWindowTitle("Perfil Longitudinal MDT")
        self.setMinimumWidth(680)
        self.setMinimumHeight(640)
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

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────────
    #  UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(8)
        main.setContentsMargins(12, 12, 12, 12)

        # ── Estilo: tema claro/oscuro con colores explícitos (ver botón 🌙/☀️) ──
        self.setStyleSheet(_build_stylesheet(self._theme))

        # ── Cabecera ──────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        title = QLabel("🗻  Perfil Longitudinal MDT")
        title.setObjectName("lbl_title")
        header_row.addWidget(title)
        header_row.addStretch()

        self.btn_theme = QPushButton()
        self.btn_theme.setObjectName("btn_theme")
        self.btn_theme.clicked.connect(self._toggle_theme)
        header_row.addWidget(self.btn_theme)
        main.addLayout(header_row)

        sub = QLabel(
            "Perfil longitudinal · Transversales · MDT buffer · Curvas de nivel"
        )
        sub.setObjectName("lbl_info")
        main.addWidget(sub)

        # ── 1. Datos de entrada (siempre visibles) ────────────────────────
        grp1 = QGroupBox("1. Datos de entrada")
        g1 = QGridLayout(grp1)
        g1.setSpacing(6)

        g1.addWidget(QLabel("Carpeta MDTs:"), 0, 0)
        self.le_folder = QLineEdit()
        self.le_folder.setPlaceholderText("Carpeta con los MDTs (GeoTIFF, ASC, IMG, BIL, FLT, DEM, HGT)")
        g1.addWidget(self.le_folder, 0, 1)
        b = QPushButton("…")
        b.setMaximumWidth(32)
        b.clicked.connect(self._browse_folder)
        g1.addWidget(b, 0, 2)

        g1.addWidget(QLabel("Eje (vectorial):"), 1, 0)
        self.le_axis = QLineEdit()
        self.le_axis.setPlaceholderText("DXF, SHP, KML/KMZ, GeoPackage, GML, GPX, GeoJSON")
        g1.addWidget(self.le_axis, 1, 1)
        b2 = QPushButton("…")
        b2.setMaximumWidth(32)
        b2.clicked.connect(self._browse_axis)
        g1.addWidget(b2, 1, 2)

        self.chk_rescan = QCheckBox("Forzar re-escaneo de MDTs (ignorar caché)")
        g1.addWidget(self.chk_rescan, 2, 0, 1, 3)

        g1.addWidget(QLabel("Carpeta de salida:"), 3, 0)
        self.le_outdir = QLineEdit()
        self.le_outdir.setPlaceholderText("Carpeta donde se guardarán los archivos generados")
        g1.addWidget(self.le_outdir, 3, 1)
        b3 = QPushButton("…")
        b3.setMaximumWidth(32)
        b3.clicked.connect(self._browse_outdir)
        g1.addWidget(b3, 3, 2)

        main.addWidget(grp1)

        # ── Pestañas ──────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tab_longitudinal(), "📈 Longitudinal")
        self.tabs.addTab(self._build_tab_transversales(), "📐 Transversales")
        self.tabs.addTab(self._build_tab_mdt_buffer(), "🗺 Buffer MDT")
        self.tabs.addTab(self._build_tab_curvas(), "〰 Curvas de nivel")

        main.addWidget(self.tabs)

        # ── Progreso ──────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        main.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Listo.")
        self.lbl_status.setObjectName("lbl_info")
        main.addWidget(self.lbl_status)

        # ── Botones ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self.btn_run = QPushButton("▶  Generar")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._run)
        btn_row.addWidget(self.btn_run)

        btn_row.addStretch()

        btn_donate = QPushButton("☕  Invítame a un café")
        btn_donate.setObjectName("btn_donate")
        btn_donate.clicked.connect(self._open_donate)
        btn_row.addWidget(btn_donate)

        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("btn_close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)

        main.addLayout(btn_row)

        self._update_theme_button()

    # ── PESTAÑA 1: Longitudinal ───────────────────────────────────────────

    def _build_tab_longitudinal(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Activar longitudinal
        self.chk_gen_longitudinal = QCheckBox("✅  Generar perfil longitudinal")
        self.chk_gen_longitudinal.setChecked(True)
        self.chk_gen_longitudinal.setStyleSheet("font-weight:bold;")
        self.chk_gen_longitudinal.toggled.connect(self._toggle_longitudinal_group)
        layout.addWidget(self.chk_gen_longitudinal)

        self.grp_longitudinal = QGroupBox("Parámetros del perfil longitudinal")

        g = QGridLayout(self.grp_longitudinal)
        g.setSpacing(6)

        g.addWidget(QLabel("Intervalo segmentación:"), 0, 0)
        self.sp_interval = QDoubleSpinBox()
        self.sp_interval.setRange(0.1, 100.0)
        self.sp_interval.setValue(1.0)
        self.sp_interval.setSingleStep(0.5)
        self.sp_interval.setSuffix(" m")
        g.addWidget(self.sp_interval, 0, 1)

        g.addWidget(QLabel("Escala horizontal  1:"), 1, 0)
        self.sp_hscale = QSpinBox()
        self.sp_hscale.setRange(50, 50000)
        self.sp_hscale.setValue(1000)
        self.sp_hscale.setSingleStep(500)
        g.addWidget(self.sp_hscale, 1, 1)

        g.addWidget(QLabel("Escala vertical      1:"), 2, 0)
        self.sp_vscale = QSpinBox()
        self.sp_vscale.setRange(10, 5000)
        self.sp_vscale.setValue(100)
        self.sp_vscale.setSingleStep(50)
        g.addWidget(self.sp_vscale, 2, 1)

        g.addWidget(QLabel("Textos guitarra:"), 3, 0)
        self.chk_text_vertical = QCheckBox("Vertical (90°)")
        self.chk_text_vertical.setChecked(True)
        g.addWidget(self.chk_text_vertical, 3, 1)

        g.addWidget(QLabel("Datos guitarra:"), 4, 0)
        eq_row = QHBoxLayout()
        self.chk_use_equidistant = QCheckBox("Mostrar a equidistancia")
        self.chk_use_equidistant.toggled.connect(self._toggle_equidistant)
        eq_row.addWidget(self.chk_use_equidistant)
        self.sp_equidistant = QDoubleSpinBox()
        self.sp_equidistant.setRange(1.0, 10000.0)
        self.sp_equidistant.setValue(100.0)
        self.sp_equidistant.setDecimals(1)
        self.sp_equidistant.setSuffix(" m")
        self.sp_equidistant.setEnabled(False)
        eq_row.addWidget(QLabel("Intervalo:"))
        eq_row.addWidget(self.sp_equidistant)
        eq_row.addStretch()
        g.addLayout(eq_row, 4, 1)

        g.addWidget(QLabel("Plano comparación:"), 5, 0)
        cp_row = QHBoxLayout()
        self.chk_cplane_auto = QCheckBox("Automático")
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

        lbl_cp = QLabel("ℹ  Automático: múltiplo de 5 por debajo del mínimo del terreno − 5 m")
        lbl_cp.setObjectName("lbl_info")
        lbl_cp.setWordWrap(True)
        g.addWidget(lbl_cp, 6, 0, 1, 2)

        # ── Eje 3D equidistante ───────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        g.addWidget(sep, 7, 0, 1, 2)

        eq3d_row = QHBoxLayout()
        eq3d_row.addWidget(QLabel("Marcas PK (equidistancia):"))
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

        self.chk_gen_eje3d_eq = QCheckBox("Generar también eje 3D limpio (sin marcas ni texto)")
        self.chk_gen_eje3d_eq.setToolTip(
            "DXF adicional con la polilínea 3D planchada sobre el MDT,\n"
            "con un vértice cada intervalo de segmentación. Sin texto ni marcas.")
        g.addWidget(self.chk_gen_eje3d_eq, 9, 0, 1, 2)

        layout.addWidget(self.grp_longitudinal)
        layout.addStretch()
        return w

    # ── PESTAÑA 2: Transversales ──────────────────────────────────────────

    def _build_tab_transversales(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chk_gen_transversales = QCheckBox("✅  Generar perfiles transversales")
        self.chk_gen_transversales.setChecked(False)
        self.chk_gen_transversales.setStyleSheet("font-weight:bold;")
        self.chk_gen_transversales.toggled.connect(self._toggle_transversales_group)
        layout.addWidget(self.chk_gen_transversales)

        self.grp_trans = QGroupBox("Parámetros de transversales")

        self.grp_trans.setEnabled(False)
        g = QGridLayout(self.grp_trans)
        g.setSpacing(6)

        g.addWidget(QLabel("Distancia entre transversales:"), 0, 0)
        self.sp_trans_spacing = QDoubleSpinBox()
        self.sp_trans_spacing.setRange(1.0, 10000.0)
        self.sp_trans_spacing.setValue(20.0)
        self.sp_trans_spacing.setDecimals(1)
        self.sp_trans_spacing.setSuffix(" m")
        self.sp_trans_spacing.setToolTip("Distancia entre secciones transversales a lo largo del eje.")
        g.addWidget(self.sp_trans_spacing, 0, 1)

        g.addWidget(QLabel("Ancho a izquierda:"), 1, 0)
        self.sp_trans_left = QDoubleSpinBox()
        self.sp_trans_left.setRange(1.0, 5000.0)
        self.sp_trans_left.setValue(10.0)
        self.sp_trans_left.setDecimals(1)
        self.sp_trans_left.setSuffix(" m")
        self.sp_trans_left.setToolTip("Metros a muestrear a la izquierda del eje.")
        g.addWidget(self.sp_trans_left, 1, 1)

        g.addWidget(QLabel("Ancho a derecha:"), 2, 0)
        self.sp_trans_right = QDoubleSpinBox()
        self.sp_trans_right.setRange(1.0, 5000.0)
        self.sp_trans_right.setValue(10.0)
        self.sp_trans_right.setDecimals(1)
        self.sp_trans_right.setSuffix(" m")
        self.sp_trans_right.setToolTip("Metros a muestrear a la derecha del eje. Puede ser distinto al de izquierda.")
        g.addWidget(self.sp_trans_right, 2, 1)

        g.addWidget(QLabel("Paso muestreo transversal:"), 3, 0)
        self.sp_trans_step = QDoubleSpinBox()
        self.sp_trans_step.setRange(0.1, 100.0)
        self.sp_trans_step.setValue(1.0)
        self.sp_trans_step.setDecimals(2)
        self.sp_trans_step.setSuffix(" m")
        self.sp_trans_step.setToolTip("Resolución del muestreo perpendicular al eje.")
        g.addWidget(self.sp_trans_step, 3, 1)

        sep = QLabel("── Escalas del DXF de transversales ──────────────────────")

        g.addWidget(sep, 4, 0, 1, 2)

        g.addWidget(QLabel("Escala horizontal  1:"), 5, 0)
        self.sp_trans_hscale = QSpinBox()
        self.sp_trans_hscale.setRange(50, 10000)
        self.sp_trans_hscale.setValue(500)
        self.sp_trans_hscale.setSingleStep(100)
        g.addWidget(self.sp_trans_hscale, 5, 1)

        g.addWidget(QLabel("Escala vertical      1:"), 6, 0)
        self.sp_trans_vscale = QSpinBox()
        self.sp_trans_vscale.setRange(10, 2000)
        self.sp_trans_vscale.setValue(100)
        self.sp_trans_vscale.setSingleStep(50)
        g.addWidget(self.sp_trans_vscale, 6, 1)

        lbl_info = QLabel(
            "Salida: <perfil>_transversales.dxf — cuadrícula de secciones con\n"
            "terreno, eje, PK, plano de comparación y tabla de cotas."
        )
        lbl_info.setObjectName("lbl_info")
        lbl_info.setWordWrap(True)
        g.addWidget(lbl_info, 7, 0, 1, 2)

        sep2 = QLabel("── Plano de comparación ──────────────────────────────────")
        g.addWidget(sep2, 8, 0, 1, 2)

        g.addWidget(QLabel("Plano por sección:"), 9, 0)
        trans_cp_row = QHBoxLayout()
        self.chk_trans_cplane_auto = QCheckBox("Relativo (0.5 m bajo el mínimo de cada sección)")
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

        sep3 = QLabel("── Mini-guitarra de cada transversal ─────────────────────")
        g.addWidget(sep3, 10, 0, 1, 2)

        g.addWidget(QLabel("Equidistancia guitarra:"), 11, 0)
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
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chk_gen_mdt_buffer = QCheckBox("✅  Exportar MDT con buffer (GeoTIFF)")
        self.chk_gen_mdt_buffer.setChecked(False)
        self.chk_gen_mdt_buffer.setStyleSheet("font-weight:bold;")
        self.chk_gen_mdt_buffer.toggled.connect(self._toggle_mdt_buffer_group)
        layout.addWidget(self.chk_gen_mdt_buffer)

        self.grp_mdt_buf = QGroupBox("Parámetros del buffer MDT")

        self.grp_mdt_buf.setEnabled(False)
        g = QGridLayout(self.grp_mdt_buf)
        g.setSpacing(6)

        g.addWidget(QLabel("Buffer (todas las direcciones):"), 0, 0)
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

        lbl_buf = QLabel(
            "GeoTIFF recortado al bounding box del eje + buffer,\n"
            "fusionando todas las teselas MDT en un único ráster comprimido (LZW)."
        )
        lbl_buf.setObjectName("lbl_info")
        lbl_buf.setWordWrap(True)
        g.addWidget(lbl_buf, 1, 0, 1, 2)

        layout.addWidget(self.grp_mdt_buf)
        layout.addStretch()
        return w

    # ── PESTAÑA 4: Curvas de nivel ────────────────────────────────────────

    def _build_tab_curvas(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chk_gen_curvas = QCheckBox("✅  Generar curvas de nivel (DXF)")
        self.chk_gen_curvas.setChecked(False)
        self.chk_gen_curvas.setStyleSheet("font-weight:bold;")
        self.chk_gen_curvas.toggled.connect(self._toggle_curvas_group)
        layout.addWidget(self.chk_gen_curvas)

        self.grp_curvas = QGroupBox("Parámetros de curvas de nivel")

        self.grp_curvas.setEnabled(False)
        g = QGridLayout(self.grp_curvas)
        g.setSpacing(6)

        g.addWidget(QLabel("Equidistancia curvas normales:"), 0, 0)
        self.sp_curvas_eq = QDoubleSpinBox()
        self.sp_curvas_eq.setRange(0.1, 100.0)
        self.sp_curvas_eq.setValue(1.0)
        self.sp_curvas_eq.setDecimals(2)
        self.sp_curvas_eq.setSuffix(" m")
        g.addWidget(self.sp_curvas_eq, 0, 1)

        g.addWidget(QLabel("Equidistancia curvas maestras:"), 1, 0)
        self.sp_curvas_maestra = QDoubleSpinBox()
        self.sp_curvas_maestra.setRange(0.5, 1000.0)
        self.sp_curvas_maestra.setValue(5.0)
        self.sp_curvas_maestra.setDecimals(1)
        self.sp_curvas_maestra.setSuffix(" m")
        self.sp_curvas_maestra.setToolTip(
            "Múltiplo de la equidistancia normal para curvas maestras\n"
            "(líneas de mayor grosor y con etiqueta de cota).")
        g.addWidget(self.sp_curvas_maestra, 1, 1)

        g.addWidget(QLabel("Suavizado (iteraciones Chaikin):"), 2, 0)
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

        g.addWidget(QLabel("Longitud mínima de curva (m):"), 3, 0)
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

        lbl_buf_req = QLabel(
            "⚠  Requiere MDT buffer. Si no está generado, se crea\n"
            "   automáticamente con el buffer de la pestaña Buffer MDT."
        )
        lbl_buf_req.setObjectName("lbl_warn")
        lbl_buf_req.setWordWrap(True)
        g.addWidget(lbl_buf_req, 4, 0, 1, 2)

        lbl_out = QLabel(
            "Salida: curvas_nivel.dxf — capas CURVAS_NORMALES,\n"
            "CURVAS_MAESTRAS (etiquetadas) y CURVAS_TEXTOS."
        )
        lbl_out.setObjectName("lbl_info")
        lbl_out.setWordWrap(True)
        g.addWidget(lbl_out, 5, 0, 1, 2)

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
            self.btn_theme.setText("☀️  Modo claro")
            self.btn_theme.setToolTip("Cambiar a modo claro (fondos claros, textos oscuros)")
        else:
            self.btn_theme.setText("🌙  Modo oscuro")
            self.btn_theme.setToolTip("Cambiar a modo oscuro (fondos oscuros, textos claros)")

    # ─────────────────────────────────────────────────────────────────────────
    #  Exploradores
    # ─────────────────────────────────────────────────────────────────────────

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de MDTs")
        if path:
            self.le_folder.setText(path)

    def _browse_axis(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de eje", "", AXIS_FORMATS)
        if path:
            self.le_axis.setText(path)

    def _browse_outdir(self):
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if path:
            self.le_outdir.setText(path)

    # ─────────────────────────────────────────────────────────────────────────
    #  Validación
    # ─────────────────────────────────────────────────────────────────────────

    def _validate(self):
        folder = self.le_folder.text().strip()
        axis = self.le_axis.text().strip()
        outdir = self.le_outdir.text().strip()

        if not folder:
            QMessageBox.warning(self, "Falta dato", "Especifica la carpeta de MDTs.")
            return False
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Carpeta no válida",
                                f"La carpeta de MDTs no existe:\n{folder}")
            return False
        if not axis:
            QMessageBox.warning(self, "Falta dato", "Especifica el archivo de eje.")
            return False
        if not os.path.isfile(axis):
            QMessageBox.warning(self, "Archivo no válido",
                                f"El archivo de eje no existe:\n{axis}")
            return False
        if not outdir:
            QMessageBox.warning(self, "Falta dato", "Especifica la carpeta de salida.")
            return False
        if not os.path.isdir(outdir):
            try:
                os.makedirs(outdir, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Carpeta no válida",
                                    f"No se puede crear la carpeta de salida:\n{e}")
                return False

        # Validar que al menos una opción está activa
        if not any([
            self.chk_gen_longitudinal.isChecked(),
            self.chk_gen_transversales.isChecked(),
            self.chk_gen_mdt_buffer.isChecked(),
            self.chk_gen_curvas.isChecked(),
        ]):
            QMessageBox.warning(self, "Nada seleccionado",
                                "Activa al menos una pestaña (Longitudinal, Transversales, "
                                "Buffer MDT o Curvas de nivel).")
            return False

        # Curvas requieren buffer (se genera automáticamente si no está activado)
        if self.chk_gen_curvas.isChecked() and not self.chk_gen_mdt_buffer.isChecked():
            reply = QMessageBox.question(
                self,
                "Curvas de nivel sin buffer",
                "Las curvas de nivel requieren un MDT buffer.\n\n"
                "¿Deseas generar automáticamente el MDT buffer con el valor configurado "
                "en la pestaña 'Buffer MDT'?\n\n"
                "(No se guardará como archivo separado si 'Buffer MDT' no está activo.)",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
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
        if not self._validate():
            return

        self.btn_run.setEnabled(False)
        self.progress_bar.setValue(0)
        self._result = None

        cp = None if self.chk_cplane_auto.isChecked() else self.sp_cplane.value()
        outdir = self.le_outdir.text().strip()
        axis_path = self.le_axis.text().strip()

        n_profiles = _count_profiles_in_file(axis_path)
        profile_base = _next_profile_name(outdir)

        if n_profiles > 1:
            self.lbl_status.setText(
                f"Se detectaron {n_profiles} geometrías en el eje.")

        params = {
            # Entrada
            'folder': self.le_folder.text().strip(),
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
        self._result = result
        self.progress_bar.setValue(100)

        outdir = result['output_dir']
        n_axes = result.get('n_axes', 1)
        cache_txt = "caché" if result['from_cache'] else "escaneo nuevo"
        cp_txt = f"{result['comp_plane_final']:.2f} m"

        mdt_buffer_error = result.get('mdt_buffer_error')
        curvas_error = result.get('curvas_error')
        had_partial_error = bool(mdt_buffer_error or curvas_error)

        status_icon = "⚠️ " if had_partial_error else "✅  "
        extra_txt = "  |  hubo errores, revisa el resumen" if had_partial_error else ""
        self.lbl_status.setText(
            f"{status_icon}{n_axes} perfil(es)  |  PC={cp_txt}  |  {cache_txt}{extra_txt}"
        )
        self.btn_run.setEnabled(True)

        if self.chk_cplane_auto.isChecked():
            self.sp_cplane.setValue(result['comp_plane_final'])

        all_res = result.get('all_results', [])
        lines = []

        if mdt_buffer_error:
            lines.append(f"⚠ MDT buffer: {mdt_buffer_error}")
        if curvas_error:
            lines.append(f"⚠ Curvas de nivel: {curvas_error}")
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

        title = "Completado con errores" if had_partial_error else "Proceso completado"
        if had_partial_error:
            QMessageBox.warning(self, title, "\n".join(lines))
        else:
            QMessageBox.information(self, title, "\n".join(lines))

    def _on_error(self, msg):
        self.progress_bar.setValue(0)
        self.lbl_status.setText("❌  Error durante el proceso.")
        self.btn_run.setEnabled(True)
        QMessageBox.critical(self, "Error", msg)

    # ─────────────────────────────────────────────────────────────────────────
    #  Donativo
    # ─────────────────────────────────────────────────────────────────────────

    def _open_donate(self):
        url = QUrl("https://www.paypal.com/donate/?hosted_button_id=UF9SYUY42GWTG")
        QDesktopServices.openUrl(url)
