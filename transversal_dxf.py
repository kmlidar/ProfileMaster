# -*- coding: utf-8 -*-
"""
transversal_dxf.py
Generación de perfiles transversales sobre MDT y exportación a DXF.

Para cada sección transversal se muestrea el terreno N metros a izquierda
y M metros a derecha del eje, perpendicular al mismo, y se genera un DXF
con el layout habitual de perfiles transversales:
 - Línea de terreno
 - Línea de cota cero (base)
 - Indicaciones de PK, número de transversal y distancias
"""

import math

try:
    from osgeo import gdal
    gdal.UseExceptions()
except ImportError:
    raise ImportError("GDAL no disponible.")


def _format_pk(dist):
    """Formatea distancia como PK estándar: 0+860, 1+150, etc."""
    if dist is None or dist < 0:
        dist = max(0.0, dist or 0.0)
    km = int(dist // 1000)
    m = dist - km * 1000
    if abs(m - round(m)) < 1e-6:
        return f"{km}+{int(round(m)):03d}"
    return f"{km}+{m:06.2f}"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers geométricos
# ─────────────────────────────────────────────────────────────────────────────


def _perpendicular_direction(p0, p1):
    """
    Devuelve el vector perpendicular unitario (izquierda → derecha) al
    segmento p0→p1.  'Izquierda' es 90° antihorario respecto a la dirección
    de avance.  Devuelve (nx_izq, ny_izq, nx_der, ny_der).
    """
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 1.0, 0.0, -1.0
    ux = dx / length
    uy = dy / length
    # 90° antihorario → izquierda en sentido topográfico (avance hacia delante)
    lx, ly = -uy, ux    # izquierda
    rx, ry = uy, -ux    # derecha
    return lx, ly, rx, ry


def _find_segment_at(vertices_2d, dist):
    """
    Dado el eje 2D como lista de (x, y) y una distancia acumulada 'dist',
    devuelve el punto (x, y) y la tangente (ux, uy) en esa posición.
    """
    acum = 0.0
    for i in range(1, len(vertices_2d)):
        x0, y0 = vertices_2d[i - 1]
        x1, y1 = vertices_2d[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-9:
            continue
        if acum + seg >= dist - 1e-6:
            t = (dist - acum) / seg
            px = x0 + t * (x1 - x0)
            py = y0 + t * (y1 - y0)
            ux = (x1 - x0) / seg
            uy = (y1 - y0) / seg
            return px, py, ux, uy
        acum += seg
    # Fin del eje
    x0, y0 = vertices_2d[-2]
    x1, y1 = vertices_2d[-1]
    seg = math.hypot(x1 - x0, y1 - y0)
    if seg > 1e-9:
        ux = (x1 - x0) / seg
        uy = (y1 - y0) / seg
    else:
        ux, uy = 1.0, 0.0
    return x1, y1, ux, uy


def _axis_total_length(vertices_2d):
    total = 0.0
    for i in range(1, len(vertices_2d)):
        total += math.hypot(
            vertices_2d[i][0] - vertices_2d[i - 1][0],
            vertices_2d[i][1] - vertices_2d[i - 1][1])
    return total


# ─────────────────────────────────────────────────────────────────────────────
#  Muestreo transversal
# ─────────────────────────────────────────────────────────────────────────────

def _sample_transversal(cx, cy, ux, uy, dist_left, dist_right, sample_step, sampler):
    """
    Muestrea el terreno a lo largo de la transversal que pasa por (cx, cy)
    perpendicular a (ux, uy).

    Devuelve lista de (dist_from_axis, z):
      - dist negativa → izquierda del eje
      - dist positiva → derecha del eje
      - dist = 0 → eje
    """
    # Vector izquierda y derecha
    lx, ly = -uy, ux    # izquierda
    rx, ry = uy, -ux    # derecha

    points = []

    # Izquierda (de -dist_left a 0, paso negativo → iremos de 0 hacia atrás)
    n_left = max(1, int(dist_left / sample_step))
    for i in range(n_left, 0, -1):
        d = i * (dist_left / n_left)
        px = cx + lx * d
        py = cy + ly * d
        z = sampler.sample(px, py)
        points.append((-d, z, px, py))

    # Eje
    z_axis = sampler.sample(cx, cy)
    points.append((0.0, z_axis, cx, cy))

    # Derecha (de 0 a +dist_right)
    n_right = max(1, int(dist_right / sample_step))
    for i in range(1, n_right + 1):
        d = i * (dist_right / n_right)
        px = cx + rx * d
        py = cy + ry * d
        z = sampler.sample(px, py)
        points.append((d, z, px, py))

    return points


def _interpolate_z_transversal(pts):
    """
    Interpola Z faltantes en una lista de (dist, z, x, y).
    Devuelve lista con los mismos elementos pero z nunca None.
    """
    result = list(pts)
    n = len(result)
    if n == 0:
        return result

    # Buscar primer y último válido
    first_v = next((i for i in range(n) if result[i][1] is not None), None)
    last_v = next((i for i in range(n - 1, -1, -1) if result[i][1] is not None), None)

    if first_v is None:
        # Sin ningún valor → z = 0
        result = [(d, 0.0, x, y) for d, z, x, y in result]
        return result

    # Rellenar extremos
    for i in range(first_v):
        d, _, x, y = result[i]
        result[i] = (d, result[first_v][1], x, y)
    for i in range(last_v + 1, n):
        d, _, x, y = result[i]
        result[i] = (d, result[last_v][1], x, y)

    # Interpolar intermedios
    i = 0
    while i < n:
        if result[i][1] is None:
            j = i + 1
            while j < n and result[j][1] is None:
                j += 1
            if j < n:
                z0 = result[i - 1][1]
                z1 = result[j][1]
                d0 = result[i - 1][0]
                d1 = result[j][0]
                for k in range(i, j):
                    t = (result[k][0] - d0) / (d1 - d0) if d1 != d0 else 0.0
                    zk = z0 + t * (z1 - z0)
                    result[k] = (result[k][0], zk, result[k][2], result[k][3])
        i += 1
    return result


def _interp_at_offset(pts, d_target):
    """
    Interpola la cota Z en una distancia concreta 'd_target' (con signo,
    negativa = izquierda) a partir de la lista de puntos muestreados
    [(dist, z, x, y), ...] ya con Z interpolada (sin None).
    Si 'd_target' cae fuera del rango muestreado, devuelve el extremo
    más cercano.
    """
    if not pts:
        return None
    if d_target <= pts[0][0]:
        return pts[0][1]
    if d_target >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        d0, z0 = pts[i - 1][0], pts[i - 1][1]
        d1, z1 = pts[i][0], pts[i][1]
        if d0 <= d_target <= d1:
            if d1 == d0:
                return z0
            t = (d_target - d0) / (d1 - d0)
            return z0 + t * (z1 - z0)
    return pts[-1][1]


# ─────────────────────────────────────────────────────────────────────────────
#  Exportación a DXF
# ─────────────────────────────────────────────────────────────────────────────

# Escala de papel (mm) para transversales
_H_SC = 500    # horizontal 1:500
_V_SC = 100    # vertical 1:100

# Separación entre transversales en el DXF (mm de papel)
_TRANS_SEP_X = 200.0   # espacio horizontal entre transversales
_TRANS_SEP_Y = 150.0   # espacio vertical entre filas

# Equidistancia (m) por defecto de la mini-guitarra de cada transversal:
# se dibuja una columna cada N metros desde el eje hasta dist_left/dist_right,
# en vez de una lista fija de distancias.
_DEFAULT_GUITARRA_INTERVAL = 5.0

# Layout vertical (mm de papel) de la mini-guitarra: una franja de cabecera
# (número de transversal + PK) y dos filas de datos (Cota encima, Distancia
# debajo, tal y como se pidió).
_GUIT_HEADER_H = 12.0
_GUIT_ROW_H = 9.0
_GUIT_TICK_H = 1.2

# Margen (m) entre el punto más bajo del terreno de la sección y el plano
# de comparación automático, para que la franja de terreno no quede
# reducida a una rendija minúscula como ocurría al usar múltiplos de 5 m.
_AUTO_PLANE_MARGIN = 1.0


def _paper_x(dist, h_scale):
    """Convierte distancia real (m) a coordenada X en papel (mm)."""
    return dist / h_scale * 1000.0


def _paper_y(z, z_ref, v_scale):
    """Convierte cota real (m) a coordenada Y en papel (mm) respecto al plano z_ref."""
    return (z - z_ref) / v_scale * 1000.0


def export_transversales_dxf(
    vertices_2d,
    sampler,
    spacing,
    dist_left,
    dist_right,
    sample_step,
    output_path,
    h_scale=500,
    v_scale=100,
    axis_name="Eje",
    comparison_plane=None,
    guitarra_interval=None,
    progress_callback=None,
):
    """
    Genera el DXF de perfiles transversales.

    Parámetros
    ----------
    vertices_2d      : list[(x, y)]
    sampler          : MDTSampler
    spacing          : float  — distancia entre transversales (m)
    dist_left        : float  — ancho a izquierda (m)
    dist_right       : float  — ancho a derecha (m)
    sample_step      : float  — paso de muestreo transversal (m)
    output_path      : str    — ruta DXF de salida
    h_scale          : int    — escala horizontal
    v_scale          : int    — escala vertical (referencia inicial; se ajusta por sección)
    axis_name        : str    — nombre del eje
    comparison_plane : float|None
        None  → plano automático por sección: redondeado a 0.5 m por debajo
               del punto más bajo del terreno de esa sección (margen pequeño,
               sin el hueco enorme de usar múltiplos de 5 m).
        float → plano fijo igual para todas las secciones
    guitarra_interval : float | None
        Equidistancia (m) de la mini-guitarra de cada transversal: se dibuja
        una columna con la cota del terreno cada 'guitarra_interval' metros,
        a izquierda y derecha del eje, hasta llegar a dist_left/dist_right
        (no una lista fija de distancias). Por defecto 5.0 m. El propio eje
        (distancia 0) no se repite aquí porque ya se marca aparte con un
        círculo y su cota.
    progress_callback : callable(pct, msg)
    """
    try:
        import ezdxf
        from ezdxf.enums import TextEntityAlignment as TEA
    except ImportError:
        try:
            from .perfil_dxf import _ensure_ezdxf
            _ensure_ezdxf()
            import ezdxf
            from ezdxf.enums import TextEntityAlignment as TEA
        except Exception as e:
            raise RuntimeError(f"No se pudo cargar ezdxf: {e}")

    if not guitarra_interval or guitarra_interval <= 0:
        guitarra_interval = _DEFAULT_GUITARRA_INTERVAL

    def _guitarra_offsets_for(d_left, d_right):
        """Genera las distancias -d_left..0..d_right a equidistancia, incluyendo el centro (0)."""
        offs = [0.0]  # siempre incluir el eje central
        d = guitarra_interval
        while d <= d_right + 1e-6:
            offs.append(d)
            d += guitarra_interval
        d = -guitarra_interval
        while d >= -d_left - 1e-6:
            offs.append(d)
            d -= guitarra_interval
        return sorted(offs)

    total_len = _axis_total_length(vertices_2d)

    # Generar lista de PKs de transversales
    pks = []
    pk = 0.0
    while pk <= total_len + 1e-6:
        pks.append(min(pk, total_len))
        pk += spacing
    if abs(pks[-1] - total_len) > 1e-3:
        pks.append(total_len)

    n_trans = len(pks)
    if progress_callback:
        progress_callback(5, f"Generando {n_trans} transversales...")

    doc = ezdxf.new('R2010', setup=True)
    msp = doc.modelspace()

    # Capas
    for lname, color, ltype in [
        ('TRANS_TERRENO', 3, 'Continuous'),    # verde
        ('TRANS_BASE', 4, 'DASHED'),           # cyan
        ('TRANS_EJE', 1, 'Continuous'),        # rojo
        ('TRANS_COTAS', 3, 'Continuous'),      # verde
        ('TRANS_TEXTOS', 7, 'Continuous'),     # blanco/negro
        ('TRANS_MARCO', 8, 'Continuous'),      # gris
        ('TRANS_GUITARRA', 8, 'Continuous'),   # gris — marco/ticks de la mini-guitarra
        ('TRANS_GUIA', 8, 'DOT'),              # gris — líneas guía punteadas
    ]:
        if lname not in doc.layers:
            lay = doc.layers.new(lname)
            lay.color = color
            try:
                lay.dxf.linetype = ltype
            except Exception:
                pass

    # Dimensiones de cada caja transversal en papel (mm)
    ancho_papel = _paper_x(dist_left + dist_right, h_scale)
    # alto de la caja: zona de terreno + mini-guitarra (cabecera + 2 filas)
    alto_zona = 80.0      # mm para la curva de terreno
    alto_guitarra = _GUIT_HEADER_H + 2 * _GUIT_ROW_H  # mm para las anotaciones
    alto_caja = alto_zona + alto_guitarra

    cols = max(1, int(1200 / (ancho_papel + 30)))  # cuántas transversales por fila

    # Offsets de la mini-guitarra (mismos para todas las secciones, ya que
    # dist_left/dist_right son constantes para todo el trazado)
    guitarra_offsets = _guitarra_offsets_for(dist_left, dist_right)

    for idx, pk_val in enumerate(pks):
        if progress_callback and idx % max(1, n_trans // 20) == 0:
            progress_callback(
                5 + int(idx / n_trans * 90),
                f"Transversal {idx + 1}/{n_trans} — PK {_format_pk(pk_val)}"
            )

        # Posición de esta caja en el DXF
        col = idx % cols
        row = idx // cols
        ox = col * (ancho_papel + 30.0)   # origen X (mm)
        oy = -row * (alto_caja + 20.0)    # origen Y (mm)

        # Punto sobre el eje y tangente
        cx, cy, ux, uy = _find_segment_at(vertices_2d, pk_val)

        # Muestreo transversal
        raw_pts = _sample_transversal(
            cx, cy, ux, uy, dist_left, dist_right, sample_step, sampler)
        pts = _interpolate_z_transversal(raw_pts)

        if not pts:
            continue

        # ── Plano de comparación ─────────────────────────────────────────────
        zs = [z for _, z, _, _ in pts if z is not None]
        if not zs:
            continue

        # Cota del eje en esta sección (punto donde dist == 0)
        z_axis_val = next((z for d, z, _, _ in pts if abs(d) < 1e-3), None)
        if z_axis_val is None:
            z_axis_val = min(zs)

        z_min_section = min(zs)
        z_max = max(zs)

        if comparison_plane is None:
            # Automático: redondeado a 0.5 m por debajo del punto más bajo
            # de ESTA sección, con un margen pequeño y fijo. Antes se usaba
            # un múltiplo de 5 por debajo de la cota del eje, lo que dejaba
            # un hueco enorme entre el plano y el terreno cuando la sección
            # apenas variaba unos decímetros.
            z_ref = math.floor((z_min_section - _AUTO_PLANE_MARGIN) * 2) / 2.0
        else:
            z_ref = comparison_plane

        # ── Altura de la zona de terreno (en papel) ─────────────────────────
        z_range = max(z_max - z_ref, 0.5)
        # Escalar para que el terreno quepa en alto_zona mm
        v_scale_local = z_range / (alto_zona / 1000.0)

        # ── Marco exterior ───────────────────────────────────────────────────
        marco_pts = [
            (ox, oy + alto_guitarra),
            (ox + ancho_papel, oy + alto_guitarra),
            (ox + ancho_papel, oy + alto_caja),
            (ox, oy + alto_caja),
            (ox, oy + alto_guitarra),
        ]
        msp.add_lwpolyline(marco_pts, dxfattribs={'layer': 'TRANS_MARCO', 'lineweight': 25})

        # Marco guitarra (zona inferior)
        guitarra_pts = [
            (ox, oy),
            (ox + ancho_papel, oy),
            (ox + ancho_papel, oy + alto_guitarra),
            (ox, oy + alto_guitarra),
            (ox, oy),
        ]
        msp.add_lwpolyline(guitarra_pts, dxfattribs={'layer': 'TRANS_MARCO', 'lineweight': 15})

        # ── Línea base (z_ref) ───────────────────────────────────────────────
        y_base = oy + alto_guitarra
        msp.add_line(
            (ox, y_base), (ox + ancho_papel, y_base),
            dxfattribs={'layer': 'TRANS_BASE', 'lineweight': 18}
        )
        # Cota del plano de comparación — antes no se indicaba en ningún sitio
        t_pc = msp.add_text(
            f'PC={z_ref:.2f} m',
            dxfattribs={'height': 1.8, 'layer': 'TRANS_BASE', 'color': 4}
        )
        t_pc.set_placement((ox + ancho_papel + 2.0, y_base), align=TEA.MIDDLE_LEFT)

        # ── Línea del eje vertical ───────────────────────────────────────────
        x_axis_paper = ox + _paper_x(dist_left, h_scale)
        msp.add_line(
            (x_axis_paper, y_base),
            (x_axis_paper, oy + alto_caja),
            dxfattribs={'layer': 'TRANS_EJE', 'lineweight': 18}
        )

        # ── Línea de terreno ─────────────────────────────────────────────────
        terrain_paper = []
        for d, z, _, _ in pts:
            px = ox + _paper_x(dist_left + d, h_scale)
            py = y_base + _paper_y(z, z_ref, v_scale_local)
            terrain_paper.append((px, py))

        if len(terrain_paper) >= 2:
            msp.add_lwpolyline(
                terrain_paper,
                dxfattribs={'layer': 'TRANS_TERRENO', 'lineweight': 35}
            )

        # ── Cabecera de la mini-guitarra: número de transversal + PK ────────
        h_txt = 2.5
        y_header_bot = oy + 2 * _GUIT_ROW_H   # límite cabecera / fila Cota
        y_cota_bot = oy + _GUIT_ROW_H         # límite fila Cota / fila Distancia
        y_txt_num = y_header_bot + _GUIT_HEADER_H * 0.72
        y_txt_pk = y_header_bot + _GUIT_HEADER_H * 0.28
        y_cota_mid = (y_header_bot + y_cota_bot) / 2.0
        y_dist_mid = (y_cota_bot + oy) / 2.0

        # Número de transversal
        t_num = msp.add_text(
            f"T-{idx + 1}",
            dxfattribs={'height': h_txt * 1.2, 'layer': 'TRANS_TEXTOS', 'color': 1}
        )
        t_num.set_placement(
            (ox + ancho_papel / 2, y_txt_num),
            align=TEA.MIDDLE_CENTER
        )

        # PK
        t_pk = msp.add_text(
            f"PK {_format_pk(pk_val)}",
            dxfattribs={'height': h_txt, 'layer': 'TRANS_TEXTOS'}
        )
        t_pk.set_placement(
            (ox + ancho_papel / 2, y_txt_pk),
            align=TEA.MIDDLE_CENTER
        )

        # ── Separadores horizontales de la mini-guitarra (cabecera/cota/dist) ─
        for y_sep in (y_header_bot, y_cota_bot):
            msp.add_line(
                (ox, y_sep), (ox + ancho_papel, y_sep),
                dxfattribs={'layer': 'TRANS_GUITARRA', 'lineweight': 13})

        # Etiquetas de fila, una vez por caja (a la izquierda, en el hueco
        # entre transversales)
        for y_mid, label in ((y_cota_mid, 'Cota (m)'), (y_dist_mid, 'Dist (m)')):
            t_row = msp.add_text(
                label,
                dxfattribs={'height': 1.8, 'layer': 'TRANS_TEXTOS', 'color': 8})
            t_row.set_placement((ox - 2.0, y_mid), align=TEA.MIDDLE_RIGHT)

        # ── Mini-guitarra: columnas con cota (encima) y distancia (debajo) ───
        # en las distancias configuradas (negativas = izquierda, positivas =
        # derecha), con guía punteada hasta el punto real del terreno.
        for d_off in guitarra_offsets:
            if d_off < -dist_left - 1e-6 or d_off > dist_right + 1e-6:
                continue  # fuera del ancho muestreado en esta sección

            z_off = _interp_at_offset(pts, d_off)
            if z_off is None:
                continue

            px_col = ox + _paper_x(dist_left + d_off, h_scale)

            # Pequeñas marcas verticales en cada línea horizontal de la
            # mini-guitarra (mismo estilo que el perfil longitudinal)
            for y_sep in (y_base, y_header_bot, y_cota_bot, oy):
                msp.add_line(
                    (px_col, y_sep - _GUIT_TICK_H), (px_col, y_sep + _GUIT_TICK_H),
                    dxfattribs={'layer': 'TRANS_GUITARRA', 'lineweight': 9})

            # Guía punteada desde la guitarra hasta el punto real del terreno
            py_terr = y_base + _paper_y(z_off, z_ref, v_scale_local)
            msp.add_line(
                (px_col, y_base), (px_col, py_terr),
                dxfattribs={'layer': 'TRANS_GUIA', 'lineweight': 9})

            t_cota_col = msp.add_text(
                f"{z_off:.2f}",
                dxfattribs={'height': 1.5, 'layer': 'TRANS_COTAS', 'color': 3,
                            'rotation': 90.0})
            t_cota_col.set_placement((px_col, y_cota_mid), align=TEA.MIDDLE_CENTER)

            dist_lbl = "0" if abs(d_off) < 1e-6 else f"{d_off:+.1f}"
            t_dist_col = msp.add_text(
                dist_lbl,
                dxfattribs={'height': 1.5, 'layer': 'TRANS_TEXTOS', 'color': 7,
                            'rotation': 90.0})
            t_dist_col.set_placement((px_col, y_dist_mid), align=TEA.MIDDLE_CENTER)

        # ── Cota en el eje (PK central de la sección) ────────────────────────
        if z_axis_val is not None:
            x_a = x_axis_paper
            y_a = y_base + _paper_y(z_axis_val, z_ref, v_scale_local)
            msp.add_circle((x_a, y_a), 1.0,
                           dxfattribs={'layer': 'TRANS_COTAS', 'color': 1})
            t_cota = msp.add_text(
                f"{z_axis_val:.2f}",
                dxfattribs={'height': h_txt * 0.8, 'layer': 'TRANS_COTAS', 'color': 1}
            )
            t_cota.set_placement((x_a + 2, y_a + 2), align=TEA.BOTTOM_LEFT)

    if progress_callback:
        progress_callback(98, "Guardando DXF de transversales...")

    doc.saveas(output_path)

    if progress_callback:
        progress_callback(100, f"DXF de transversales guardado: {output_path}")
