"""
roxymaster v8.3 - entry point for nuitka compilation (pcbot)
punto de entrada para compilar con nuitka a binario unico.
todo en minusculas, utf-8 sin bom.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main

if __name__ == "__main__":
    main()