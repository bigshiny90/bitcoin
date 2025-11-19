#!/usr/bin/env python3
"""
Memory Pressure Test Analysis
Analyzes overhead calculation accuracy and MemAvailable stability
"""

import csv
import statistics
from collections import defaultdict
from pathlib import Path

def analyze_overhead_accuracy():
    """Compare predicted vs actual overhead"""

    # Current formula: overhead_mb = batch_size_mb * 2.9, threshold = overhead + 330
    def predicted_overhead(batch_bytes):
        batch_mb = batch_bytes / (1024 * 1024)
        return batch_mb * 2.9

    results = defaultdict(list)

    # Read both CSV files
    for csv_file in ['mempressure_test_results/lowmem_thresholds_linuxVM.csv',
                     'mempressure_test_results/lowmem_thresholds_linux.csv']:
        try:
            with open(csv_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    batch = int(row['dbbatchsize_mb'])
                    actual_overhead = int(row['overhead_mb'])
                    cache_size = int(row['cache_size_mb'])
                    duration = int(row['duration_ms'])
                    memavail = int(row['sys_memavail_mb'])

                    # Skip outliers (0 overhead likely means no actual flush happened)
                    if actual_overhead == 0:
                        continue

                    key = f"{csv_file.split('_')[-1].replace('.csv', '')}_batch{batch}"
                    results[key].append({
                        'batch': batch,
                        'actual': actual_overhead,
                        'predicted': predicted_overhead(batch),
                        'cache': cache_size,
                        'duration': duration,
                        'memavail': memavail,
                        'env': csv_file.split('_')[-1].replace('.csv', '')
                    })
        except FileNotFoundError:
            pass

    print("=" * 80)
    print("MEMORY OVERHEAD ANALYSIS")
    print("=" * 80)
    print()
    print("Current Formula: overhead = (batch_size_mb * 2.9)")
    print("                threshold = overhead + 330")
    print()

    for key in sorted(results.keys()):
        data = results[key]
        actual_overheads = [d['actual'] for d in data]
        predicted = data[0]['predicted']
        batch = data[0]['batch']
        env = data[0]['env']

        if not actual_overheads:
            continue

        mean_actual = statistics.mean(actual_overheads)
        median_actual = statistics.median(actual_overheads)
        min_actual = min(actual_overheads)
        max_actual = max(actual_overheads)
        stddev = statistics.stdev(actual_overheads) if len(actual_overheads) > 1 else 0

        print(f"\n{env.upper()} - Batch Size: {batch}MB ({len(actual_overheads)} samples)")
        print(f"  Predicted overhead:  {predicted:.1f} MB")
        print(f"  Actual mean:         {mean_actual:.1f} MB")
        print(f"  Actual median:       {median_actual:.1f} MB")
        print(f"  Actual range:        {min_actual} - {max_actual} MB")
        print(f"  Std deviation:       {stddev:.1f} MB")
        print(f"  Prediction error:    {mean_actual - predicted:+.1f} MB ({((mean_actual - predicted) / predicted * 100):+.1f}%)")
        print(f"  Safety margin:       {max_actual - predicted:+.1f} MB")

        # Check if our 330MB buffer is sufficient
        threshold = predicted + 330
        over_threshold = sum(1 for x in actual_overheads if x > threshold)
        print(f"  Threshold (330MB):   {threshold:.1f} MB")
        print(f"  Samples > threshold: {over_threshold}/{len(actual_overheads)} ({over_threshold/len(actual_overheads)*100:.1f}%)")

def analyze_memavailable_stability():
    """Analyze MemAvailable trends over time"""

    print("\n")
    print("=" * 80)
    print("MEMAVAILABLE STABILITY ANALYSIS")
    print("=" * 80)
    print()

    for csv_file in ['mempressure_test_results/lowmem_thresholds_linuxVM.csv',
                     'mempressure_test_results/lowmem_thresholds_linux.csv']:
        try:
            with open(csv_file) as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            env = csv_file.split('_')[-1].replace('.csv', '')

            # Group by test configuration
            configs = defaultdict(list)
            for row in rows:
                dbcache = row['dbcachesize_mb']
                dbbatch = row['dbbatchsize_mb']
                memavail = int(row['sys_memavail_mb'])
                timestamp = row['timestamp']

                key = f"dbcache={dbcache}MB_batch={dbbatch}MB"
                configs[key].append((timestamp, memavail))

            print(f"\n{env.upper()} Environment:")
            print("-" * 80)

            for config, values in sorted(configs.items()):
                if len(values) < 3:  # Need at least 3 samples
                    continue

                memavails = [v[1] for v in values]

                mean_memavail = statistics.mean(memavails)
                median_memavail = statistics.median(memavails)
                min_memavail = min(memavails)
                max_memavail = max(memavails)
                stddev = statistics.stdev(memavails) if len(memavails) > 1 else 0

                # Calculate drift (first half vs second half)
                mid = len(memavails) // 2
                first_half = memavails[:mid]
                second_half = memavails[mid:]

                drift = statistics.mean(second_half) - statistics.mean(first_half)
                drift_pct = (drift / statistics.mean(first_half)) * 100

                print(f"\n  {config} ({len(memavails)} flushes)")
                print(f"    Mean MemAvailable:   {mean_memavail:.0f} MB")
                print(f"    Range:               {min_memavail} - {max_memavail} MB (Δ{max_memavail - min_memavail} MB)")
                print(f"    Std deviation:       {stddev:.1f} MB")
                print(f"    Drift (early→late):  {drift:+.0f} MB ({drift_pct:+.1f}%)")

                # Stability verdict
                variability_pct = (stddev / mean_memavail) * 100
                if variability_pct < 5:
                    verdict = "✓ STABLE"
                elif variability_pct < 10:
                    verdict = "~ MODERATE"
                else:
                    verdict = "✗ UNSTABLE"
                print(f"    Variability:         {variability_pct:.1f}% - {verdict}")

        except FileNotFoundError:
            pass

def analyze_interesting_findings():
    """Find interesting patterns or anomalies"""

    print("\n")
    print("=" * 80)
    print("INTERESTING FINDINGS")
    print("=" * 80)
    print()

    # Look for correlations between overhead and other factors
    linuxvm_data = []
    linux_data = []

    for csv_file, data_list in [
        ('mempressure_test_results/lowmem_thresholds_linuxVM.csv', linuxvm_data),
        ('mempressure_test_results/lowmem_thresholds_linux.csv', linux_data)
    ]:
        try:
            with open(csv_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if int(row['overhead_mb']) > 0:  # Skip zero overheads
                        data_list.append(row)
        except FileNotFoundError:
            pass

    if linuxvm_data:
        print("\n1. LinuxVM (4GB RAM) Observations:")

        # Find extreme overheads
        overheads = [(int(r['overhead_mb']), r) for r in linuxvm_data]
        overheads.sort(key=lambda x: x[0], reverse=True)

        print(f"   - Highest overhead: {overheads[0][0]} MB (batch={overheads[0][1]['dbbatchsize_mb']}MB, duration={int(overheads[0][1]['duration_ms'])//1000}s)")
        print(f"   - Lowest overhead:  {overheads[-1][0]} MB (batch={overheads[-1][1]['dbbatchsize_mb']}MB, duration={int(overheads[-1][1]['duration_ms'])//1000}s)")

        # Duration correlation
        batch_64 = [r for r in linuxvm_data if int(r['dbbatchsize_mb']) == 67108864]
        batch_128 = [r for r in linuxvm_data if int(r['dbbatchsize_mb']) == 134217728]

        if batch_64 and batch_128:
            avg_duration_64 = statistics.mean([int(r['duration_ms']) for r in batch_64]) / 1000
            avg_duration_128 = statistics.mean([int(r['duration_ms']) for r in batch_128]) / 1000
            speedup = avg_duration_64 / avg_duration_128 if avg_duration_128 > 0 else 0

            print(f"   - Avg flush time 64MB:  {avg_duration_64:.1f}s")
            print(f"   - Avg flush time 128MB: {avg_duration_128:.1f}s")
            print(f"   - Speedup with 128MB:   {speedup:.2f}x FASTER")

    if linux_data:
        print("\n2. Linux Bare Metal (32GB RAM) Observations:")

        # MemAvailable abundance
        memavails = [int(r['sys_memavail_mb']) for r in linux_data]
        avg_memavail = statistics.mean(memavails)
        min_memavail = min(memavails)

        print(f"   - Average MemAvailable: {avg_memavail:.0f} MB")
        print(f"   - Minimum MemAvailable: {min_memavail} MB")
        print(f"   - Memory pressure risk: VERY LOW (abundant RAM)")

        # Overhead consistency
        batch_256 = [r for r in linux_data if int(r['dbbatchsize_mb']) == 268435456]
        if batch_256:
            overheads_256 = [int(r['overhead_mb']) for r in batch_256 if int(r['overhead_mb']) > 0]
            if overheads_256:
                avg_overhead = statistics.mean(overheads_256)
                stddev = statistics.stdev(overheads_256) if len(overheads_256) > 1 else 0
                variability = (stddev / avg_overhead) * 100

                print(f"   - 256MB batch overhead:  {avg_overhead:.0f} ± {stddev:.0f} MB ({variability:.1f}% variability)")
                print(f"   - Consistency verdict:   {'EXCELLENT' if variability < 10 else 'GOOD' if variability < 20 else 'MODERATE'}")

if __name__ == '__main__':
    analyze_overhead_accuracy()
    analyze_memavailable_stability()
    analyze_interesting_findings()

    print("\n")
    print("=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)
    print()
    print("The analysis will help determine if the current formula (batch * 2.9 + 330)")
    print("provides adequate safety margins across different environments and batch sizes.")
    print()
