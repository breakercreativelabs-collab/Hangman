"""CLI launcher (outside src/): blender -b --factory-startup -P blender_cli.py -- <module> <command> [--options value ...]

Blender does not add the script folder to sys.path and ignores PYTHONPATH, so this launcher adds src/ (the only
sys.path.insert in the repo; forbidden inside src/, structure test b). All logic lives in agent3d.cli.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from agent3d.cli import main  # noqa: E402

sys.exit(main())
