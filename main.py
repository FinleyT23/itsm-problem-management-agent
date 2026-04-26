"""
main.py — FinServe Problem Management Agent — Entry Point
==========================================================
Loads data file paths, configures environment, runs the Problem Management
crew, and saves the final report.

Usage:
    python main.py

Environment Variables (optional — override default relative paths):
    FINSERVE_DATA_DIR   Path to directory containing the three CSV files
    FINSERVE_OUTPUT_DIR Path to output directory for KE records and RFCs
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Resolve data and output directories
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("FINSERVE_DATA_DIR", BASE_DIR / "data"))
OUTPUT_DIR = Path(os.environ.get("FINSERVE_OUTPUT_DIR", BASE_DIR / "output"))

# Export as env vars so tools.py can pick them up via os.environ.get()
os.environ["FINSERVE_DATA_DIR"] = str(DATA_DIR)
os.environ["FINSERVE_OUTPUT_DIR"] = str(OUTPUT_DIR)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def validate_data_files():
    """Ensure all three required CSV files are present before starting the crew."""
    required = [
        "finserve_incidents_q1_2026.csv",
        "finserve_cmdb.csv",
        "finserve_changes.csv",
    ]
    missing = [f for f in required if not (DATA_DIR / f).exists()]
    if missing:
        print(f"ERROR: Missing data files in {DATA_DIR}:")
        for f in missing:
            print(f"  - {f}")
        print("\nPlace the CSV files in the data/ directory and re-run.")
        sys.exit(1)
    print(f"✓ Data files verified in: {DATA_DIR}")


def print_header():
    print("=" * 70)
    print("  FinServe Digital Bank — ITIL 4 Problem Management Agent")
    print("  CrewAI + Ollama (qwen3:8b-q4_K_M)")
    print("=" * 70)
    print(f"  Data directory : {DATA_DIR}")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Run started    : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)
    print()


def save_final_report(result: str, output_dir: Path):
    """Persist the crew's final output as a markdown report."""
    report_path = output_dir / "problem_management_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# FinServe Problem Management Report\n")
        f.write(f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}_\n\n")
        f.write("---\n\n")
        f.write(str(result))
    print(f"\n✓ Full report saved to: {report_path}")
    return report_path


def list_output_artifacts(output_dir: Path):
    """Print a summary of all artifacts written to the output directory."""
    artifacts = list(output_dir.glob("*.json")) + list(output_dir.glob("*.md"))
    if not artifacts:
        return
    print("\n" + "=" * 70)
    print("  OUTPUT ARTIFACTS")
    print("=" * 70)
    for a in sorted(artifacts):
        size_kb = a.stat().st_size / 1024
        print(f"  {a.name:<45} {size_kb:>6.1f} KB")
    print("=" * 70)


def main():
    print_header()
    validate_data_files()

    # Import here (after env vars set) so tools resolve paths correctly
    from src.problem_crew import create_problem_crew

    print("Initializing Problem Management crew...\n")
    crew = create_problem_crew()

    print("Starting sequential crew execution...")
    print("This may take 10–30 minutes depending on Ollama model performance.\n")
    print("-" * 70)

    try:
        result = crew.kickoff()
    except Exception as e:
        print(f"\nERROR during crew execution: {e}")
        raise

    print("\n" + "=" * 70)
    print("  CREW EXECUTION COMPLETE")
    print("=" * 70)

    # Print final output to console
    final_output = str(result)
    print("\n--- FINAL REPORT (Executive Summary) ---\n")
    # Print first 3000 chars to console; full report is saved to file
    if len(final_output) > 3000:
        print(final_output[:3000])
        print(f"\n... [truncated — full report saved to file] ...")
    else:
        print(final_output)

    # Save full report
    save_final_report(final_output, OUTPUT_DIR)
    list_output_artifacts(OUTPUT_DIR)

    print(f"\nRun completed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    return result


if __name__ == "__main__":
    main()
