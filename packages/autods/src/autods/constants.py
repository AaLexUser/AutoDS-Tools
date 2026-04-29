from pathlib import Path

# Agents
AUTO_DS_AGENT = "autods"

# AUTODS_HOME
AUTODS_HOME = Path.home() / ".autods"
AUTODS_PACKAGE = Path(__file__).parent

# CONFIG
DEFAULT_CONFIG_PATH = AUTODS_HOME / "autods_config.yaml"

# Error Messages
MULTI_TOOL_ERROR = "Multiple tool calls detected. Only ONE tool call is permitted per turn."
TOOLS_NOT_FOUND_ERROR = lambda tools: f"Tool calls not found. Be ACTIVE and use the tools. Available tools: {tools}"

# Project Folder
AUTODS_PROJECT_HOME = Path(".autods")

ANALYST_REPORT_PATH = AUTODS_PROJECT_HOME / "analyst_report.md"
PLANNER_REPORT_PATH = AUTODS_PROJECT_HOME / "planner_report.md"
RESEARCHER_REPORT_PATH = AUTODS_PROJECT_HOME / "researcher_report.md"
