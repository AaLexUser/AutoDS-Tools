from pathlib import Path

# AUTODS_HOME
AUTODS_HOME = Path.home() / ".autods"
AUTODS_PACKAGE = Path(__file__).parent

# Project Folder
AUTODS_PROJECT_HOME = Path(".autods")

ANALYST_REPORT_PATH = AUTODS_PROJECT_HOME / "analyst_report.md"
MANAGER_REPORT_PATH = AUTODS_PROJECT_HOME / "planner_report.md"
RESEARCHER_REPORT_PATH = AUTODS_PROJECT_HOME / "researcher_report.md"
PRESENTER_REPORT_PATH = AUTODS_PROJECT_HOME / "presenter_report.md"
