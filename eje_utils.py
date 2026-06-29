# -*- coding: utf-8 -*-
"""
eje_utils.py
Lectura del eje DXF, planchado sobre MDT y segmentación.
"""

import math
import os

try:
    from osgeo import gdal, ogr, osr
    gdal.UseExceptions()
except ImportError:
    raise ImportError("GDAL/OGR no disponible.")


# ─────────────────────────────────────────────────────────────────────────────
#  LECTURA DEL EJE — multi-formato con reproyección automática
# ─────────────────────────────────────────────────────────────────────────────

# Tipos de geometría lineal que OGR puede devolver
_LINEAR_TYPES = (
    ogr.wkbLineString, ogr.wkbLineString25D,
    ogr.wkbMultiLineString, ogr.wkbMultiLineString25D,
    ogr.wkbLinearRing,
)

# Drivers a probar por extensión cuando ogr.Open falla
_DRIVER_BY_EXT = {
    '.kml': 'KML',
    '.kmz': 'LIBKML',
    '.gpx': 'GPX',
    '.shp': 'ESRI Shapefile',
    '.gpkg': 'GPKG',
    '.gml': 'GML',
    '.geojson': 'GeoJSON',
    '.json': 'GeoJSON',
    '.dxf': 'DXF',
}


def _open_datasource(path):
    """
    Abre un datasource OGR probando primero ogr.Open y luego el driver
    específico de la extensión. Para KMZ (ZIP) descomprime en memoria.
    """
    ext = os.path.splitext(path)[1].lower()

    # KMZ → descomprimir y tratar como KML en memoria
    if ext == '.kmz':
        import zipfile
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix='perfil_kmz_')
        with zipfile.ZipFile(path, 'r') as zf:
            zf.extractall(tmp_dir)
        # Buscar el .kml raíz
        for root, _, files in os.walk(tmp_dir):
            for f in files:
                if f.lower().endswith('.kml'):
                    kml_path = os.path.join(root, f)
                    ds = ogr.Open(kml_path)
                    if ds:
                        return ds
                    drv = ogr.GetDriverByName('KML')
                    if drv:
                        ds = drv.Open(kml_path)
                        if ds:
                            return ds
        raise ValueError(f"No se encontró ningún .kml dentro del KMZ: {path}")

    # Intento 1: ogr.Open genérico
    ds = ogr.Open(path)
    if ds:
        return ds

    # Intento 2: driver específico por extensión
    drv_name = _DRIVER_BY_EXT.get(ext)
    if drv_name:
        drv = ogr.GetDriverByName(drv_name)
        if drv:
            ds = drv.Open(path)
            if ds:
                return ds

    # Intento 3: probar todos los drivers registrados
    for i in range(ogr.GetDriverCount()):
        drv = ogr.GetDriver(i)
        try:
            ds = drv.Open(path)
            if ds and ds.GetLayerCount() > 0:
                return ds
        except Exception:
            pass

    raise ValueError(
        f"No se puede abrir el archivo de eje: {path}\n"
        f"Formato no reconocido o archivo corrupto."
    )


def _get_srs_from_ds(ds):
    """Devuelve el SRS del primer layer con SRS definido, o None."""
    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayerByIndex(i)
        srs = lyr.GetSpatialRef()
        if srs:
            return srs
    return None


def _get_mdt_srs(mdt_paths):
    """Lee el SRS del primer MDT disponible."""
    if not mdt_paths:
        return None
    try:
        ds = gdal.Open(mdt_paths[0], gdal.GA_ReadOnly)
    except Exception:
        return None
    if not ds:
        return None
    wkt = ds.GetProjection()
    ds = None
    if not wkt:
        return None
    try:
        srs = osr.SpatialReference()
        srs.ImportFromWkt(wkt)
    except Exception:
        # WKT presente pero corrupto/no reconocido por GDAL/OGR: se trata
        # como si el MDT no tuviera CRS (en vez de interrumpir el proceso).
        return None
    return srs


def _needs_reproject(axis_srs, mdt_srs):
    """True si los SRS son distintos (ej: WGS84 vs UTM).

    AutoIdentifyEPSG() e IsSame() pueden lanzar una excepción de GDAL/OGR
    ("Unsupported SRS") cuando el MDT usa una proyección local, personalizada
    o sin código EPSG reconocible (frecuente en MDTs topográficos). En ese
    caso no debe romperse todo el proceso: simplemente se ignora el fallo de
    identificación y, si ni siquiera se pueden comparar, se asume de forma
    conservadora que SÍ hace falta reproyectar (para no comparar a ciegas
    dos definiciones que GDAL no ha podido verificar).
    """
    if axis_srs is None or mdt_srs is None:
        return False
    try:
        axis_srs.AutoIdentifyEPSG()
    except Exception:
        pass
    try:
        mdt_srs.AutoIdentifyEPSG()
    except Exception:
        pass
    try:
        return not axis_srs.IsSame(mdt_srs)
    except Exception:
        return True


def _get_sample_point(ds):
    """
    Devuelve un punto (x, y) de ejemplo de la primera geometría lineal
    encontrada en el datasource, o None si no hay ninguna.
    Se usa solo para comprobar si el SRS declarado es plausible.
    """
    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayerByIndex(i)
        lyr.ResetReading()
        sample = None
        for feat in lyr:
            geom = feat.GetGeometryRef()
            if geom is None:
                continue
            g = geom
            while g.GetGeometryCount() > 0:
                g = g.GetGeometryRef(0)
            if g.GetPointCount() > 0:
                sample = (g.GetX(0), g.GetY(0))
                break
        lyr.ResetReading()
        if sample is not None:
            return sample
    return None


def _axis_srs_is_plausible(ds, axis_srs):
    """
    Comprueba que las coordenadas reales del archivo son compatibles con el
    SRS que el driver de OGR le ha asignado.

    Algunos formatos (sobre todo GeoJSON sin miembro "crs") hacen que OGR
    asuma WGS84 (geográfico, en grados) aunque el archivo en realidad
    contenga coordenadas ya proyectadas (metros, UTM...). Si se intenta
    reproyectar esas coordenadas como si fueran longitud/latitud, PROJ
    lanza errores como "tmerc: Invalid latitude". Esta función detecta
    ese caso para poder ignorar el SRS declarado y tratar el eje como si
    ya estuviera en el CRS del MDT.
    """
    if axis_srs is None:
        return True
    try:
        is_geographic = bool(axis_srs.IsGeographic())
    except Exception:
        return True
    if not is_geographic:
        return True  # Proyectado: cualquier rango de valores es válido

    sample = _get_sample_point(ds)
    if sample is None:
        return True
    sx, sy = sample
    return -180.0 <= sx <= 180.0 and -90.0 <= sy <= 90.0


def _extract_linestring_points(geom, transform=None):
    """Extrae puntos de cualquier geometría lineal, con reproyección opcional."""
    gtype = geom.GetGeometryType()
    # Aplanar tipo (quitar Z, M, ZM del tipo)
    gtype_flat = ogr.GT_Flatten(gtype)

    if gtype_flat == ogr.wkbMultiLineString:
        pts = []
        for i in range(geom.GetGeometryCount()):
            pts.extend(
                _extract_linestring_points(
                    geom.GetGeometryRef(i),
                    transform))
        return pts

    if gtype_flat in (ogr.wkbLineString, ogr.wkbLinearRing):
        if transform:
            clone = geom.Clone()
            try:
                clone.Transform(transform)
                geom = clone
            except Exception:
                # La transformación ha fallado (p.ej. PROJ: "Invalid latitude"
                # porque el SRS declarado no coincide con las coordenadas
                # reales). Se usan las coordenadas originales sin transformar:
                # lo más probable es que el eje ya esté en el CRS del MDT.
                pass
        return [(geom.GetX(i), geom.GetY(i))
                for i in range(geom.GetPointCount())]

    # GeometryCollection u otros: recorrer sub-geometrías
    if geom.GetGeometryCount() > 0:
        pts = []
        for i in range(geom.GetGeometryCount()):
            pts.extend(
                _extract_linestring_points(
                    geom.GetGeometryRef(i),
                    transform))
        return pts

    return []


def read_axis_from_dxf(axis_path, mdt_paths=None):
    """
    Lee el eje vectorial de cualquier formato soportado por OGR.
    Reproyecta automáticamente al CRS del MDT si son distintos
    (ej: eje en WGS84/KML → MDT en UTM).

    Parámetros
    ----------
    axis_path : str  – ruta al archivo de eje
    mdt_paths : list[str] – opcional, rutas de los MDTs para detectar CRS destino

    Devuelve lista de (x, y) en el CRS del MDT.
    """
    ds = _open_datasource(axis_path)

    # SRS del eje
    axis_srs = _get_srs_from_ds(ds)

    # Si el SRS declarado no es plausible para las coordenadas reales
    # (p.ej. GeoJSON "WGS84 por defecto" con coordenadas ya proyectadas),
    # se ignora para no intentar reproyectar con datos incoherentes.
    if not _axis_srs_is_plausible(ds, axis_srs):
        axis_srs = None

    # SRS destino (MDT)
    mdt_srs = _get_mdt_srs(mdt_paths) if mdt_paths else None

    # Transformación si hace falta
    transform = None
    reprojected = False
    if axis_srs and mdt_srs and _needs_reproject(axis_srs, mdt_srs):
        try:
            axis_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            mdt_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            transform = osr.CoordinateTransformation(axis_srs, mdt_srs)
            reprojected = True
        except Exception:
            # No se pudo construir la transformación (CRS no soportado por
            # PROJ/GDAL). Se continúa sin reproyectar; si los CRS realmente
            # son distintos, el plugin avisará más adelante de que ningún
            # MDT intersecta con el eje.
            transform = None
            reprojected = False

    # GPX: las rutas lineales están en layer "tracks" o "routes"
    ext = os.path.splitext(axis_path)[1].lower()
    preferred_layers = []
    if ext == '.gpx':
        preferred_layers = ['tracks', 'routes', 'track_points']

    vertices = []

    def _scan_layer(layer):
        nonlocal vertices
        layer.ResetReading()
        for feat in layer:
            geom = feat.GetGeometryRef()
            if geom is None:
                continue
            pts = _extract_linestring_points(geom, transform)
            if len(pts) > len(vertices):
                vertices = pts

    # Primero layers preferidos, luego el resto
    scanned = set()
    for name in preferred_layers:
        lyr = ds.GetLayerByName(name)
        if lyr:
            _scan_layer(lyr)
            scanned.add(name)

    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayerByIndex(i)
        if lyr.GetName() not in scanned:
            _scan_layer(lyr)

    ds = None

    if not vertices:
        raise ValueError(
            f"No se encontró ningún eje lineal en: {os.path.basename(axis_path)}\n\n"
            f"Formatos soportados: DXF, SHP, KML, KMZ, GeoPackage, GML, GPX, GeoJSON.\n"
            f"El archivo debe contener al menos una geometría de tipo línea o polilínea."
        )

    if reprojected:
        import warnings
        warnings.warn(
            "El eje ha sido reproyectado automáticamente al CRS del MDT.",
            stacklevel=2
        )

    return vertices


def get_axis_bbox(vertices_2d):
    """Devuelve (xmin, ymin, xmax, ymax) del eje."""
    xs = [p[0] for p in vertices_2d]
    ys = [p[1] for p in vertices_2d]
    return min(xs), min(ys), max(xs), max(ys)


def read_all_axes_from_file(axis_path, mdt_paths=None):
    """
    Lee TODAS las geometrías lineales del archivo y las devuelve como lista
    de listas de vértices (x, y), una por eje detectado.

    Si el archivo tiene 1 sola polilínea devuelve [[v1, v2, ...]].
    Si tiene 3 polilíneas devuelve [[...], [...], [...]].

    Cada lista de vértices se ordena por longitud descendente (el más largo
    primero), aunque se devuelven todos.

    Parámetros
    ----------
    axis_path : str
    mdt_paths : list[str], opcional — para reproyección automática WGS84→UTM

    Devuelve lista de listas [(x,y), ...]
    """
    ds = _open_datasource(axis_path)
    axis_srs = _get_srs_from_ds(ds)

    # Si el SRS declarado no es plausible para las coordenadas reales
    # (p.ej. GeoJSON "WGS84 por defecto" con coordenadas ya proyectadas),
    # se ignora para no intentar reproyectar con datos incoherentes.
    if not _axis_srs_is_plausible(ds, axis_srs):
        axis_srs = None

    mdt_srs = _get_mdt_srs(mdt_paths) if mdt_paths else None

    transform = None
    if axis_srs and mdt_srs and _needs_reproject(axis_srs, mdt_srs):
        try:
            axis_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            mdt_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            transform = osr.CoordinateTransformation(axis_srs, mdt_srs)
        except Exception:
            # CRS no soportado por PROJ/GDAL para construir la transformación.
            # Se continúa sin reproyectar; si los CRS realmente son distintos,
            # el plugin avisará más adelante de que ningún MDT intersecta.
            transform = None

    ext = os.path.splitext(axis_path)[1].lower()
    preferred_layers = ['tracks', 'routes',
                        'track_points'] if ext == '.gpx' else []

    all_axes = []  # lista de listas de (x, y)

    def _scan_layer_all(layer):
        layer.ResetReading()
        for feat in layer:
            geom = feat.GetGeometryRef()
            if geom is None:
                continue
            gtype_flat = ogr.GT_Flatten(geom.GetGeometryType())
            if gtype_flat == ogr.wkbMultiLineString:
                # Cada sub-geometría es un eje independiente
                for i in range(geom.GetGeometryCount()):
                    sub = geom.GetGeometryRef(i)
                    pts = _extract_linestring_points(sub, transform)
                    if len(pts) >= 2:
                        all_axes.append(pts)
            else:
                pts = _extract_linestring_points(geom, transform)
                if len(pts) >= 2:
                    all_axes.append(pts)

    scanned = set()
    for name in preferred_layers:
        lyr = ds.GetLayerByName(name)
        if lyr:
            _scan_layer_all(lyr)
            scanned.add(name)

    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayerByIndex(i)
        if lyr.GetName() not in scanned:
            _scan_layer_all(lyr)

    ds = None

    if not all_axes:
        raise ValueError(
            f"No se encontró ningún eje lineal en: {
                os.path.basename(axis_path)}")

    # Ordenar por longitud (mayor primero) — así perfil1 es el más largo
    def _axis_len(verts):
        return sum(math.hypot(verts[i + 1][0] - verts[i][0],
                              verts[i + 1][1] - verts[i][1])
                   for i in range(len(verts) - 1))

    all_axes.sort(key=_axis_len, reverse=True)
    return all_axes


# ─────────────────────────────────────────────
#  PLANCHADO DE VÉRTICES SOBRE EL MDT
# ─────────────────────────────────────────────

class MDTSampler:
    """Muestrea cotas de uno o varios GeoTIFs con solapamiento."""

    def __init__(self, mdt_paths):
        self._datasets = []
        for p in mdt_paths:
            ds = gdal.Open(p, gdal.GA_ReadOnly)
            if ds:
                gt = ds.GetGeoTransform()
                cols = ds.RasterXSize
                rows = ds.RasterYSize
                nodata = ds.GetRasterBand(1).GetNoDataValue()
                self._datasets.append({
                    "ds": ds,
                    "gt": gt,
                    "cols": cols,
                    "rows": rows,
                    "nodata": nodata,
                    "xmin": gt[0],
                    "ymax": gt[3],
                    "xmax": gt[0] + gt[1] * cols,
                    "ymin": gt[3] + gt[5] * rows,
                })

    def sample(self, x, y):
        """
        Devuelve la cota Z en (x, y) usando interpolación bilineal
        entre los 4 píxeles vecinos del raster.

        La interpolación bilineal elimina el efecto de «dientes de sierra»
        que produce la lectura de vecino más cercano cuando la resolución
        del MDT es mayor que el intervalo de segmentación del eje.
        """
        for d in self._datasets:
            gt = d["gt"]
            xmin, xmax = d["xmin"], d["xmax"]
            ymin, ymax = d["ymin"], d["ymax"]
            if not (xmin <= x <= xmax and ymin <= y <= ymax):
                continue

            # Posición fraccionaria dentro del raster
            col_f = (x - gt[0]) / gt[1] - 0.5
            row_f = (y - gt[3]) / gt[5] - 0.5

            col0 = int(math.floor(col_f))
            row0 = int(math.floor(row_f))
            col1 = col0 + 1
            row1 = row0 + 1

            # Pesos bilineales
            tc = col_f - col0   # fracción columna (0–1)
            tr = row_f - row0   # fracción fila    (0–1)

            cols = d["cols"]
            rows = d["rows"]
            nodata = d["nodata"]
            band = d["ds"].GetRasterBand(1)

            def _read(c, r):
                """Lee un píxel con clamping a bordes."""
                c = max(0, min(c, cols - 1))
                r = max(0, min(r, rows - 1))
                data = band.ReadAsArray(c, r, 1, 1)
                if data is None:
                    return None
                v = float(data[0][0])
                if nodata is not None and abs(v - nodata) < 1e-3:
                    return None
                return v

            z00 = _read(col0, row0)
            z10 = _read(col1, row0)
            z01 = _read(col0, row1)
            z11 = _read(col1, row1)

            # Si todos los vecinos son válidos → bilineal completo
            if all(z is not None for z in (z00, z10, z01, z11)):
                z = (z00 * (1 - tc) * (1 - tr) + z10 * tc * (1 - tr) + z01 * (1 - tc) * tr + z11 * tc * tr)
                return z

            # Algún vecino es NoData → bilineal sólo con los válidos
            pairs = [(z00, (1 - tc) * (1 - tr)), (z10, tc * (1 - tr)),
                     (z01, (1 - tc) * tr), (z11, tc * tr)]
            valid = [(v, w) for v, w in pairs if v is not None]
            if not valid:
                continue
            total_w = sum(w for _, w in valid)
            if total_w < 1e-9:
                continue
            return sum(v * w for v, w in valid) / total_w

        return None

    def close(self):
        for d in self._datasets:
            d["ds"] = None


# ─────────────────────────────────────────────
#  SEGMENTACIÓN DEL EJE
# ─────────────────────────────────────────────

def segment_axis(vertices_2d, interval):
    """
    Segmenta el eje en puntos separados 'interval' metros.
    Los vértices originales se insertan EXACTAMENTE en su posición real,
    sin redondear ni moverlos al punto de intervalo más cercano.

    Devuelve:
      segmented       : lista de (x, y, dist_acum)
      original_indices: índices en segmented de los vértices originales
    """
    if interval <= 0:
        raise ValueError("El intervalo de segmentación debe ser mayor que 0.")

    segmented = []   # (x, y, dist_acum)
    original_indices = []

    dist_acum = 0.0
    dist_since_last = 0.0  # distancia desde el último punto de intervalo emitido

    # Primer vértice
    segmented.append((vertices_2d[0][0], vertices_2d[0][1], 0.0))
    original_indices.append(0)

    for i in range(1, len(vertices_2d)):
        x0, y0 = vertices_2d[i - 1]
        x1, y1 = vertices_2d[i]
        seg_len = math.hypot(x1 - x0, y1 - y0)

        if seg_len == 0:
            continue

        dx = (x1 - x0) / seg_len
        dy = (y1 - y0) / seg_len

        remaining = seg_len
        pos_in_seg = 0.0   # posición dentro de este segmento

        # Emitir puntos de intervalo que caigan dentro de este segmento
        while dist_since_last + remaining >= interval:
            step = interval - dist_since_last
            pos_in_seg += step
            remaining -= step
            dist_acum += step
            dist_since_last = 0.0
            xi = x0 + pos_in_seg * dx
            yi = y0 + pos_in_seg * dy
            segmented.append((xi, yi, dist_acum))

        dist_acum += remaining
        dist_since_last += remaining

        # Insertar el vértice original exacto al final de este segmento
        # Solo si es diferente al último punto emitido (evitar duplicados)
        last = segmented[-1]
        if math.hypot(last[0] - x1, last[1] - y1) > 1e-6:
            segmented.append((x1, y1, dist_acum))

        # Registrar el índice de este vértice original (solo intermedios por ahora;
        # el primero ya está, el último se añade después)
        if i < len(vertices_2d) - 1:
            original_indices.append(len(segmented) - 1)

    # Último vértice original
    original_indices.append(len(segmented) - 1)

    original_indices = sorted(set(original_indices))
    return segmented, original_indices


# ─────────────────────────────────────────────
#  PLANCHADO COMPLETO
# ─────────────────────────────────────────────

def drape_points(points_2d_dist, sampler, progress_callback=None):
    """
    Plancha una lista de (x, y, dist) sobre el MDT.
    Devuelve lista de (x, y, z, dist). Los puntos sin cota quedan con z=None.
    """
    result = []
    n = len(points_2d_dist)
    for i, (x, y, dist) in enumerate(points_2d_dist):
        z = sampler.sample(x, y)
        result.append((x, y, z, dist))
        if progress_callback and i % 100 == 0:
            progress_callback(int(i / n * 100))
    return result


def interpolate_missing_z(points_3d):
    """
    Interpola linealmente los valores Z faltantes (None).
    """
    pts = list(points_3d)
    n = len(pts)

    # Propagar desde el primer punto válido hacia atrás
    first_valid = next(
        (i for i, p in enumerate(pts) if p[2] is not None), None)
    last_valid = next((i for i, p in enumerate(
        reversed(pts)) if p[2] is not None), None)

    if first_valid is None:
        raise ValueError(
            "No se pudo obtener ninguna cota del MDT para el eje.")

    # Rellenar inicio
    for i in range(first_valid):
        pts[i] = (pts[i][0], pts[i][1], pts[first_valid][2], pts[i][3])

    # Rellenar fin
    for i in range(n - 1, n - 1 - (last_valid or 0), -1):
        pts[i] = (pts[i][0],
                  pts[i][1],
                  pts[n - 1 - (last_valid or 0)][2],
                  pts[i][3])

    # Interpolar intermedios
    i = 0
    while i < n:
        if pts[i][2] is None:
            j = i + 1
            while j < n and pts[j][2] is None:
                j += 1
            if j < n:
                z0 = pts[i - 1][2]
                z1 = pts[j][2]
                d0 = pts[i - 1][3]
                d1 = pts[j][3]
                for k in range(i, j):
                    t = (pts[k][3] - d0) / (d1 - d0) if d1 != d0 else 0
                    zi = z0 + t * (z1 - z0)
                    pts[k] = (pts[k][0], pts[k][1], zi, pts[k][3])
        i += 1

    return pts


# ─────────────────────────────────────────────────────────────────────────────
#  EXPORTACIÓN EJE 3D A DXF (usando ezdxf para máxima compatibilidad)
# ─────────────────────────────────────────────────────────────────────────────

def export_axis_3d_dxf(points_3d, output_path, equidistant_interval=0.0):
    """Exporta UN eje 3D a DXF. Wrapper de compatibilidad."""
    export_all_axes_3d_dxf([('Eje', points_3d)], output_path,
                           equidistant_interval=equidistant_interval)


# Tamaños por defecto (metros reales, no de papel) de las marcas y textos
# que se dibujan en los vértices originales del eje 3D.
_EJE3D_MARK_SIZE = 0.5
_EJE3D_TEXT_HEIGHT = 1.2


def _vertex_tangent(coords, i):
    """
    Dirección unitaria aproximada (ux, uy) en el vértice i de una polilínea
    de coordenadas (x, y, z). Usa el vértice anterior y el siguiente cuando
    existen, o el único segmento disponible en los extremos.
    """
    n = len(coords)
    if n < 2:
        return 1.0, 0.0
    if i == 0:
        p0, p1 = coords[0], coords[1]
    elif i == n - 1:
        p0, p1 = coords[-2], coords[-1]
    else:
        p0, p1 = coords[i - 1], coords[i + 1]
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 1.0, 0.0
    return dx / length, dy / length


def _format_pk(dist):
    """
    Formatea una distancia acumulada (m) como PK estándar de topografía:
    kilómetros '+' metros con 3 dígitos, p.ej.:
      0.0      -> '0+000'
      1150.0   -> '1+150'
      1150.45  -> '1+150.45'  (si tiene decimales se muestran con 2 dígitos)
    """
    if dist is None:
        dist = 0.0
    if dist < 0:
        dist = 0.0
    km = int(dist // 1000)
    m = dist - km * 1000
    if abs(m - round(m)) < 1e-6:
        return f"{km}+{int(round(m)):03d}"
    return f"{km}+{m:06.2f}"


def resample_axis_3d_equidistant(pts_3d, interval, sampler):
    """
    Genera una polilínea 3D que combina los vértices ORIGINALES del eje con
    puntos equidistantes intermedios, todos planchados sobre el MDT.

    Los vértices originales se conservan SIEMPRE (son los quiebros reales del
    trazado). Entre ellos se intercalan puntos a 'interval' metros para dar
    densidad a la polilínea exportada. Así la geometría de la línea 3D respeta
    el trazado en planta y no introduce desviaciones.

    pts_3d  : lista de (x, y, z, dist) — eje ya planchado con todos los puntos
    interval: float — equidistancia adicional entre vértices originales (m)
    sampler : MDTSampler — para obtener Z real en los nuevos puntos

    Devuelve lista de (x, y, z) lista para add_polyline3d.
    """
    if not pts_3d or interval <= 0:
        return [(x, y, z if z is not None else 0.0) for x, y, z, _ in pts_3d]

    total_dist = pts_3d[-1][3]

    # Construir conjunto de distancias a incluir:
    # 1) Todos los vértices originales de pts_3d (cambios de dirección reales)
    # 2) Puntos a equidistancia regular (0, interval, 2*interval, ...)
    dist_set = set()

    # Vértices originales: son los que marcan los segmentos del eje
    # pts_3d ya contiene tanto los vértices originales como los puntos
    # de segmentación fina. Para recuperar solo los vértices originales
    # (quiebros del trazado), los identificamos por cambio de dirección.
    # Como pts_3d ya viene con vértices originales preservados (segment_axis
    # los inserta exactamente), los incluimos todos — la densidad no perjudica.
    orig_dists = [p[3] for p in pts_3d]
    for d in orig_dists:
        dist_set.add(round(d, 6))

    # Puntos equidistantes
    next_d = 0.0
    while next_d <= total_dist + 1e-6:
        dist_set.add(round(next_d, 6))
        next_d += interval

    sorted_dists = sorted(dist_set)

    # Interpolar XY en cada distancia y muestrear Z en el MDT
    result = []
    n = len(pts_3d)
    j = 1  # índice de avance en pts_3d

    for target_d in sorted_dists:
        if target_d > total_dist + 1e-6:
            break
        # Avanzar j hasta el segmento que contiene target_d
        while j < n and pts_3d[j][3] < target_d - 1e-9:
            j += 1

        if j >= n:
            # Más allá del final: usar el último punto
            pf = pts_3d[-1]
            zf = sampler.sample(pf[0], pf[1])
            result.append((pf[0], pf[1], zf if zf is not None else (pf[2] or 0.0)))
            break

        p_prev = pts_3d[j - 1] if j > 0 else pts_3d[0]
        p_cur = pts_3d[j]
        d0_seg = p_prev[3]
        d1_seg = p_cur[3]

        if abs(d1_seg - d0_seg) < 1e-9:
            xi, yi = p_cur[0], p_cur[1]
        else:
            t = (target_d - d0_seg) / (d1_seg - d0_seg)
            t = max(0.0, min(1.0, t))
            xi = p_prev[0] + t * (p_cur[0] - p_prev[0])
            yi = p_prev[1] + t * (p_cur[1] - p_prev[1])

        zi = sampler.sample(xi, yi)
        if zi is None:
            # Fallback: interpolar Z del perfil
            if abs(d1_seg - d0_seg) < 1e-9:
                zi = p_cur[2] or 0.0
            else:
                t = (target_d - d0_seg) / (d1_seg - d0_seg)
                t = max(0.0, min(1.0, t))
                zi = (p_prev[2] or 0.0) + t * ((p_cur[2] or 0.0) - (p_prev[2] or 0.0))

        result.append((xi, yi, zi))

    # Eliminar duplicados consecutivos muy próximos (pueden aparecer cuando
    # un vértice original coincide exactamente con un múltiplo de interval)
    clean = [result[0]] if result else []
    for pt in result[1:]:
        last = clean[-1]
        if math.hypot(pt[0] - last[0], pt[1] - last[1]) > 1e-6:
            clean.append(pt)

    return clean


def _dist_tangent(pts_3d, target_dist):
    """
    Dirección unitaria aproximada (ux, uy) del eje en una distancia
    acumulada arbitraria 'target_dist' (no necesariamente un vértice),
    usando el segmento de pts_3d que la contiene.
    """
    n = len(pts_3d)
    if n < 2:
        return 1.0, 0.0
    for i in range(1, n):
        d0, d1 = pts_3d[i - 1][3], pts_3d[i][3]
        if d0 <= target_dist <= d1 or i == n - 1:
            dx = pts_3d[i][0] - pts_3d[i - 1][0]
            dy = pts_3d[i][1] - pts_3d[i - 1][1]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                return 1.0, 0.0
            return dx / length, dy / length
    return 1.0, 0.0


def _equidistant_pk_points(pts_3d, interval, sampler, tol=0.05):
    """
    Genera puntos (x, y, z, dist) a equidistancia regular 'interval' a lo
    largo del eje (PK redondos: 0+100, 0+200...), EXCLUYENDO el origen y
    el final del eje y cualquier PK que caiga muy cerca de un vértice
    original (ambos ya quedan cubiertos por las marcas V1...Vn, así que
    aquí no se duplican).
    """
    if not pts_3d or interval <= 0 or sampler is None:
        return []

    total_dist = pts_3d[-1][3]
    orig_dists = [p[3] for p in pts_3d]
    n = len(pts_3d)
    result = []
    next_d = interval
    i = 1
    while next_d < total_dist - 1e-6:
        if any(abs(next_d - od) < tol for od in orig_dists):
            next_d += interval
            continue
        while i < n and pts_3d[i][3] < next_d - 1e-9:
            i += 1
        if i >= n:
            break
        p_prev = pts_3d[i - 1]
        p_cur = pts_3d[i]
        d0_seg, d1_seg = p_prev[3], p_cur[3]
        t = (next_d - d0_seg) / (d1_seg - d0_seg) if d1_seg > d0_seg else 0.0
        xi = p_prev[0] + t * (p_cur[0] - p_prev[0])
        yi = p_prev[1] + t * (p_cur[1] - p_prev[1])
        zi = sampler.sample(xi, yi)
        if zi is None:
            zi = (p_prev[2] or 0.0) + t * ((p_cur[2] or 0.0) - (p_prev[2] or 0.0))
        result.append((xi, yi, zi, next_d))
        next_d += interval
    return result


def export_all_axes_3d_dxf(axes_list, output_path, equidistant_interval=0.0,
                           sampler=None, mark_size=_EJE3D_MARK_SIZE,
                           text_height=_EJE3D_TEXT_HEIGHT,
                           clean_equidistant=False):
    """
    Exporta VARIOS ejes 3D planchados a un único DXF de planta.

    Modos:
    - clean_equidistant=True   → conserva los vértices ORIGINALES del eje
                                  (quiebros reales del trazado) e intercala
                                  además puntos cada 'equidistant_interval'
                                  metros, todos planchados sobre el MDT.
                                  Polilínea limpia (sin texto ni marcas).
                                  Requiere 'sampler'.
    - clean_equidistant=False  → vértices originales planchados, CON marcas
                                  (cruz 3D) y texto "Vn  PK x+xxx  Z=cota"
                                  en CADA vértice (incluye su distancia
                                  acumulada en notación estándar de PK).
                                  Si además se indica 'equidistant_interval'
                                  (>0) y 'sampler', se añaden marcas EXTRA
                                  en los PK redondos de esa equidistancia
                                  (p.ej. 0+000, 0+100, 0+200... si es 100 m),
                                  aparte de los vértices reales.

    axes_list  : [(nombre, points_3d), ...]
                 points_3d = lista de (x, y, z, dist)
    sampler    : MDTSampler
    mark_size  : float  — semilongitud (m) de la cruz 3D en cada vértice
    text_height: float  — altura (m) del texto "Vn  PK x+xxx  Z=cota"
    """
    try:
        import ezdxf
        from ezdxf.enums import TextEntityAlignment as _TEA
    except ImportError:
        try:
            from .perfil_dxf import _ensure_ezdxf
            _ensure_ezdxf()
            import ezdxf
            from ezdxf.enums import TextEntityAlignment as _TEA
        except Exception:
            if axes_list:
                _export_axis_ogr(axes_list[0][1], output_path)
            return

    doc = ezdxf.new('R2010', setup=True)
    msp = doc.modelspace()
    _colors = [2, 1, 4, 5, 6, 3, 7]

    for idx, (nombre, pts_3d) in enumerate(axes_list):
        color = _colors[idx % len(_colors)]
        lname = f'EJE_{nombre.upper().replace(" ", "_")}'

        if lname not in doc.layers:
            lay = doc.layers.new(lname)
            lay.color = color

        # ── Vértices a exportar ───────────────────────────────────────────────
        if clean_equidistant and equidistant_interval > 0 and sampler is not None:
            # Eje 3D equidistante: limpio, sin marcas ni texto.
            coords = resample_axis_3d_equidistant(pts_3d, equidistant_interval, sampler)
        else:
            # Eje 3D de vértices originales: con marcas y etiquetas
            # "Vn  PK x+xxx  Z=cota" en TODOS los vértices (incluida su
            # distancia acumulada / PK en notación estándar de topografía).
            coords_full = [(x, y, z if z is not None else 0.0, d)
                           for x, y, z, d in pts_3d]
            coords = [(x, y, z) for x, y, z, _ in coords_full]

            ltxt = f'{lname}_TEXTOS'
            if ltxt not in doc.layers:
                lay2 = doc.layers.new(ltxt)
                lay2.color = color

            for i, (x, y, z, d) in enumerate(coords_full):
                v_num = i + 1
                mh = mark_size
                # Marca: pequeña cruz 3D (visible desde planta y desde perfil)
                msp.add_line((x - mh, y, z), (x + mh, y, z),
                             dxfattribs={'layer': lname})
                msp.add_line((x, y - mh, z), (x, y + mh, z),
                             dxfattribs={'layer': lname})
                msp.add_line((x, y, z - mh), (x, y, z + mh),
                             dxfattribs={'layer': lname})

                # Etiqueta "Vn  PK x+xxx", desplazada perpendicularmente al eje.
                # Texto HORIZONTAL (rotation=0): la Z no se pone aquí, ya está
                # en los perfiles longitudinales.
                ux, uy = _vertex_tangent(coords, i)
                lx, ly = -uy, ux
                off = mark_size * 3.0
                tx = x + lx * off
                ty = y + ly * off

                t = msp.add_text(
                    f'V{v_num}  PK {_format_pk(d)}',
                    dxfattribs={'height': text_height, 'layer': ltxt,
                                'rotation': 0.0})
                t.set_placement((tx, ty, z), align=_TEA.LEFT)

            # Marcas adicionales en los PK redondos de la equidistancia
            # configurada (p.ej. 0+000, 0+100, 0+200... si es 100 m).
            # Texto HORIZONTAL, sin Z (solo PK). La Z está en los perfiles.
            if equidistant_interval > 0 and sampler is not None:
                pk_mark_size = mark_size * 0.7
                for (xi, yi, zi, di) in _equidistant_pk_points(
                        coords_full, equidistant_interval, sampler):
                    mh = pk_mark_size
                    msp.add_line((xi - mh, yi, zi), (xi + mh, yi, zi),
                                 dxfattribs={'layer': lname})
                    msp.add_line((xi, yi - mh, zi), (xi, yi + mh, zi),
                                 dxfattribs={'layer': lname})
                    msp.add_line((xi, yi, zi - mh), (xi, yi, zi + mh),
                                 dxfattribs={'layer': lname})

                    ux, uy = _dist_tangent(coords_full, di)
                    lx, ly = -uy, ux
                    off = mh * 3.0
                    tx = xi + lx * off
                    ty = yi + ly * off

                    t = msp.add_text(
                        f'PK {_format_pk(di)}',
                        dxfattribs={'height': text_height * 0.85, 'layer': ltxt,
                                    'rotation': 0.0})
                    t.set_placement((tx, ty, zi), align=_TEA.LEFT)

        if len(coords) >= 2:
            msp.add_polyline3d(coords, dxfattribs={'layer': lname})

    doc.saveas(output_path)


def _export_axis_ogr(points_3d, output_path):
    """Fallback OGR."""
    driver = ogr.GetDriverByName("DXF")
    if driver is None:
        raise RuntimeError("Driver DXF no disponible en GDAL.")
    if os.path.exists(output_path):
        driver.DeleteDataSource(output_path)
    ds = driver.CreateDataSource(output_path)
    srs = osr.SpatialReference()
    layer = ds.CreateLayer("Eje_3D", srs=srs, geom_type=ogr.wkbLineString25D)
    line = ogr.Geometry(ogr.wkbLineString25D)
    for (x, y, z, _) in points_3d:
        line.AddPoint(x, y, z if z is not None else 0.0)
    feat = ogr.Feature(layer.GetLayerDefn())
    feat.SetGeometry(line)
    layer.CreateFeature(feat)
    feat = None
    ds = None
