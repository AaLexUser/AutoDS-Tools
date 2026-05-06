from pathlib import Path

from autods.constants import (
    ANALYST_REPORT_PATH,
    MANAGER_REPORT_PATH,
    RESEARCHER_REPORT_PATH,
)


def _saved_reports_context(
    project_path: str,
    *,
    include_planner: bool = True,
) -> str:
    sections: list[str] = []
    report_paths = [
        ("Analyst Report", ANALYST_REPORT_PATH),
        ("Researcher Report", RESEARCHER_REPORT_PATH),
    ]
    if include_planner:
        report_paths.insert(1, ("Planner Report", MANAGER_REPORT_PATH))

    for label, relative_path in report_paths:
        report_path = Path(project_path) / relative_path
        if not report_path.exists() or not report_path.is_file():
            continue
        report = report_path.read_text(encoding="utf-8").strip()
        if report:
            sections.append(f"[{label}]\n{report}")

    return "\n\n".join(sections)
