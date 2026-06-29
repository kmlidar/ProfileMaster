# -*- coding: utf-8 -*-
"""
perfil_dxf.py  –  Exportación del perfil longitudinal a DXF R2010.

Coordenadas internas (mm de papel):
  X = dist_real / h_scale * 1000
  Y = (cota - plano_comp) / v_scale * 1000  →  plano de comp. en Y = 0
"""

import math

try:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment as _TEA
    _EZDXF_OK = True
except ImportError:
    _EZDXF_OK = False

_TXT_COTA = 2.5
_TXT_TABLA = 2.0
_TXT_PC = 2.2
_TXT_TITLE = 4.0
_TXT_GRID = 2.0

_LW_TERRAIN = 35
_LW_TABLE = 25
_LW_PLANE = 18
_LW_VERT = 9
_LW_TICK = 25


def _format_pk(dist):
    """Formatea distancia como PK estándar: 0+860, 1+150, etc."""
    if dist is None or dist < 0:
        dist = max(0.0, dist or 0.0)
    km = int(dist // 1000)
    m = dist - km * 1000
    if abs(m - round(m)) < 1e-6:
        return f"{km}+{int(round(m)):03d}"
    return f"{km}+{m:06.2f}"

_TICK_HALF = 0.8
_GRID_LBL_X = -4.0
_LABEL_X = -30.0
_OVERLAP_TOL = 1.5


def _find_qgis_python():
    """
    Devuelve la ruta al ejecutable python.exe del entorno de QGIS.
    En Windows, QGIS viene con su propio Python en apps/Python312 (o similar)
    junto al ejecutable de QGIS.  sys.executable apunta a qgis.exe, no a python.exe.
    """
    import sys
    import os
    import glob

    # 1. Si sys.executable ya es un python real, usarlo
    base = os.path.basename(sys.executable).lower()
    if 'python' in base and 'qgis' not in base:
        return sys.executable

    # 2. Buscar python.exe relativo a sys.executable (instalación típica de
    # QGIS en Windows)
    qgis_dir = os.path.dirname(sys.executable)   # …/QGIS 3.xx/bin
    parent = os.path.dirname(qgis_dir)          # …/QGIS 3.xx

    # QGIS 3.x LTR / última: apps/Python312, apps/Python311, apps/Python39 …
    for pattern in ['apps/Python3*', 'apps/python3*']:
        hits = sorted(glob.glob(os.path.join(parent, pattern)), reverse=True)
        for hit in hits:
            candidate = os.path.join(hit, 'python.exe')
            if os.path.isfile(candidate):
                return candidate

    # 3. Último recurso: python del PATH
    import shutil
    py = shutil.which('python3') or shutil.which('python')
    if py:
        return py

    raise RuntimeError(
        "No se encontró el ejecutable de Python de QGIS.\n"
        "Instala ezdxf manualmente desde OSGeo4W Shell:\n"
        "  python -m pip install ezdxf"
    )


def _ensure_ezdxf():
    """Instala ezdxf en el Python de QGIS si no está disponible."""
    global _EZDXF_OK, ezdxf, _TEA
    if _EZDXF_OK:
        return

    import subprocess
    python_exe = _find_qgis_python()

    try:
        subprocess.check_call(
            [python_exe, '-m', 'pip', 'install', 'ezdxf', '--quiet'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "No se pudo instalar ezdxf automáticamente.\n\n"
            "Instálalo manualmente abriendo la OSGeo4W Shell (como Administrador) y ejecutando:\n"
            "  python -m pip install ezdxf\n\n"
            f"(Python usado: {python_exe})\n"
            f"(Error: {e})"
        )

    # Importar ahora que está instalado
    import importlib
    _ez = importlib.import_module('ezdxf')
    from ezdxf.enums import TextEntityAlignment as _T
    ezdxf = _ez
    _TEA = _T
    _EZDXF_OK = True


def _px(d, hs):
    return d / hs * 1000.0


def _py(z, cp, vs):
    return (z - cp) / vs * 1000.0


def _add_text(msp, text, pos, align, height, layer, rotation=0.0):
    t = msp.add_text(text, dxfattribs={'height': height, 'layer': layer,
                                       'rotation': rotation})
    t.set_placement(pos, align=align)
    return t


def _table_rows(text_vertical):
    row_h = 15.0 if text_vertical else 8.0
    top = -5.0
    h1 = top - row_h      # número de vértice
    h2 = h1 - row_h       # cota
    h3 = h2 - row_h       # dist. parcial
    bot = h3 - row_h      # dist. total
    return top, h1, h2, h3, bot


def _interp_z(terrain_points, dist):
    for i, pt in enumerate(terrain_points):
        if pt[3] >= dist:
            if i == 0 or abs(pt[3] - dist) < 1e-9:
                return pt[2]
            p0 = terrain_points[i - 1]
            d0, z0, d1, z1 = p0[3], p0[2], pt[3], pt[2]
            if z0 is None or z1 is None:
                return None
            return z0 + (z1 - z0) * (dist - d0) / (d1 - d0)
    return terrain_points[-1][2] if terrain_points else None


def export_profile_dxf(
    terrain_points,
    original_indices,
    comparison_plane,
    h_scale,
    v_scale,
    output_path,
    title="Perfil Longitudinal",
    text_vertical=True,
    use_equidistant=False,
    equidistant_interval=100.0,
):
    _ensure_ezdxf()

    TABLE_TOP, TABLE_H1, TABLE_H2, TABLE_H3, TABLE_BOT = _table_rows(
        text_vertical)

    doc = ezdxf.new('R2010', setup=True)
    msp = doc.modelspace()

    # ── Linetypes — setup=True ya crea DASHED/DOT, no recrear ───────────────
    # Solo añadir los que NO existan
    lts = doc.linetypes
    existing_lts = {lt.dxf.name for lt in lts}
    if 'DOTTED' not in existing_lts:   # DOTTED no está en el estándar, usar DOT
        pass  # usaremos 'DOT' que sí existe

    # ── Capas ───────────────────────────────────────────────────────────────
    def _lay(name, color, ltype='Continuous', lw=_LW_VERT):
        lyr = doc.layers.new(
            name) if name not in doc.layers else doc.layers.get(name)
        lyr.color = color
        lyr.linetype = ltype
        lyr.dxf.lineweight = lw

    _lay('TERRENO', 3, lw=_LW_TERRAIN)
    _lay('PLANO_COMP', 4, 'DASHED', _LW_PLANE)
    _lay('REF_VERT', 8, 'DOT', _LW_VERT)
    _lay('EQUI_VERT', 8, 'DOT', _LW_VERT)
    _lay('VERTICES', 3, lw=_LW_TICK)
    _lay('COTAS', 3, lw=_LW_VERT)
    _lay('TABLA_MARCO', 7, lw=_LW_TABLE)
    _lay('TABLA_TEXTO', 7, lw=_LW_VERT)
    _lay('TITULO', 4, lw=_LW_VERT)
    _lay('GRID', 8, lw=_LW_VERT)
    _lay('MINMAX', 1, lw=_LW_VERT)

    # ── Rango de datos ──────────────────────────────────────────────────────
    x_max = _px(terrain_points[-1][3], h_scale)
    zs = [p[2] for p in terrain_points if p[2] is not None]
    z_max_v = max(zs)
    orig_pts = [terrain_points[i] for i in original_indices]

    # Offset de cota: el pie del texto debe quedar claramente por encima
    # de la línea de terreno. El texto rotado 90° tiene ancho = _TXT_COTA,
    # así que necesitamos al menos _TXT_COTA/2 de margen más el tick.
    _cota_offset = _TICK_HALF + _TXT_COTA * 2.5   # ~7 mm de papel

    # ── 1. Polilínea de terreno ─────────────────────────────────────────────
    pts = [(_px(p[3], h_scale), _py(p[2], comparison_plane, v_scale))
           for p in terrain_points if p[2] is not None]
    if pts:
        msp.add_lwpolyline(pts, dxfattribs={'layer': 'TERRENO',
                                            'lineweight': _LW_TERRAIN})

    # ── 2. Plano de comparación ─────────────────────────────────────────────
    msp.add_line((0.0, 0.0), (x_max, 0.0),
                 dxfattribs={'layer': 'PLANO_COMP', 'lineweight': _LW_PLANE})
    _add_text(msp, f'PC={comparison_plane:.2f} m',
              (x_max + 5.0, 0.0), _TEA.MIDDLE_LEFT, _TXT_PC, 'PLANO_COMP')

    # ── 3. Grid de cotas ────────────────────────────────────────────────────
    grid_step = 10.0
    g = math.ceil(comparison_plane / grid_step) * grid_step
    while g <= z_max_v + grid_step:
        gy = _py(g, comparison_plane, v_scale)
        if gy >= 0:
            msp.add_line((0.0, gy), (x_max, gy),
                         dxfattribs={'layer': 'GRID', 'lineweight': _LW_VERT})
            msp.add_line((_GRID_LBL_X, gy), (0.0, gy),
                         dxfattribs={'layer': 'GRID', 'lineweight': _LW_PLANE})
            _add_text(msp, f'{g:.1f}',
                      (_GRID_LBL_X - 1.0, gy), _TEA.MIDDLE_RIGHT,
                      _TXT_GRID, 'GRID')
        g += grid_step

    # ── 4. Línea base (tope de guitarra) ────────────────────────────────────
    msp.add_line((0.0, TABLE_TOP), (x_max, TABLE_TOP),
                 dxfattribs={'layer': 'GRID', 'lineweight': _LW_PLANE})

    # ── 5. Vértices originales ──────────────────────────────────────────────
    vert_px = {}
    for vert_num, pt in enumerate(orig_pts, 1):
        if pt[2] is None:
            continue
        px = _px(pt[3], h_scale)
        py = _py(pt[2], comparison_plane, v_scale)
        vert_px[round(px, 3)] = pt[3]

        msp.add_line((px, TABLE_TOP), (px, py),
                     dxfattribs={'layer': 'REF_VERT', 'lineweight': _LW_VERT})
        msp.add_line((px - _TICK_HALF, py), (px + _TICK_HALF, py),
                     dxfattribs={'layer': 'VERTICES', 'lineweight': _LW_TICK})
        msp.add_line((px, py - _TICK_HALF), (px, py + _TICK_HALF),
                     dxfattribs={'layer': 'VERTICES', 'lineweight': _LW_TICK})
        # Cota: el pie del texto arranca desde py + _cota_offset
        # (el offset ya incluye el TICK_HALF internamente)
        _add_text(msp, f'{pt[2]:.3f}',
                  (px, py + _cota_offset), _TEA.BOTTOM_CENTER,
                  _TXT_COTA, 'COTAS', rotation=90.0)

    # ── 6. MIN y MAX ────────────────────────────────────────────────────────
    # El texto MIN/MAX se coloca ENCIMA de la línea de terreno (no junto al punto).
    # Si el punto MIN/MAX coincide en X con un vértice original, se desplaza
    # horizontalmente _TXT_COTA*2 mm para evitar solapamiento.
    z_min_all = min(zs)
    z_max_all = max(zs)
    # Offset vertical: suficiente para quedar por encima del texto de cota
    # del vértice (que ya ocupa _cota_offset + longitud del texto rotado 90°)
    _minmax_v_offset = _cota_offset + _TXT_COTA * 8   # ~24 mm de papel

    def _minmax_x(pxm):
        """Desplaza horizontalmente si coincide con un vértice existente."""
        for vpx in vert_px:
            if abs(pxm - vpx) < _TXT_COTA * 1.5:
                return pxm + _TXT_COTA * 3   # desplazar a la derecha
        return pxm

    for pt in terrain_points:
        if pt[2] == z_min_all:
            pxm = _px(pt[3], h_scale)
            pym = _py(pt[2], comparison_plane, v_scale)
            msp.add_line((pxm - _TICK_HALF, pym), (pxm + _TICK_HALF, pym),
                         dxfattribs={'layer': 'MINMAX', 'lineweight': _LW_TICK})
            msp.add_line((pxm, pym - _TICK_HALF), (pxm, pym + _TICK_HALF),
                         dxfattribs={'layer': 'MINMAX', 'lineweight': _LW_TICK})
            tx = _minmax_x(pxm)
            # MIN cuelga hacia abajo desde el punto (mínimo = punto más bajo)
            _add_text(msp, f'MIN:{z_min_all:.3f}',
                      (tx, pym - _TICK_HALF - _cota_offset), _TEA.TOP_CENTER,
                      _TXT_COTA, 'MINMAX', rotation=90.0)
            break

    for pt in reversed(terrain_points):
        if pt[2] == z_max_all:
            pxm = _px(pt[3], h_scale)
            pym = _py(pt[2], comparison_plane, v_scale)
            msp.add_line((pxm - _TICK_HALF, pym), (pxm + _TICK_HALF, pym),
                         dxfattribs={'layer': 'MINMAX', 'lineweight': _LW_TICK})
            msp.add_line((pxm, pym - _TICK_HALF), (pxm, pym + _TICK_HALF),
                         dxfattribs={'layer': 'MINMAX', 'lineweight': _LW_TICK})
            tx = _minmax_x(pxm)
            # MAX sube por encima del texto de cota del vértice
            _add_text(
                msp,
                f'MAX:{z_max_all:.3f}',
                (tx, pym + _TICK_HALF + _minmax_v_offset),
                _TEA.BOTTOM_CENTER,
                _TXT_COTA,
                'MINMAX',
                rotation=90.0)
            break

    # ── 7. Marco de guitarra ────────────────────────────────────────────────
    msp.add_lwpolyline(
        [(0.0, TABLE_TOP), (x_max, TABLE_TOP),
         (x_max, TABLE_BOT), (0.0, TABLE_BOT)],
        close=True,
        dxfattribs={'layer': 'TABLA_MARCO', 'lineweight': _LW_TABLE},
    )
    for y_sep in (TABLE_H1, TABLE_H2, TABLE_H3):
        msp.add_line((0.0, y_sep), (x_max, y_sep),
                     dxfattribs={'layer': 'TABLA_MARCO',
                                 'lineweight': _LW_TABLE // 2})

    # ── 8. Columnas unificadas ──────────────────────────────────────────────
    columns = []
    for pt in orig_pts:
        if pt[2] is not None:
            columns.append({'dist': pt[3], 'z': pt[2], 'is_vertex': True})

    if use_equidistant and equidistant_interval > 0:
        total_dist = terrain_points[-1][3]
        d = equidistant_interval
        while d < total_dist - 0.01:
            px_eq = _px(d, h_scale)
            if not any(abs(px_eq - vp) < _OVERLAP_TOL for vp in vert_px):
                z_eq = _interp_z(terrain_points, d)
                if z_eq is not None:
                    columns.append({'dist': d, 'z': z_eq, 'is_vertex': False})
            d += equidistant_interval

    columns.sort(key=lambda c: c['dist'])

    # ── 9. Datos de guitarra ────────────────────────────────────────────────
    y_vert_num = (TABLE_TOP + TABLE_H1) / 2
    y_cota = (TABLE_H1 + TABLE_H2) / 2
    y_par = (TABLE_H2 + TABLE_H3) / 2
    y_tot = (TABLE_H3 + TABLE_BOT) / 2
    _dat_rot = 90.0 if text_vertical else 0.0
    _dat_align = _TEA.MIDDLE_CENTER

    # Altura de los ticks (pequeñas marcas verticales)
    _tick_h = 2.0

    prev_dist = 0.0
    vert_counter = 0
    for col in columns:
        px_col = _px(col['dist'], h_scale)
        dist_tot = col['dist']
        dist_par = dist_tot - prev_dist
        prev_dist = dist_tot

        if col['is_vertex']:
            vert_counter += 1

        # Pequeños ticks en TODAS las líneas horizontales de la guitarra
        # Top
        msp.add_line((px_col, TABLE_TOP), (px_col, TABLE_TOP + _tick_h),
                     dxfattribs={'layer': 'TABLA_MARCO',
                                 'lineweight': _LW_TABLE // 2})
        # Entre Vértice y Cota
        msp.add_line(
            (px_col,
             TABLE_H1 - _tick_h),
            (px_col,
             TABLE_H1 + _tick_h),
            dxfattribs={
                'layer': 'TABLA_MARCO',
                'lineweight': _LW_TABLE // 2})
        # Entre Cota y Dist.Parcial
        msp.add_line(
            (px_col,
             TABLE_H2 - _tick_h),
            (px_col,
             TABLE_H2 + _tick_h),
            dxfattribs={
                'layer': 'TABLA_MARCO',
                'lineweight': _LW_TABLE // 2})
        # Entre Dist.Parcial y Dist.Total
        msp.add_line(
            (px_col,
             TABLE_H3 - _tick_h),
            (px_col,
             TABLE_H3 + _tick_h),
            dxfattribs={
                'layer': 'TABLA_MARCO',
                'lineweight': _LW_TABLE // 2})
        # Bottom
        msp.add_line((px_col, TABLE_BOT - _tick_h), (px_col, TABLE_BOT),
                     dxfattribs={'layer': 'TABLA_MARCO',
                                 'lineweight': _LW_TABLE // 2})

        if not col['is_vertex']:
            py_eq = _py(col['z'], comparison_plane, v_scale)
            msp.add_line((px_col, TABLE_TOP), (px_col, py_eq), dxfattribs={
                         'layer': 'EQUI_VERT', 'lineweight': _LW_VERT})

        # Número de vértice — solo para vértices originales
        if col['is_vertex']:
            _add_text(
                msp,
                f'V{vert_counter}',
                (px_col,
                 y_vert_num),
                _dat_align,
                _TXT_TABLA,
                'TABLA_TEXTO',
                rotation=_dat_rot)

        _add_text(msp, f"{col['z']:.3f}",
                  (px_col, y_cota), _dat_align, _TXT_TABLA, 'TABLA_TEXTO',
                  rotation=_dat_rot)
        _add_text(msp, _format_pk(dist_par),
                  (px_col, y_par), _dat_align, _TXT_TABLA, 'TABLA_TEXTO',
                  rotation=_dat_rot)
        _add_text(msp, _format_pk(dist_tot),
                  (px_col, y_tot), _dat_align, _TXT_TABLA, 'TABLA_TEXTO',
                  rotation=_dat_rot)

    # ── 10. Etiquetas de fila — siempre horizontales ────────────────────────
    for y_mid, label in [
        (y_vert_num, 'Vértice'),
        (y_cota, 'Cota (m)'),
        (y_par, 'Dist.Parcial (PK)'),
        (y_tot, 'Dist.Total (PK)'),
    ]:
        _add_text(msp, label,
                  (_LABEL_X, y_mid), _TEA.MIDDLE_RIGHT,
                  _TXT_TABLA, 'TABLA_TEXTO', rotation=0.0)

    # ── 11. Título y escala ─────────────────────────────────────────────────
    y_title = _py(z_max_v, comparison_plane, v_scale) + 20.0
    _add_text(msp, title,
              (x_max / 2, y_title), _TEA.BOTTOM_CENTER, _TXT_TITLE, 'TITULO')
    _add_text(msp, f'Escala  H 1:{h_scale}   V 1:{v_scale}',
              (x_max, y_title - 6.0), _TEA.BOTTOM_RIGHT, _TXT_PC, 'TITULO')

    doc.saveas(output_path)


# ─────────────────────────────────────────────────────────────────────────────
#  CSV
# ─────────────────────────────────────────────────────────────────────────────

def export_profile_csv(terrain_points, original_indices, output_path,
                       axis_name="Eje",
                       use_equidistant=False,
                       equidistant_interval=100.0):
    """
    Exporta CSV del perfil en formato europeo (coma decimal, punto y coma como separador).
    Columnas: Eje, Tipo, Num_Vertice, Dist_Total_m, Dist_Parcial_m, Cota_m, X, Y

    Si use_equidistant es True, incluye puntos interpolados a equidistancia.
    """
    import csv

    def _fmt(v):
        """Formatea número con coma decimal."""
        return f'{v:.3f}'.replace('.', ',')

    # Interpolar puntos a equidistancia si está habilitado
    if use_equidistant and equidistant_interval > 0:
        def _interp_z_csv(pts, dist):
            """Interpola cota Z a una distancia dada."""
            for i, pt in enumerate(pts):
                if pt[3] >= dist:
                    if i == 0 or abs(pt[3] - dist) < 1e-9:
                        return pt[2]
                    p0 = pts[i - 1]
                    d0, z0, d1, z1 = p0[3], p0[2], pt[3], pt[2]
                    if z0 is None or z1 is None:
                        return None
                    return z0 + (z1 - z0) * (dist - d0) / (d1 - d0)
            return pts[-1][2] if pts else None

        def _interp_xy_csv(pts, dist):
            """Interpola coordenadas X, Y a una distancia dada."""
            for i, pt in enumerate(pts):
                if pt[3] >= dist:
                    if i == 0 or abs(pt[3] - dist) < 1e-9:
                        return pt[0], pt[1]
                    p0 = pts[i - 1]
                    t = (dist - p0[3]) / (pt[3] - p0[3])
                    x_eq = p0[0] + (pt[0] - p0[0]) * t
                    y_eq = p0[1] + (pt[1] - p0[1]) * t
                    return x_eq, y_eq
            return None, None

        total_dist = terrain_points[-1][3]

        # Distancias de los vértices originales, para no duplicar una marca
        # de equidistancia que caiga justo sobre un vértice ya existente.
        orig_dists = [terrain_points[i][3] for i in original_indices]

        d = equidistant_interval
        interpolated_points = []

        while d < total_dist - 0.01:
            if not any(abs(d - od) < 1e-6 for od in orig_dists):
                z_eq = _interp_z_csv(terrain_points, d)
                if z_eq is not None:
                    x_eq, y_eq = _interp_xy_csv(terrain_points, d)
                    if x_eq is not None and y_eq is not None:
                        interpolated_points.append((x_eq, y_eq, z_eq, d))
            d += equidistant_interval

        # IMPORTANTE: el CSV con equidistancia activada NO debe incluir todos
        # los puntos del muestreo fino (intervalo de segmentación, p.ej. 1 m).
        # Solo deben quedar los vértices ORIGINALES del eje + los puntos
        # interpolados a la equidistancia solicitada (p.ej. 50 m), igual que
        # hace el "cuadro de datos" (guitarra) del DXF de perfil.
        all_points = [(terrain_points[i], True) for i in original_indices]
        for pt in interpolated_points:
            all_points.append((pt, False))
        all_points.sort(key=lambda x: x[0][3])

        # Reconstruir terrain_points y original_indices con los nuevos índices
        terrain_points = [pt for pt, _ in all_points]
        original_indices = [
            i for i, (pt, is_orig) in enumerate(all_points) if is_orig]

    orig_set = set(original_indices)
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['Eje', 'Tipo', 'Num_Vertice', 'Dist_Total_m',
                    'Dist_Parcial_m', 'Cota_m', 'X', 'Y'])
        vert_num = 0
        prev_dist = 0.0
        for i, pt in enumerate(terrain_points):
            x, y, z, dist = pt
            if z is None:
                continue
            if i in orig_set:
                vert_num += 1
                tipo = 'VERTICE'
                label = vert_num
            else:
                tipo = 'INTERPOLADO'
                label = ''
            dist_par = dist - prev_dist
            prev_dist = dist
            w.writerow([axis_name, tipo, label,
                        _fmt(dist), _fmt(dist_par),
                        _fmt(z), _fmt(x), _fmt(y)])
