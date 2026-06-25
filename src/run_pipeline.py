"""
run_pipeline.py
Master script — runs all 7 pipeline steps in sequence.

Usage:
  python src/run_pipeline.py                     # full pipeline
  python src/run_pipeline.py --steps 1 2 3       # only steps 1-3
  python src/run_pipeline.py --psr_positions 20  # fast PSR preview (20 sun positions)
  python src/run_pipeline.py --synthetic-demo    # UI-only fake Stokes (NOT for judges)
"""

import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(__file__))

STEPS = {
    1: ("Data Ingestion",           "01_data_ingestion",      "main"),
    2: ("PSR Mapping",              "02_psr_mapping",         "run_psr_mapping"),
    3: ("Radar Ice Detection",      "03_radar_ice_detection", "run_ice_detection"),
    4: ("Terrain Analysis",         "04_terrain_analysis",    "run_terrain_analysis"),
    5: ("Landing Site Selection",   "05_landing_site_selection", "run_landing_site_selection"),
    6: ("Rover Traverse Planning",  "06_rover_traverse",      "run_rover_traverse"),
    7: ("Ice Volume Estimation",    "07_ice_volume_estimation","run_ice_volume_estimation"),
}


def run_step(step_num: int, kwargs: dict = None):
    """Dynamically import and run a pipeline step."""
    name, module_name, func_name = STEPS[step_num]
    print(f"\n{'='*70}")
    print(f"  STEP {step_num}: {name}")
    print(f"{'='*70}\n")

    t0 = time.time()
    mod = __import__(module_name)
    func = getattr(mod, func_name)
    result = func(**(kwargs or {}))
    elapsed = time.time() - t0
    print(f"\n  ✓ Step {step_num} completed in {elapsed:.1f}s\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="Lunar Ice Pipeline")
    parser.add_argument("--steps", nargs="+", type=int,
                        default=list(STEPS.keys()),
                        help="Steps to run (default: all 1-7)")
    parser.add_argument("--psr_positions", type=int, default=100,
                        help="Solar positions for PSR mapping (default 100, use 20 for fast preview)")
    parser.add_argument(
        "--synthetic-demo",
        action="store_true",
        help="Step 1 only: generate demo Stokes from single-band amplitude (UI testing, not science)",
    )
    args = parser.parse_args()

    print("\n" + "="*70)
    print("  BHARATIYA ANTARIKSH HACKATHON 2026 — Challenge #8")
    print("  Lunar South Pole Ice Detection Pipeline")
    print("  Target: Shackleton Crater (~89.9°S)")
    print("="*70)

    results = {}
    t_start = time.time()

    for step in sorted(args.steps):
        if step not in STEPS:
            print(f"[WARNING] Unknown step {step}. Skipping.")
            continue

        extra = {}
        if step == 1:
            extra = {"synthetic_demo": args.synthetic_demo}
        if step == 2:
            extra = {"n_sun_positions": args.psr_positions}

        try:
            results[step] = run_step(step, extra)
        except Exception as e:
            print(f"\n[ERROR] Step {step} failed: {e}")
            import traceback
            traceback.print_exc()
            print(f"\nCheck that all required input files exist.")
            break

    total_time = time.time() - t_start
    print("\n" + "="*70)
    print(f"  Pipeline finished in {total_time:.0f}s ({total_time/60:.1f} min)")
    print("  Outputs in:  data/processed/  and  data/exports/")
    print("  Dashboard:   open  dashboard/index.html  in Chrome")
    print("="*70)


if __name__ == "__main__":
    main()
