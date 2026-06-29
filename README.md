# Plugin QGIS – Perfil Longitudinal MDT

> Repositorio: [github.com/kmlidar/qgis-perfil-longitudinal](https://github.com/kmlidar/qgis-perfil-longitudinal)

Genera perfiles longitudinales topográficos a partir de ejes vectoriales y Modelos Digitales de Terreno en cualquier formato ráster soportado por GDAL (GeoTIFF, ASC, IMG, BIL, FLT, DEM, HGT...). El resultado sigue el esquema de presentación de herramientas topográficas profesionales (línea de terreno, plano de comparación, tabla de distancias y cotas).

---

## Características

| Funcionalidad | Descripción |
|---|---|
| **Múltiples formatos de eje** | DXF, Shapefile, KML/KMZ, GeoPackage, GML, GPX y GeoJSON. |
| **Múltiples formatos de MDT** | GeoTIFF, ASC, IMG, BIL, FLT, DEM, HGT — cualquier ráster soportado por GDAL. Se pueden mezclar formatos en la misma carpeta. |
| **Caché inteligente de MDTs** | Escanea la carpeta una sola vez y guarda `mdt_cache.json`. Ejecuciones posteriores son instantáneas. |
| **Detección automática** | Identifica qué MDTs intersectan con el eje sin recorrerlos todos. |
| **Planchado del eje** | Obtiene las cotas Z de cada vértice del eje sobre el MDT con interpolación de huecos. |
| **Segmentación configurable** | Fragmenta el eje en intervalos (por defecto 1 m) para mayor fidelidad del perfil. |
| **Perfil longitudinal** | Línea de terreno, plano de comparación, distancias parciales/totales y cotas en vértices originales. |
| **Escalas independientes** | Escala horizontal y vertical configurables por separado (ej: H 1:1000 / V 1:100). |
| **Plano de comparación** | Automático (múltiplo de 5 por debajo del mínimo del terreno − 5 m) o cota fija. |
| **Nombrado automático** | Los archivos de salida se nombran `perfil1`, `perfil2`, … sin sobrescribir los anteriores. |
| **Exportación CSV** | Tabla de datos del perfil (distancias parciales/totales, cotas, X, Y) en formato europeo (`;` y coma decimal). |
| **Exportación DXF perfil** | Perfil con polilíneas, textos y tabla de datos (guitarra), listo para abrir en AutoCAD o similar. |
| **Exportación DXF 3D (planta)** | Eje planchado con coordenadas Z, con marcas de PK 0, PK final y equidistancia intermedia, exportado a DXF. |

---

## Requisitos

- **QGIS 3.16** o superior
- **Python 3.8+** (incluido con QGIS)
- **GDAL/OGR** (incluido con QGIS)
- **ezdxf** – se instala automáticamente la primera vez que el plugin exporta un DXF. Si la instalación automática falla, instálalo manualmente desde la OSGeo4W Shell:

```bash
python -m pip install ezdxf
```

> `matplotlib` solo es necesario si vas a usar el script de prueba standalone `test_perfil.py` (ver más abajo); el plugin dentro de QGIS no lo requiere.

---

## Instalación

### Opción A – Script automático (recomendado)

```bash
# Desde una terminal en la carpeta del plugin:
python install_plugin.py

# O especificando la ruta de plugins manualmente:
python install_plugin.py --path "/ruta/a/tu/carpeta/de/plugins/QGIS"
```

### Opción B – Instalación manual

1. Copia la carpeta `perfil_longitudinal_plugin` completa a:
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - **Linux:**   `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **macOS:**   `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

2. Abre QGIS → **Complementos → Administrar e instalar complementos**
3. Pestaña **Instalados** → activa **Perfil Longitudinal MDT**

---

## Uso

### 1. Preparar los datos

- Todos los archivos del **MDT** en una misma carpeta (pueden ser varios mosaicos, incluso de formatos distintos entre sí). Formatos soportados: ver tabla más abajo.
- El **eje** en cualquier formato vectorial soportado (ver tabla de formatos más abajo).
- Ambos deben estar **en el mismo sistema de coordenadas** (mismo EPSG).

### 2. Abrir el plugin

**Complementos → Perfil Longitudinal MDT** (o icono en la barra de herramientas).

### 3. Configurar los parámetros

#### Sección 1 – Datos de entrada

| Campo | Descripción |
|---|---|
| **Carpeta MDTs** | Carpeta donde están los archivos del modelo digital de terreno (GeoTIFF, ASC, IMG, BIL, FLT, DEM, HGT...). El primer uso escanea y crea el caché; los siguientes son inmediatos. |
| **Eje (vectorial)** | Archivo de eje en cualquiera de los formatos soportados. Debe contener al menos una geometría de tipo línea o polilínea. |
| **Forzar re-escaneo** | Marca esta opción si has añadido, eliminado o modificado TIFs desde el último uso. |

#### Sección 2 – Parámetros del perfil

| Parámetro | Descripción |
|---|---|
| **Intervalo segmentación** | Distancia entre puntos de muestreo sobre el terreno (línea de terreno del perfil). Recomendado: 0.5–2 m. Menores valores = mayor precisión de la línea de terreno. **No afecta** a los datos mostrados en la guitarra/CSV; eso lo controla la equidistancia (ver abajo). |
| **Escala horizontal 1:** | Denominador de la escala horizontal del perfil impreso (ej: 1000 → escala 1:1000). |
| **Escala vertical 1:** | Denominador de la escala vertical. Valores bajos exageran el relieve (ej: 100 → escala 1:100). |
| **Textos en guitarra** | Orientación de los textos de cota/distancia en la tabla de datos: vertical (90°, estilo topográfico) u horizontal. |
| **Datos en guitarra → Mostrar a equidistancia** | Los vértices originales del eje **siempre** aparecen en la guitarra y en el CSV. Si activas esta opción, además se añade un dato cada *N* metros (el **Intervalo** de al lado), independientemente del intervalo de segmentación. |
| **Plano de comparación** | Ver apartado siguiente. |

#### Plano de comparación

- **Automático (recomendado):** se calcula como el múltiplo de 5 más próximo por debajo de la cota mínima del terreno, menos 5 m adicionales. Por ejemplo, si el punto más bajo está a 347.3 m: `⌊347.3/5⌋×5 − 5 = 345 − 5 = 340 m`. Tras ejecutar, el spinbox muestra el valor calculado.
- **Manual:** desmarca "Automático" e introduce la cota exacta. Útil para que varios perfiles compartan la misma referencia inferior.

#### Sección 3 – Carpeta de salida

Selecciona una carpeta. El plugin genera automáticamente, por cada eje detectado en el archivo de entrada:

| Archivo | Contenido |
|---|---|
| `perfil1.dxf` | Perfil DXF con entidades CAD (línea de terreno, plano de comparación, guitarra/tabla de datos) |
| `perfil1.csv` | Datos del perfil: eje, tipo de punto, distancia parcial/total, cota, X, Y |
| `perfiles_ejes3d.dxf` | DXF de planta con TODOS los ejes planchados sobre el MDT (coordenadas Z), con marcas de PK 0, PK final y, si está activada la equidistancia, marcas intermedias cada N metros |

Si ya existen `perfil1.dxf`/`perfil1.csv` en la carpeta, los archivos de la siguiente ejecución se llamarán `perfil2`, y así sucesivamente. El DXF de planta (`perfiles_ejes3d.dxf`) es único por carpeta y acumula todos los ejes generados en él.

### 4. Ejecutar

Pulsa **▶ Generar perfil**. La barra de progreso muestra cada fase del proceso. Al terminar aparece un mensaje con la ubicación de todos los archivos generados.

---

## Formatos de eje soportados

El archivo de eje puede ser cualquier formato vectorial que soporte OGR/GDAL (incluido con QGIS). Los probados y recomendados son:

| Formato | Extensión | Notas |
|---|---|---|
| AutoCAD DXF | `.dxf` | Polilíneas 2D o 3D (POLYLINE / LWPOLYLINE) |
| ESRI Shapefile | `.shp` | Geometría de tipo línea o multilinea |
| KML / KMZ | `.kml`, `.kmz` | Google Earth. Coordenadas en WGS84 |
| GeoPackage | `.gpkg` | Estándar OGC, recomendado como alternativa a SHP |
| GML | `.gml` | Geography Markup Language |
| GPX | `.gpx` | Trazas GPS (tracks o rutas) |
| GeoJSON | `.geojson`, `.json` | Coordenadas en WGS84 |

> **Nota sobre sistemas de coordenadas:** KML, KMZ, GPX y GeoJSON usan siempre WGS84 (EPSG:4326). Si los MDTs están en una proyección métrica (ej: UTM), el resultado puede ser incorrecto. Reproyecta el eje antes de usarlo o asegúrate de que los MDTs también están en WGS84.

---

## Formatos de MDT soportados

El plugin abre los MDTs con la API genérica de GDAL, así que en teoría funciona con cualquier formato ráster que GDAL reconozca. Los probados son:

| Formato | Extensión | Notas |
|---|---|---|
| GeoTIFF | `.tif`, `.tiff` | Formato recomendado, el más extendido |
| ESRI ASCII Grid | `.asc` | Habitual en MDTs del IGN/PNOA. Necesita un `.prj` al lado para llevar CRS |
| ERDAS IMAGINE | `.img` | |
| ESRI BIL / EHdr | `.bil` | Necesita el `.hdr` correspondiente en la misma carpeta |
| ESRI Float binario | `.flt` | Necesita el `.hdr` correspondiente en la misma carpeta |
| USGS DEM | `.dem` | Formato nativo USGS |
| SRTM | `.hgt` | Tiles de elevación SRTM |

Puedes mezclar formatos distintos en la misma carpeta (ej: parte en `.tif` y parte en `.asc`); el plugin los detecta y los trata todos por igual. Si necesitas otro formato ráster que no esté en la lista (NetCDF, VRT, etc.) y tu GDAL lo soporta, abre un issue en el repositorio y lo añadimos al filtro de extensiones.

---

## Archivos de caché generados

Después del primer uso, en la carpeta de MDTs aparecen:

| Archivo | Descripción |
|---|---|
| `mdt_cache.json` | Índice con extensiones y metadatos de todos los TIFs. |
| `mdt_footprints.dxf` | Huellas (bounding boxes) de los MDTs. Cárgalo en QGIS para visualizar la cobertura del modelo. |

---

## Prueba sin QGIS (script de línea de comandos)

Para verificar dependencias o depurar errores antes de instalar el plugin:

```bash
cd perfil_longitudinal_plugin

python test_perfil.py \
    --folder /ruta/a/carpeta/mdt \
    --axis   /ruta/al/eje.dxf \
    --outdir /ruta/de/salida

# Con opciones adicionales:
python test_perfil.py \
    --folder /ruta/mdt \
    --axis   /ruta/eje.shp \
    --outdir /ruta/salida \
    --interval 0.5 \
    --hscale 500 \
    --vscale 50 \
    --cplane 340.0 \
    --rescan
```

El script acepta los mismos formatos de eje que el plugin. A diferencia del plugin (que exporta DXF + CSV), este script standalone también genera una imagen PNG del perfil con matplotlib, útil solo para depuración rápida sin abrir QGIS/AutoCAD.

---

## Cómo funciona internamente

```
Archivo de eje  →  OGR lee geometrías lineales
      ↓
Caché MDTs      →  GDAL escanea TIFs y guarda extensiones en JSON
      ↓
Intersección    →  Se descartan MDTs que no solapan con el eje
      ↓
Segmentación    →  El eje se divide en puntos cada N metros
      ↓
Planchado       →  Cada punto se proyecta sobre el raster para obtener Z
      ↓
Interpolación   →  Los huecos sin cota (NoData) se rellenan por interpolación lineal
      ↓
Plano de comp.  →  Automático o fijo; define la referencia inferior del perfil
      ↓
Exportación     →  DXF perfil (guitarra)  +  CSV  +  DXF planta (ejes 3D, PK 0/intermedios/final)
```

---

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| *"Ningún MDT intersecta con el eje"* | Sistemas de coordenadas diferentes | Reproyecta el eje o los TIFs al mismo CRS |
| *"No se encontró ningún eje lineal"* | El archivo no contiene geometrías de tipo línea | Verifica que el eje es una polilínea/línea, no puntos o polígonos |
| *"No se pudo instalar ezdxf"* | Falla la instalación automática (sin permisos/sin red) | Instala ezdxf manualmente desde la OSGeo4W Shell como Administrador: `python -m pip install ezdxf` |
| El perfil aparece casi plano | Escala vertical demasiado alta | Reduce el denominador de la escala vertical (ej: de 1:500 a 1:100) |
| Caché desactualizado | Se añadieron nuevos TIFs | Marca "Forzar re-escaneo" |
| KML/GPX sin cotas correctas | Archivo en WGS84, MDTs en UTM | Reproyecta el eje antes de usarlo |

---

## Estructura del plugin

```
perfil_longitudinal_plugin/
├── __init__.py              ← Punto de entrada QGIS
├── metadata.txt             ← Metadatos del plugin (nombre, versión, descripción)
├── perfil_longitudinal.py   ← Clase principal del plugin (menú y barra de herramientas)
├── perfil_dialog.py         ← Interfaz gráfica (QDialog) y worker en hilo separado
├── mdt_cache.py             ← Escaneo, caché y detección de MDTs afectados
├── eje_utils.py             ← Lectura de ejes, segmentación, planchado y exportación DXF 3D
├── perfil_draw.py           ← Gráfico del perfil con matplotlib (solo usado por test_perfil.py)
├── perfil_dxf.py            ← Exportación del perfil a DXF con entidades CAD reales
├── install_plugin.py        ← Script de instalación automática
├── test_perfil.py           ← Script de prueba standalone (sin QGIS)
└── icons/
    ├── icon.png             ← Icono del plugin (32×32 px)
    └── icon.svg             ← Icono en formato vectorial
```

---

## Autor

Desarrollado por **Kiko Molina**.

## Licencia

Este plugin se distribuye como software libre. Consulta el archivo `LICENSE` para más detalles.
