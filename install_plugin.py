#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_plugin.py
Instala el plugin 'perfil_longitudinal_plugin' en QGIS automáticamente.

Uso:
    python install_plugin.py              # detecta QGIS automáticamente
    python install_plugin.py --path "C:\\Users\\TU_USUARIO\\AppData\\Roaming\\QGIS\\QGIS3\\profiles\\default\\python\\plugins"
"""

import os
import sys
import shutil
import argparse
import platform


def find_qgis_plugin_dir():
    """Intenta localizar la carpeta de plugins de QGIS 3."""
    home = os.path.expanduser("~")
    candidates = []

    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "")
        candidates = [
            os.path.join(
                appdata,
                "QGIS",
                "QGIS3",
                "profiles",
                "default",
                "python",
                "plugins"),
        ]
    elif platform.system() == "Darwin":
        candidates = [
            os.path.join(
                home,
                "Library",
                "Application Support",
                "QGIS",
                "QGIS3",
                "profiles",
                "default",
                "python",
                "plugins"),
        ]
    else:  # Linux
        candidates = [
            os.path.join(home, ".local", "share", "QGIS", "QGIS3",
                         "profiles", "default", "python", "plugins"),
        ]

    for c in candidates:
        if os.path.isdir(c):
            return c

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Instala el plugin Perfil Longitudinal MDT en QGIS"
    )
    parser.add_argument(
        "--path", default=None,
        help="Ruta manual a la carpeta plugins de QGIS "
             "(si no se especifica, se detecta automáticamente)"
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_src = script_dir  # la carpeta del plugin ES este directorio
    plugin_name = os.path.basename(script_dir)

    print("=" * 60)
    print("  Instalador – Perfil Longitudinal MDT")
    print("=" * 60)

    # Destino
    if args.path:
        plugins_dir = args.path
    else:
        plugins_dir = find_qgis_plugin_dir()

    if plugins_dir is None:
        print("\n❌  No se encontró la carpeta de plugins de QGIS automáticamente.")
        print("    Usa:  python install_plugin.py --path <ruta_plugins>")
        sys.exit(1)

    dest = os.path.join(plugins_dir, plugin_name)

    print(f"\n  Origen:  {plugin_src}")
    print(f"  Destino: {dest}")

    # Crear carpeta plugins si no existe
    os.makedirs(plugins_dir, exist_ok=True)

    # Borrar instalación anterior
    if os.path.exists(dest):
        print("\n  Eliminando versión anterior...")
        shutil.rmtree(dest)

    # Copiar
    print("  Copiando archivos...")
    shutil.copytree(
        plugin_src, dest,
        ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '.git', '.gitignore',
            'install_plugin.py', 'test_perfil.py',
            'mdt_cache.json',          # no copiar caché de desarrollo
        )
    )

    print(f"\n✅  Plugin instalado en:\n    {dest}")

    # Instalar dependencia ezdxf si no está disponible
    try:
        import ezdxf  # noqa: F401
        print("  ✅  ezdxf ya está instalado.")
    except ImportError:
        print("\n  Instalando dependencia: ezdxf ...")
        import subprocess
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "ezdxf"],
                stdout=subprocess.DEVNULL,
            )
            print("  ✅  ezdxf instalado correctamente.")
        except Exception as e:
            print(f"  ⚠️   No se pudo instalar ezdxf automáticamente: {e}")
            print("      Instálalo manualmente:")
            print("        python -m pip install ezdxf")

    print("\n  Pasos siguientes:")
    print("  1. Abre QGIS")
    print("  2. Menú Complementos → Administrar e instalar complementos")
    print("  3. Pestaña 'Instalados' → activa 'Perfil Longitudinal MDT'")
    print("  4. Aparecerá en el menú Complementos y en la barra de herramientas")
    print("=" * 60)


if __name__ == "__main__":
    main()
