# -*- coding: utf-8 -*-
"""
perfil_draw.py
Generación del gráfico de perfil longitudinal estilo topografía.

La imagen generada respeta la relación de escalas H/V:
  - Ancho del perfil  = longitud_total / h_scale  (en metros de papel)
  - Alto útil del perfil = desnivel_visible / v_scale (en metros de papel)
  El cociente v_scale/h_scale determina la exageración vertical real.

Si cambias H 1:1000 → 1:500 el perfil es el doble de ancho.
Si cambias V 1:100  → 1:50  el perfil es el doble de alto.
"""

import math

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import matplotlib.gridspec as gridspec
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ── Constantes visuales ─────────────────────────────────────────────────
_DPI = 150          # resolución de exportación
_MM_PER_INCH = 25.4
_MIN_W_IN = 16           # ancho mínimo de figura (pulgadas)
_MAX_W_IN = 80           # ancho máximo
_MIN_H_IN = 8            # alto mínimo
_MAX_H_IN = 30           # alto máximo

_COLOR_TERRAIN = '#4A3728'
_COLOR_FILL_ABOVE = '#D4C5A9'
_COLOR_FILL_BELOW = '#B8C9D4'
_COLOR_COMP_PLANE = '#1A5276'
_COLOR_VERTICES = '#C0392B'
_COLOR_VERT_LINE = '#888877'
_COLOR_GRID = '#CCCCBB'
_COLOR_BG = '#F8F8F0'
_COLOR_PANEL = '#FAFAF5'
_COLOR_TABLE_BG = '#EEF0E5'


def draw_profile(
    terrain_points,
    original_indices,
    h_scale=1000,
    v_scale=100,
    comparison_plane=None,
    output_path=None,
    title="Perfil Longitudinal",
    text_vertical=True,
):
    """
    Genera el perfil longitudinal.

    El tamaño de la figura se calcula en mm de papel reales a partir de
    h_scale y v_scale, de modo que cambiar la escala produce una imagen
    visualmente diferente (más ancha, más alta, más o menos exagerada).

    Parameters
    ----------
    terrain_points   : list[(x, y, z, dist)]  – todos los puntos segmentados
    original_indices : list[int]               – índices de vértices originales
    h_scale          : int    – denominador escala horizontal  (ej: 1000 → 1:1000)
    v_scale          : int    – denominador escala vertical    (ej: 100  → 1:100)
    comparison_plane : float  – cota PC (None = automático)
    output_path      : str    – ruta de salida (None = retorna fig)
    title            : str    – texto del título
    """
    if not HAS_MATPLOTLIB:
        raise ImportError(
            "matplotlib no está instalado. Instálalo con:\n  pip install matplotlib"
        )

    # ── Datos base ──────────────────────────────────────────────────────────
    dists = [p[3] for p in terrain_points]
    zs = [p[2] if p[2] is not None else float('nan') for p in terrain_points]

    orig_pts = [terrain_points[i] for i in original_indices]
    orig_dists = [p[3] for p in orig_pts]
    orig_zs = [p[2] if p[2] is not None else float('nan') for p in orig_pts]

    total_dist = dists[-1]
    z_valid = [z for z in zs if not math.isnan(z)]
    z_min = min(z_valid)
    z_max = max(z_valid)

    if comparison_plane is None:
        comparison_plane = math.floor(z_min / 5) * 5 - 5

    # ── Coordenadas en mm de papel ──────────────────────────────────────────
    # mm_papel = metros_reales / escala * 1000
    # Ejemplo: 1843 m / 1000 * 1000 = 1843 mm de ancho para H 1:1000
    #          1843 m / 500  * 1000 = 3686 mm de ancho para H 1:500
    def to_x(d):
        return d / h_scale * 1000.0           # mm papel

    def to_y(z):
        return (z - comparison_plane) / v_scale * 1000.0

    xs_mm = [to_x(d) for d in dists]
    ys_mm = [to_y(z) if not math.isnan(z) else float('nan') for z in zs]
    oxs_mm = [to_x(d) for d in orig_dists]
    oys_mm = [to_y(z) if not math.isnan(z) else float('nan') for z in orig_zs]
    cp_mm = 0.0   # plano de comparación siempre en Y=0

    total_x_mm = to_x(total_dist)
    # altura del terreno sobre el PC en mm papel
    visible_y_mm = to_y(z_max)
    margin_y_mm = max(visible_y_mm * 0.20, 10.0)

    # ── Tamaño de figura en pulgadas ────────────────────────────────────────
    # Escala directa: 1 mm de papel → 1 unidad en datos (trabajamos en mm)
    # El aspecto del panel de perfil debe ser PROPORCIONAL a las escalas reales.
    #
    # Relación de exageración vertical = h_scale / v_scale
    # Ejemplo H1:1000 V1:100 → exageración 10x
    #         H1:1000 V1:50  → exageración 20x  (perfil el doble de alto)
    #         H1:500  V1:100 → exageración 5x   (perfil el doble de ancho)

    fig_w_mm = total_x_mm + 60          # margen izq/der: 60 mm papel extra
    fig_h_mm = (visible_y_mm + margin_y_mm * 2) * 1.45 + 60  # perfil + tabla

    # Convertir a pulgadas, respetando límites
    fig_w_in = max(_MIN_W_IN, min(_MAX_W_IN, fig_w_mm / _MM_PER_INCH))
    fig_h_in = max(_MIN_H_IN, min(_MAX_H_IN, fig_h_mm / _MM_PER_INCH))

    # ── Figura ──────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(fig_w_in, fig_h_in), dpi=_DPI)
    fig.patch.set_facecolor(_COLOR_BG)

    gs = gridspec.GridSpec(
        2, 1,
        height_ratios=[4, 1],
        hspace=0.04,
        left=0.07, right=0.98, top=0.93, bottom=0.02
    )
    ax = fig.add_subplot(gs[0])   # panel perfil
    axt = fig.add_subplot(gs[1])   # tabla

    # ── Panel del perfil ────────────────────────────────────────────────────
    ax.set_facecolor(_COLOR_PANEL)
    ax.set_title(title, fontsize=10, fontweight='bold',
                 fontfamily='monospace', pad=8, color='#1A1A2E')

    ax.grid(True, color=_COLOR_GRID, linewidth=0.4, linestyle=':')

    # Relleno terreno
    ys_clean = [y if not math.isnan(y) else cp_mm for y in ys_mm]
    ax.fill_between(xs_mm, ys_clean, cp_mm,
                    where=[y >= cp_mm for y in ys_clean],
                    color=_COLOR_FILL_ABOVE, alpha=0.55)
    ax.fill_between(xs_mm, ys_clean, cp_mm,
                    where=[y < cp_mm for y in ys_clean],
                    color=_COLOR_FILL_BELOW, alpha=0.55)

    # Línea de terreno
    ax.plot(xs_mm, ys_mm, color=_COLOR_TERRAIN, linewidth=1.2,
            label='Terreno', zorder=3)

    # Plano de comparación
    ax.axhline(
        y=cp_mm,
        color=_COLOR_COMP_PLANE,
        linewidth=1.0,
        linestyle='--',
        label=f'PC = {
            comparison_plane:.2f} m',
        zorder=2)

    # Vértices originales
    oys_valid = [y for y in oys_mm if not math.isnan(y)]
    oxs_valid = [x for x, y in zip(oxs_mm, oys_mm) if not math.isnan(y)]
    ax.scatter(oxs_valid, oys_valid, color=_COLOR_VERTICES,
               s=25, zorder=5, label='Vértices')

    # Líneas verticales en vértices
    for xv, yv in zip(oxs_mm, oys_mm):
        if not math.isnan(yv):
            ax.vlines(xv, cp_mm, yv, colors=_COLOR_VERT_LINE,
                      linewidth=0.5, linestyle=':', zorder=2)

    # Etiquetas de cota sobre vértices
    _rot = 90 if text_vertical else 0
    _ha = 'center' if text_vertical else 'left'
    _va = 'bottom'
    for xv, yv, zreal in zip(oxs_mm, oys_mm, orig_zs):
        if not math.isnan(zreal):
            ax.annotate(
                f'{zreal:.2f}',
                xy=(xv, yv),
                xytext=(0, 8), textcoords='offset points',
                fontsize=6.5, color='#1A1A2E',
                ha=_ha, va=_va,
                fontfamily='monospace',
                rotation=_rot,
                zorder=6,
            )

    # Límites de ejes
    margin_x = total_x_mm * 0.01
    ax.set_xlim(-margin_x, total_x_mm + margin_x)
    ax.set_ylim(
        min(cp_mm, min(ys_clean)) - margin_y_mm,
        max(ys_clean) + margin_y_mm * 2.5
    )

    # Formatters: mostrar valores reales (metros) aunque las unidades internas
    # son mm papel
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(
        lambda val, _: f'{val / 1000 * v_scale + comparison_plane:.0f}'
    ))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda val, _: f'{val / 1000 * h_scale:.0f}'
    ))
    ax.set_ylabel('Cota (m)', fontsize=8, color='#333333')

    # Escala en la esquina
    exag = h_scale / v_scale
    ax.text(0.99, 0.02,
            f'H 1:{h_scale}    V 1:{v_scale}    (Exag. vert. ×{exag:.0f})',
            transform=ax.transAxes,
            fontsize=7, ha='right', va='bottom',
            fontfamily='monospace', color='#555555')

    ax.legend(fontsize=7, loc='upper left', framealpha=0.7)

    # ── Tabla inferior ──────────────────────────────────────────────────────
    axt.set_xlim(ax.get_xlim())
    axt.set_ylim(0, 3.5)
    axt.axis('off')
    axt.set_facecolor(_COLOR_TABLE_BG)

    parciales = [0.0]
    for i in range(1, len(orig_dists)):
        parciales.append(orig_dists[i] - orig_dists[i - 1])

    # Orden de filas: Número Vértice | Cota | Dist.Parcial | Dist.Total
    row_labels = [
        'Vértice',
        'Cota (m)',
        'Dist. parcial (m)',
        'Dist. total (m)']
    row_ys = [2.7, 2.3, 1.5, 0.7]
    row_colors = ['#333333', '#6B2D0F', '#2C3E50', '#1A5276']
    _trot = 90 if text_vertical else 0

    # Altura de los ticks (marcas verticales)
    _tick_height = 0.15
    _tick_y_top = 3.0
    _tick_y_h1 = row_ys[0]  # Vértice
    _tick_y_h2 = row_ys[1]  # Cota
    _tick_y_h3 = row_ys[2]  # Dist.Parcial
    _tick_y_bot = 0.0

    # Etiquetas de fila
    for label, ry, rc in zip(row_labels, row_ys, row_colors):
        axt.text(-margin_x * 1.5, ry, label,
                 fontsize=6, ha='right', va='center',
                 color=rc, fontfamily='monospace', clip_on=False,
                 rotation=_trot)

    # Separadores y datos
    for vert_num, (xv, dt, dp, zr) in enumerate(
            zip(oxs_mm, orig_dists, parciales, orig_zs), start=1):
        # Pequeños ticks en TODAS las líneas horizontales de la guitarra
        # Top
        axt.plot([xv, xv], [_tick_y_top - _tick_height, _tick_y_top],
                 color='#AAAAAA', linewidth=0.8)
        # Entre Vértice y Cota
        axt.plot([xv, xv],
                 [_tick_y_h1 - _tick_height, _tick_y_h1 + _tick_height],
                 color='#AAAAAA', linewidth=0.8)
        # Entre Cota y Dist.Parcial
        axt.plot([xv, xv],
                 [_tick_y_h2 - _tick_height, _tick_y_h2 + _tick_height],
                 color='#AAAAAA', linewidth=0.8)
        # Entre Dist.Parcial y Dist.Total
        axt.plot([xv, xv],
                 [_tick_y_h3 - _tick_height, _tick_y_h3 + _tick_height],
                 color='#AAAAAA', linewidth=0.8)
        # Bottom
        axt.plot([xv, xv], [_tick_y_bot, _tick_y_bot + _tick_height],
                 color='#AAAAAA', linewidth=0.8)

        fs = 6.0
        # Número de vértice — fila 0
        axt.text(xv, row_ys[0], f'V{vert_num}',
                 ha='center', va='center', fontsize=fs,
                 color=row_colors[0], fontfamily='monospace', rotation=_trot,
                 fontweight='bold')
        # Cota — fila 1
        if not math.isnan(zr):
            axt.text(xv,
                     row_ys[1],
                     f'{zr:.2f}',
                     ha='center',
                     va='center',
                     fontsize=fs,
                     color=row_colors[1],
                     fontfamily='monospace',
                     rotation=_trot)
        # Dist. parcial — fila 2
        axt.text(xv, row_ys[2], f'{dp:.1f}' if dp > 0 else '0',
                 ha='center', va='center', fontsize=fs,
                 color=row_colors[2], fontfamily='monospace', rotation=_trot)
        # Dist. total — fila 3
        axt.text(xv, row_ys[3], f'{dt:.1f}',
                 ha='center', va='center', fontsize=fs,
                 color=row_colors[3], fontfamily='monospace', rotation=_trot)

    # Separador visual entre perfil y tabla
    fig.add_artist(
        plt.Line2D([0.07, 0.98], [0.22, 0.22],
                   transform=fig.transFigure,
                   color='#888877', linewidth=0.8)
    )

    # ── Guardar o retornar ──────────────────────────────────────────────────
    if output_path:
        plt.savefig(output_path, dpi=_DPI, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        return output_path
    else:
        return fig
