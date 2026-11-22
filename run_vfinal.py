from tools.generate_project_structure import refresh_project_structure
from vfinal.cli.main import main

if __name__ == "__main__":
    refresh_project_structure()
    raise SystemExit(main())
