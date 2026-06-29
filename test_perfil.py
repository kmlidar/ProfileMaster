#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_perfil.py  –  Script de prueba independiente (sin QGIS).

Permite verificar que las dependencias están instaladas y que el cálculo
funciona correctamente antes de usar el plugin en QGIS.

Uso básico:
    python test_perfil.py \\
        --folder /ruta/a/carpeta/mdt \\
        --axis   /ruta/al/eje.dxf \\
        --outdir /ruta/de/salida

Formatos de eje aceptados (cualquier formato soportado por OGR/GDAL):
    DXF, SHP, KML, KMZ, GeoPackage (.gpkg), GML, GPX, GeoJSON

Opciones adicionales:
    --interval 1.0        Intervalo de segmentación en metros (defecto: 1.0)
    --hscale   1000       Escala horizontal 1:X (defecto: 1000)
    --vscale   100        Escala vertical 1:X (defecto: 100)
    --cplane   340.0      Plano de comparación fijo (omitir = automático)
    --rescan              Forzar re-escaneo del caché de MDTs
"""

from perfil_dxf import export_profile_dxf
from perfil_draw import draw_profile
from eje_utils import (
    read_axis_from_dxf, get_axis_bbox,
    segment_axis, MDTSampler, drape_points,
    interpolate_missing_z, export_axis_3d_dxf,
)
from mdt_cache import load_or_build_cache, get_affected_mdts, invalidate_cache
import argparse
import sys
import os
import math

# Permite importar los módulos del plugin sin QGIS instalado
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def next_profile_name(output_dir, base="perfil"):
    """Devuelve el siguiente nombre disponible (perfil1, perfil2, …)."""
    i = 1
    while True:
        if not os.path.exists(os.path.join(output_dir, f"{base}{i}.png")):
            return f"{base}{i}"
        i += 1


def main():
    parser = argparse.ArgumentParser(
        description="Perfil Longitudinal MDT – prueba standalone (sin QGIS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--folder", required=True,
                        help="Carpeta con los archivos GeoTIF del MDT")
    parser.add_argument(
        "--axis",
        required=True,
        help="Archivo de eje (DXF, SHP, KML, KMZ, GPKG, GML, GPX, GeoJSON)")
    parser.add_argument("--outdir", default=".",
                        help="Carpeta de salida (defecto: directorio actual)")
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Intervalo de segmentación en metros (defecto: 1.0)")
    parser.add_argument("--hscale", type=int, default=1000,
                        help="Escala horizontal 1:X (defecto: 1000)")
    parser.add_argument("--vscale", type=int, default=100,
                        help="Escala vertical 1:X (defecto: 100)")
    parser.add_argument(
        "--cplane",
        type=float,
        default=None,
        help="Plano de comparación fijo en metros (omitir = automático)")
    parser.add_argument("--rescan", action="store_true",
                        help="Forzar re-escaneo del caché de MDTs")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    profile_base = next_profile_name(args.outdir)

    out_img = os.path.join(args.outdir, f"{profile_base}.png")
    out_dxf3d = os.path.join(args.outdir, f"{profile_base}_eje3d.dxf")
    out_perfil_dxf = os.path.join(args.outdir, f"{profile_base}.dxf")

    print("=" * 60)
    print("  Perfil Longitudinal MDT – test standalone")
    print("=" * 60)
    print(f"  Perfil de salida: {profile_base}")
    print()

    # 1. Caché MDTs
    if args.rescan:
        invalidate_cache(args.folder)

    print(f"[1/6] Cargando caché de MDTs en: {args.folder}")
    mdts, from_cache = load_or_build_cache(
        args.folder,
        lambda p: print(f"  Escaneo: {p}%", end='\r')
    )
    print(
        f"  → {
            len(mdts)} MDTs  ({
            'caché' if from_cache else 'escaneo nuevo'})")
    for m in mdts:
        print(f"     • {os.path.basename(m['path'])}  "
              f"res={m['res_x']:.2f}m")

    # 2. Leer eje
    print(f"\n[2/6] Leyendo eje: {args.axis}")
    vertices_2d = read_axis_from_dxf(args.axis)
    bbox = get_axis_bbox(vertices_2d)
    print(f"  → {len(vertices_2d)} vértices")
    print(f"  → Bbox: {[round(v, 2) for v in bbox]}")

    # 3. MDTs afectados
    print("\n[3/6] Identificando MDTs afectados...")
    affected = get_affected_mdts(mdts, bbox)
    if not affected:
        print("  ❌  Ningún MDT intersecta con el eje.")
        print("     Verifica que los sistemas de coordenadas coincidan.")
        sys.exit(1)
    print(f"  → {len(affected)} MDT(s) afectados")

    # 4. Segmentar
    print(f"\n[4/6] Segmentando eje cada {args.interval} m...")
    segmented, orig_indices = segment_axis(vertices_2d, args.interval)
    print(
        f"  → {
            len(segmented)} puntos  |  {
            len(orig_indices)} vértices originales")

    # 5. Planchar
    print("\n[5/6] Planchando sobre MDT...")
    mdt_paths = [m['path'] for m in affected]
    sampler = MDTSampler(mdt_paths)
    terrain_3d = drape_points(
        segmented,
        sampler,
        lambda p: print(
            f"  {p}%",
            end='\r') if p % 10 == 0 else None)
    terrain_3d = interpolate_missing_z(terrain_3d)
    sampler.close()
    print(
        f"\n  → {sum(1 for p in terrain_3d if p[2] is not None)} puntos con cota")

    # Plano de comparación
    zs = [p[2] for p in terrain_3d if p[2] is not None]
    if args.cplane is None:
        cp = math.floor(min(zs) / 5) * 5 - 5
        print(f"  → Plano de comparación automático: {cp:.2f} m")
    else:
        cp = args.cplane
        print(f"  → Plano de comparación fijo: {cp:.2f} m")

    # 6. Exportar
    print(f"\n[6/6] Exportando resultados como '{profile_base}'...")

    orig_3d = [terrain_3d[i] for i in orig_indices]
    export_axis_3d_dxf(orig_3d, out_dxf3d)
    print(f"  → Eje 3D:     {out_dxf3d}")

    draw_profile(
        terrain_points=terrain_3d,
        original_indices=orig_indices,
        h_scale=args.hscale,
        v_scale=args.vscale,
        comparison_plane=cp,
        output_path=out_img,
        title=f"Perfil – {os.path.basename(args.axis)}",
    )
    print(f"  → Imagen:     {out_img}")

    export_profile_dxf(
        terrain_points=terrain_3d,
        original_indices=orig_indices,
        comparison_plane=cp,
        h_scale=args.hscale,
        v_scale=args.vscale,
        output_path=out_perfil_dxf,
        title=f"Perfil – {os.path.basename(args.axis)}",
        text_vertical=True,
        use_equidistant=False,
        equidistant_interval=100.0,
    )
    print(f"  → Perfil DXF: {out_perfil_dxf}")

    print("\n" + "=" * 60)
    print("  ✅  Completado")
    print(f"  Longitud total:  {terrain_3d[-1][3]:.2f} m")
    print(f"  Cota mínima:     {min(zs):.2f} m")
    print(f"  Cota máxima:     {max(zs):.2f} m")
    print(f"  Desnivel total:  {max(zs) - min(zs):.2f} m")
    print("=" * 60)


if __name__ == "__main__":
    main()
