# -*- coding: utf-8 -*-
"""
mdt_export.py
Exportación del MDT recortado con buffer sobre el eje y generación de
curvas de nivel.

Funciones:
  export_mdt_buffer   → GeoTIFF recortado con buffer siguiendo el trazado
  export_curvas_nivel → DXF de curvas de nivel (normales + maestras + suavizado)
"""

import math
import os

try:
    from osgeo import gdal, ogr, osr
    gdal.UseExceptions()
except ImportError:
    raise ImportError("GDAL no disponible.")


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers geométricos
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_axes(data):
    """
    Acepta tanto una lista plana de puntos [(x,y), ...] de UN eje como una
    lista de ejes [[(x,y), ...], [(x,y), ...], ...] y siempre devuelve la
    segunda forma (lista de ejes).
    """
    if not data:
        return []
    first = data[0]
    if isinstance(first, (list, tuple)) and len(first) > 0 and isinstance(first[0], (list, tuple)):
        return [list(axis) for axis in data]
    return [list(data)]


def _build_axis_buffer_polygon(vertices_2d, buffer_m):
    """
    Construye un polígono de buffer que SIGUE EL TRAZADO real del eje,
    usando la API OGR (buffer geométrico sobre la línea).
    También añade buffer longitudinal en inicio y fin.

    Devuelve un ogr.Geometry de tipo polígono.
    """
    # Construir LineString OGR
    line = ogr.Geometry(ogr.wkbLineString)
    for x, y in vertices_2d:
        line.AddPoint_2D(x, y)

    # Buffer geométrico real siguiendo el trazado
    # NOTA: algunas versiones de los bindings de OGR (SWIG) no aceptan
    # 'quadsecs' como argumento de palabra clave (TypeError: Geometry.Buffer()
    # got an unexpected keyword argument 'quadsecs'), aunque sí lo aceptan
    # como argumento posicional. Se pasa posicional para máxima compatibilidad.
    poly = line.Buffer(buffer_m, 16)
    return poly


def _build_multi_axis_buffer_polygon(axes_vertices, buffer_m):
    """
    Construye el buffer de CADA eje por separado y devuelve la unión.

    IMPORTANTE: si hay varios ejes (varias polilíneas independientes en el
    archivo de entrada) y se concatenaran sus vértices en una sola línea,
    se crearía un segmento recto "puente" uniendo el final de un eje con
    el principio del siguiente, aunque estén muy alejados entre sí. Ese
    puente falso puede inflar muchísimo el polígono de buffer (o desplazarlo
    fuera de la zona real), provocando que ningún MDT lo intersecte y que
    el buffer / las curvas de nivel fallen sin generarse.
    """
    union_poly = None
    for verts in axes_vertices:
        if len(verts) < 2:
            continue
        poly = _build_axis_buffer_polygon(verts, buffer_m)
        if poly is None:
            continue
        union_poly = poly if union_poly is None else union_poly.Union(poly)
    if union_poly is None:
        raise ValueError(
            "No hay suficientes vértices en el/los eje(s) para construir el buffer.")
    return union_poly


def _poly_to_bbox(poly):
    """Devuelve (xmin, ymin, xmax, ymax) de la envolvente de un polígono OGR."""
    env = poly.GetEnvelope()
    return env[0], env[2], env[1], env[3]


def _get_mdt_paths_intersecting(mdt_list, xmin, ymin, xmax, ymax):
    """Filtra MDTs que intersectan con la bbox dada."""
    return [
        m['path'] for m in mdt_list
        if all((
            m['xmax'] >= xmin,
            m['xmin'] <= xmax,
            m['ymax'] >= ymin,
            m['ymin'] <= ymax,
        ))
    ]


def _create_cutline_shp(poly, shp_path, projection_wkt=None):
    """
    Guarda el polígono de buffer como Shapefile temporal para usarlo
    como cutline en gdal.Warp (recorte por forma real del eje).

    Devuelve (shp_path, layer_name). IMPORTANTE: el driver "ESRI Shapefile"
    IGNORA el nombre que se le pase a CreateLayer() y fuerza el nombre de
    la capa a coincidir con el nombre base del archivo .shp. Si luego se
    usa un nombre de capa distinto en 'cutlineLayer' al llamar a gdal.Warp,
    GDAL no encuentra la capa y falla con:
        "RuntimeError: Failed to identify source layer from datasource."
    Por eso aquí se calcula el nombre real y se devuelve para usarlo tal
    cual en el Warp.
    """
    driver = ogr.GetDriverByName('ESRI Shapefile')
    if os.path.exists(shp_path):
        driver.DeleteDataSource(shp_path)
    ds = driver.CreateDataSource(shp_path)
    srs = osr.SpatialReference()
    if projection_wkt:
        srs.ImportFromWkt(projection_wkt)
    layer_name = os.path.splitext(os.path.basename(shp_path))[0]
    lyr = ds.CreateLayer(layer_name, srs=srs, geom_type=ogr.wkbPolygon)
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetGeometry(poly)
    lyr.CreateFeature(feat)
    ds.FlushCache()
    ds = None
    return shp_path, layer_name


# ─────────────────────────────────────────────────────────────────────────────
#  Exportación MDT con buffer → GeoTIFF
# ─────────────────────────────────────────────────────────────────────────────

def export_mdt_buffer(
    vertices_2d,
    mdt_list,
    buffer_m,
    output_path,
    progress_callback=None,
):
    """
    Exporta el MDT recortado al buffer real del eje (siguiendo el trazado).

    El recorte usa gdal.Warp con cutline sobre el polígono de buffer
    generado geométricamente sobre la línea del eje, no un bbox rectangular.
    El bbox de recorte de la imagen sí es rectangular (envolvente del polígono)
    pero la zona enmascarada (NoData) sigue la forma real del buffer.

    Parámetros
    ----------
    vertices_2d   : list[(x,y)] de un único eje, o list[list[(x,y)]] con
                    varios ejes (cada uno se buferiza por separado y se
                    unen los resultados, para no crear un puente recto
                    falso entre ejes independientes).
    mdt_list      : list[dict]  — caché de MDTs
    buffer_m      : float       — buffer en metros
    output_path   : str         — GeoTIFF de salida
    progress_callback : callable(pct, msg)
    """
    if progress_callback:
        progress_callback(5, "Calculando buffer del eje...")

    # Polígono de buffer siguiendo el trazado (por eje, unidos si hay varios)
    axes_vertices = _normalize_axes(vertices_2d)
    buf_poly = _build_multi_axis_buffer_polygon(axes_vertices, buffer_m)
    xmin, ymin, xmax, ymax = _poly_to_bbox(buf_poly)

    mdt_paths = _get_mdt_paths_intersecting(mdt_list, xmin, ymin, xmax, ymax)
    if not mdt_paths:
        raise ValueError(
            "Ningún MDT intersecta con el área de buffer.\n"
            "Amplía el buffer o comprueba que los MDTs cubren la zona del eje."
        )

    if progress_callback:
        progress_callback(15, f"Mosaico de {len(mdt_paths)} MDT(s)...")

    # Obtener proyección del primer MDT para el cutline
    projection_wkt = None
    try:
        ds_ref = gdal.Open(mdt_paths[0], gdal.GA_ReadOnly)
        if ds_ref:
            projection_wkt = ds_ref.GetProjection()
            ds_ref = None
    except Exception:
        pass

    # VRT mosaico
    vrt_path = output_path.replace('.tif', '_tmp.vrt')
    vrt_opts = gdal.BuildVRTOptions(resampleAlg='bilinear')
    vrt_ds = gdal.BuildVRT(vrt_path, mdt_paths, options=vrt_opts)
    if vrt_ds is None:
        raise RuntimeError("No se pudo crear el mosaico VRT de los MDTs.")
    vrt_ds.FlushCache()
    vrt_ds = None

    if progress_callback:
        progress_callback(35, "Creando cutline del buffer...")

    # Shapefile temporal para cutline
    cutline_path = output_path.replace('.tif', '_cutline.shp')
    cutline_path, cutline_layer = _create_cutline_shp(buf_poly, cutline_path, projection_wkt)

    if progress_callback:
        progress_callback(50, "Recortando MDT con buffer del trazado...")

    # Si ya existe un GeoTIFF previo en esa ruta (p.ej. de una ejecución
    # anterior) lo borramos explícitamente con el driver de GDAL antes de
    # generarlo de nuevo. Si está bloqueado -porque está abierto como capa
    # en QGIS o en otro programa- lo detectamos aquí con un mensaje claro,
    # en vez de dejar que falle dentro de gdal.Warp con un RuntimeError
    # críptico de "Permission denied".
    if os.path.exists(output_path):
        try:
            gdal.GetDriverByName('GTiff').Delete(output_path)
        except Exception:
            raise RuntimeError(
                f"No se puede sobrescribir '{output_path}'.\n"
                "El archivo está abierto en QGIS (como capa) o bloqueado por "
                "otro programa. Cierra la capa/archivo e inténtalo de nuevo."
            )

    # Warp con cutline (recorte por la forma real del buffer)
    warp_opts = gdal.WarpOptions(
        format='GTiff',
        outputBounds=(xmin, ymin, xmax, ymax),
        cutlineDSName=cutline_path,
        cutlineLayer=cutline_layer,
        cropToCutline=False,     # usamos outputBounds para el bbox, cutline para máscara
        dstNodata=-9999,
        resampleAlg=gdal.GRA_Bilinear,
        creationOptions=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_NEEDED'],
        multithread=True,
        warpMemoryLimit=512,
    )

    if progress_callback:
        progress_callback(65, "Exportando GeoTIFF...")

    out_ds = gdal.Warp(output_path, vrt_path, options=warp_opts)
    if out_ds is None:
        raise RuntimeError(f"No se pudo generar el GeoTIFF: {output_path}")
    out_ds.FlushCache()
    out_ds = None

    # Limpiar temporales
    for tmp in [vrt_path, cutline_path,
                cutline_path.replace('.shp', '.dbf'),
                cutline_path.replace('.shp', '.shx'),
                cutline_path.replace('.shp', '.prj')]:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

    if progress_callback:
        progress_callback(100, f"MDT exportado: {os.path.basename(output_path)}")

    return output_path


# ─────────────────────────────────────────────────────────────────────────────
#  Suavizado de curvas (Chaikin)
# ─────────────────────────────────────────────────────────────────────────────

def _chaikin_smooth(pts, iterations=2):
    """
    Suavizado de Chaikin: en cada iteración reemplaza cada segmento por
    dos puntos al 25% y 75% del mismo. Conserva los extremos de la polilínea.
    Rápido, sin dependencias externas y produce curvas muy parecidas a las
    de programas profesionales.
    """
    closed = all((
        len(pts) >= 2,
        abs(pts[0][0] - pts[-1][0]) < 1e-6,
        abs(pts[0][1] - pts[-1][1]) < 1e-6,
    ))

    for _ in range(iterations):
        new_pts = []
        n = len(pts)
        if closed:
            # Para curvas cerradas tratamos el anillo completo
            for i in range(n - 1):
                p0 = pts[i]
                p1 = pts[(i + 1) % n]
                new_pts.append((0.75 * p0[0] + 0.25 * p1[0],
                                0.75 * p0[1] + 0.25 * p1[1]))
                new_pts.append((0.25 * p0[0] + 0.75 * p1[0],
                                0.25 * p0[1] + 0.75 * p1[1]))
            new_pts.append(new_pts[0])  # cerrar
        else:
            # Para curvas abiertas conservamos primer y último punto
            new_pts.append(pts[0])
            for i in range(n - 1):
                p0 = pts[i]
                p1 = pts[i + 1]
                new_pts.append((0.75 * p0[0] + 0.25 * p1[0],
                                0.75 * p0[1] + 0.25 * p1[1]))
                new_pts.append((0.25 * p0[0] + 0.75 * p1[0],
                                0.25 * p0[1] + 0.75 * p1[1]))
            new_pts.append(pts[-1])
        pts = new_pts
    return pts


# ─────────────────────────────────────────────────────────────────────────────
#  Curvas de nivel → DXF
# ─────────────────────────────────────────────────────────────────────────────

def export_curvas_nivel(
    geotiff_path,
    output_dxf_path,
    equidistancia=1.0,
    equidistancia_maestra=5.0,
    smooth_iterations=2,
    min_longitud=30.0,
    progress_callback=None,
):
    """
    Genera curvas de nivel (normales y maestras) a partir del GeoTIFF del
    MDT con buffer y las exporta a DXF.

    Parámetros
    ----------
    geotiff_path          : str   — GeoTIFF de entrada
    output_dxf_path       : str   — DXF de salida
    equidistancia         : float — equidistancia de curvas normales (m)
    equidistancia_maestra : float — equidistancia de curvas maestras (m)
    smooth_iterations     : int   — iteraciones de suavizado Chaikin (0 = sin suavizar)
    min_longitud          : float — longitud mínima (m) de una curva para exportarla;
                                    las curvas cerradas o abiertas más cortas se
                                    descartan para evitar minicurvas antiestéticas.
                                    Valor 0 = exportar todas (sin filtro).
    progress_callback     : callable(pct, msg)
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF no encontrado: {geotiff_path}")

    if progress_callback:
        progress_callback(5, "Abriendo MDT para curvas de nivel...")

    ds = gdal.Open(geotiff_path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"No se pudo abrir el GeoTIFF: {geotiff_path}")

    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    projection = ds.GetProjection()

    if progress_callback:
        progress_callback(15, "Calculando rango de cotas...")

    stats = band.GetStatistics(True, True)
    z_min, z_max = stats[0], stats[1]

    if z_min is None or z_max is None or z_max <= z_min:
        raise ValueError("No se pudieron obtener estadísticas del MDT.")

    if progress_callback:
        progress_callback(25, f"Generando curvas {equidistancia}m (maestras {equidistancia_maestra}m)...")

    # Niveles a generar
    base = math.floor(z_min / equidistancia) * equidistancia
    levels = []
    z = base
    while z <= z_max + equidistancia * 0.01:
        levels.append(round(z, 8))
        z += equidistancia
    if not levels:
        raise ValueError("No se generaron niveles de curvas de nivel.")

    # ── ezdxf ────────────────────────────────────────────────────────────────
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

    doc = ezdxf.new('R2010', setup=True)
    msp = doc.modelspace()

    for lname, color, lw in [
        ('CURVAS_NORMALES', 3, 13),
        ('CURVAS_MAESTRAS', 1, 40),
        ('CURVAS_TEXTOS',   7,  0),
    ]:
        lay = doc.layers.new(lname)
        lay.color = color
        lay.lineweight = lw

    # ── SRS para OGR ─────────────────────────────────────────────────────────
    srs = osr.SpatialReference()
    if projection:
        try:
            srs.ImportFromWkt(projection)
        except Exception:
            pass

    if progress_callback:
        progress_callback(30, "Calculando curvas de nivel (ContourGenerate)...")

    mem_driver = ogr.GetDriverByName('Memory')

    n_levels = len(levels)
    for i, level in enumerate(levels):
        if progress_callback and i % max(1, n_levels // 30) == 0:
            progress_callback(
                30 + int(i / n_levels * 55),
                f"Curva {level:.2f} m ({i + 1}/{n_levels})..."
            )

        nearest_diff = abs(
            round(level / equidistancia_maestra) * equidistancia_maestra - level
        )
        is_maestra = nearest_diff < equidistancia * 0.01
        dxf_layer = 'CURVAS_MAESTRAS' if is_maestra else 'CURVAS_NORMALES'
        color = 1 if is_maestra else 3

        # ContourGenerate sobre un layer temporal en memoria
        tmp_ds = mem_driver.CreateDataSource('tmp')
        tmp_lyr = tmp_ds.CreateLayer('tmp', srs=srs, geom_type=ogr.wkbLineString)
        tmp_lyr.CreateField(ogr.FieldDefn('ID', ogr.OFTInteger))
        tmp_lyr.CreateField(ogr.FieldDefn('ELEV', ogr.OFTReal))

        gdal.ContourGenerate(
            band,
            0,        # contourInterval — no usar, preferimos fixedLevels
            0,        # contourBase
            [level],  # fixedLevels
            1 if nodata is not None else 0,
            nodata or 0.0,
            tmp_lyr,
            0,  # idField
            1,  # elevField
        )

        tmp_lyr.ResetReading()
        for feat in tmp_lyr:
            geom = feat.GetGeometryRef()
            if geom is None:
                continue

            def _add_geom(g):
                np_ = g.GetPointCount()
                if np_ < 2:
                    return
                pts = [(g.GetX(k), g.GetY(k)) for k in range(np_)]

                # ── Filtro de longitud mínima ─────────────────────────────
                # Se calcula la longitud real de la polilínea ANTES del
                # suavizado (el suavizado no cambia la longitud de forma
                # significativa). Las curvas cerradas muy pequeñas (islotes
                # de cota) quedan descartadas si son < min_longitud metros.
                if min_longitud > 0:
                    import math as _math
                    lon = sum(
                        _math.hypot(pts[k+1][0]-pts[k][0], pts[k+1][1]-pts[k][1])
                        for k in range(len(pts)-1)
                    )
                    if lon < min_longitud:
                        return

                # Suavizado Chaikin
                if smooth_iterations > 0:
                    pts = _chaikin_smooth(pts, smooth_iterations)

                msp.add_lwpolyline(
                    pts,
                    dxfattribs={'layer': dxf_layer, 'color': color}
                )
                # Etiqueta cota en maestras
                if is_maestra:
                    mi = len(pts) // 2
                    mx, my = pts[mi]
                    t_elev = msp.add_text(
                        f"{level:.1f}",
                        dxfattribs={
                            'height': 1.5,
                            'layer': 'CURVAS_TEXTOS',
                            'color': 1,
                        }
                    )
                    t_elev.set_placement((mx, my), align=TEA.MIDDLE_CENTER)

            gt_flat = ogr.GT_Flatten(geom.GetGeometryType())
            if gt_flat == ogr.wkbLineString:
                _add_geom(geom)
            elif gt_flat == ogr.wkbMultiLineString:
                for si in range(geom.GetGeometryCount()):
                    _add_geom(geom.GetGeometryRef(si))

        tmp_ds = None

    ds = None

    if progress_callback:
        progress_callback(97, "Guardando DXF de curvas de nivel...")

    doc.saveas(output_dxf_path)

    if progress_callback:
        progress_callback(100, f"Curvas exportadas: {os.path.basename(output_dxf_path)}")

    return output_dxf_path
