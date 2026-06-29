# -*- coding: utf-8 -*-
"""
mdt_cache.py
Gestión del caché de Modelos Digitales de Terreno.
Escanea la carpeta de entrada una vez, guarda un archivo JSON de caché
con la extensión geográfica de cada MDT y sus metadatos.
Soporta cualquier formato ráster que reconozca GDAL (GeoTIFF, ASC, IMG,
BIL, FLT, DEM, HGT...), ya que se abre con la API genérica de GDAL.
También genera un DXF con las huellas (footprints) de los MDTs.
"""

import os
import json
import hashlib
import datetime

try:
    from osgeo import gdal, osr, ogr
    gdal.UseExceptions()
except ImportError:
    raise ImportError(
        "GDAL no está disponible. Asegúrate de que QGIS está correctamente instalado.")


CACHE_FILENAME = "mdt_cache.json"
FOOTPRINTS_DXF = "mdt_footprints.dxf"


# Extensiones de MDT soportadas. GDAL abre cualquiera de estos formatos de
# forma transparente (MDTSampler y _get_tif_info usan la API genérica de
# GDAL, sin nada específico de GeoTIFF), así que basta con que el archivo
# aparezca en esta lista para que se incluya en el escaneo de la carpeta.
MDT_EXTENSIONS = (
    '.tif', '.tiff',   # GeoTIFF
    # ESRI ASCII Grid (PNOA, IGN, etc. — normalmente con .prj al lado)
    '.asc',
    '.img',            # ERDAS IMAGINE
    '.bil',            # ESRI BIL / EHdr (con .hdr al lado)
    '.flt',            # ESRI Float binario (con .hdr al lado)
    '.dem',            # USGS DEM nativo
    '.hgt',            # SRTM
)


def _folder_hash(folder_path):
    """Hash basado en la lista de MDTs y sus fechas de modificación."""
    tifs = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(MDT_EXTENSIONS)
    ])
    sig = "|".join(
        f"{f}:{os.path.getmtime(os.path.join(folder_path, f))}"
        for f in tifs
    )
    return hashlib.md5(sig.encode(), usedforsecurity=False).hexdigest()


def _get_tif_info(tif_path):
    """Extrae extensión geográfica, CRS y resolución de un MDT.

    Es tolerante con MDTs sin CRS definido (p.ej. un .asc sin su .prj al
    lado: GDAL devuelve entonces una proyección vacía) y, en general, con
    cualquier fallo al leer CRS o nodata: en esos casos se sigue usando el
    MDT con esos datos a None en vez de interrumpir todo el escaneo con un
    traceback de GDAL/OGR.
    """
    try:
        ds = gdal.Open(tif_path, gdal.GA_ReadOnly)
    except Exception:
        ds = None
    if ds is None:
        return None

    try:
        gt = ds.GetGeoTransform()
        cols = ds.RasterXSize
        rows = ds.RasterYSize

        xmin = gt[0]
        ymax = gt[3]
        xmax = xmin + gt[1] * cols
        ymin = ymax + gt[5] * rows  # gt[5] es negativo
    except Exception:
        # No se ha podido determinar ni la extensión del ráster: el archivo
        # está demasiado dañado para usarlo. Se omite (igual que si
        # gdal.Open hubiera devuelto None).
        ds = None
        return None

    # CRS: si el formato no lleva proyección definida (.asc sin .prj, etc.)
    # GDAL devuelve una cadena WKT vacía, y pasarla a ImportFromWkt lanza
    # "OGR Error: Corrupt data". No es un problema real: simplemente el MDT
    # no tiene CRS conocido (epsg=None) y el plugin sigue funcionando con
    # él con normalidad, asumiendo que está en el mismo CRS que el eje.
    epsg = None
    try:
        wkt = ds.GetProjection()
        if wkt:
            srs = osr.SpatialReference()
            srs.ImportFromWkt(wkt)
            epsg = srs.GetAuthorityCode(None)
    except Exception:
        epsg = None

    nodata = None
    try:
        band = ds.GetRasterBand(1)
        if band is not None:
            nodata = band.GetNoDataValue()
    except Exception:
        nodata = None

    ds = None

    return {
        "path": tif_path,
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
        "res_x": abs(gt[1]),
        "res_y": abs(gt[5]),
        "epsg": epsg,
        "nodata": nodata,
    }


def scan_folder(folder_path, progress_callback=None):
    """
    Escanea la carpeta buscando MDTs.
    Devuelve lista de dicts con info de cada MDT.
    Un archivo individual que dé problemas (corrupto, formato no reconocido,
    etc.) se omite sin interrumpir el escaneo del resto de la carpeta.
    """
    tifs = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(MDT_EXTENSIONS)
    ]

    results = []
    for i, tif_path in enumerate(tifs):
        try:
            info = _get_tif_info(tif_path)
        except Exception:
            info = None
        if info:
            results.append(info)
        if progress_callback:
            progress_callback(int((i + 1) / len(tifs) * 100))

    return results


def load_or_build_cache(folder_path, progress_callback=None):
    """
    Carga el caché si existe y es válido (mismo conjunto de archivos).
    Si no, escanea la carpeta y genera el caché.
    Devuelve (lista_mdts, desde_cache: bool).
    """
    cache_path = os.path.join(folder_path, CACHE_FILENAME)
    current_hash = _folder_hash(folder_path)

    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            if cache.get("folder_hash") == current_hash:
                return cache["mdts"], True
        except Exception:
            pass  # caché corrupto → regenerar

    # Regenerar caché
    mdts = scan_folder(folder_path, progress_callback)
    cache = {
        "folder_hash": current_hash,
        "generated": datetime.datetime.now().isoformat(),
        "folder": folder_path,
        "mdts": mdts,
    }
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # no crítico

    # Generar DXF de huellas
    _export_footprints_dxf(mdts, os.path.join(folder_path, FOOTPRINTS_DXF))

    return mdts, False


def _export_footprints_dxf(mdts, dxf_path):
    """Exporta las huellas (bounding boxes) de los MDTs a un DXF."""
    try:
        driver = ogr.GetDriverByName("DXF")
        if driver is None:
            return

        if os.path.exists(dxf_path):
            driver.DeleteDataSource(dxf_path)

        ds = driver.CreateDataSource(dxf_path)
        layer = ds.CreateLayer("MDT_Footprints", geom_type=ogr.wkbPolygon)

        # Campo nombre
        field_defn = ogr.FieldDefn("Nombre", ogr.OFTString)
        field_defn.SetWidth(254)
        layer.CreateField(field_defn)

        for mdt in mdts:
            ring = ogr.Geometry(ogr.wkbLinearRing)
            xmin, ymin, xmax, ymax = mdt["xmin"], mdt["ymin"], mdt["xmax"], mdt["ymax"]
            ring.AddPoint(xmin, ymin)
            ring.AddPoint(xmax, ymin)
            ring.AddPoint(xmax, ymax)
            ring.AddPoint(xmin, ymax)
            ring.AddPoint(xmin, ymin)

            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)

            feat = ogr.Feature(layer.GetLayerDefn())
            feat.SetGeometry(poly)
            feat.SetField("Nombre", os.path.basename(mdt["path"]))
            layer.CreateFeature(feat)
            feat = None

        ds = None
    except Exception:
        pass


def get_affected_mdts(mdts, axis_bbox):
    """
    Filtra los MDTs que intersectan con la bbox del eje.
    axis_bbox: (xmin, ymin, xmax, ymax)
    """
    ax_xmin, ax_ymin, ax_xmax, ax_ymax = axis_bbox
    affected = []
    for mdt in mdts:
        # Comprobación de intersección de bounding boxes
        if (mdt["xmax"] >= ax_xmin and mdt["xmin"] <= ax_xmax and mdt["ymax"] >= ax_ymin and mdt["ymin"] <= ax_ymax):
            affected.append(mdt)
    return affected


def invalidate_cache(folder_path):
    """Elimina el archivo de caché para forzar un nuevo escaneo."""
    cache_path = os.path.join(folder_path, CACHE_FILENAME)
    if os.path.exists(cache_path):
        os.remove(cache_path)
