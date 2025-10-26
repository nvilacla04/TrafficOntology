#!/usr/bin/env python3
"""
Merge Traffic Data with Sensor Locations - UPDATED

Enhanced with proper understanding of site ID structure:
RWS01_MONIBAS_0021hrl0802ra_1
├─ RWS01: Rijkswaterstaat region
├─ MONIBAS: Device type (Monitoring Basis)
├─ 0021: Road number (A21)
├─ hrl: Direction (hecto-links = left)
├─ 0802: Hectometer position (8.02 km)
├─ ra: Roadway/Lane A
└─ _1: Sensor index

Usage:
    python merge_traffic_with_sensors.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
import re
from difflib import get_close_matches

# ============================================================================
# CONFIGURATION - Relative paths (script runs from data_raw/)
# ============================================================================

# Get the project root (parent of data_raw where script is located)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Input files - using relative paths
TELPUNTEN_CSV = PROJECT_ROOT / 'data_processed' / 'Sensors_cleaned' / 'telpunten_all_columns.csv'
MEETVAKKEN_CSV = PROJECT_ROOT / 'data_processed' / 'Sensors_cleaned' / 'meetvakken_all_columns.csv'
TRAFFIC_SPEED_CSV = PROJECT_ROOT / 'data_processed' / 'traffic_flowtraffic_speed_clean.csv'
TRAFFIC_FLOW_CSV = PROJECT_ROOT / 'data_processed' / 'traffic_flowtraffic_flow_clean.csv'
SITE_SUMMARY_CSV = PROJECT_ROOT / 'data_processed' / 'traffic_flowsite_summary.csv'

# Output directory
OUTPUT_DIR = PROJECT_ROOT / 'data_processed' / 'merged'

# ============================================================================
# SITE ID PARSING FUNCTIONS
# ============================================================================

def parse_rws_site_id(site_id):
    """
    Parse RWS MONIBAS site ID structure.
    
    Example: RWS01_MONIBAS_0021hrl0802ra_1
    Returns: dict with provider, device, road, direction, hectometer, lane, index
    """
    parts = str(site_id).split('_')
    
    if len(parts) < 3:
        return None
    
    result = {
        'provider': parts[0],
        'device': parts[1],
        'full_code': parts[2] if len(parts) > 2 else '',
        'index': parts[3] if len(parts) > 3 else None
    }
    
    # Try to parse the location code (e.g., 0021hrl0802ra)
    code = result['full_code']
    match = re.match(r'(\d{4})(hr[lr])(\d{4})([a-z]{2})', code)
    
    if match:
        result['road_number'] = match.group(1)
        result['direction'] = match.group(2)  # hrl or hrr
        result['hectometer'] = match.group(3)
        result['lane'] = match.group(4)
    
    return result


def get_site_hierarchy(site_id):
    """
    Extract hierarchical components for flexible matching.
    
    Returns multiple levels of granularity:
    - Level 1: Full ID (most specific)
    - Level 2: Without index suffix
    - Level 3: Provider + device + road + direction + hectometer
    - Level 4: Provider + device + road
    """
    site_str = str(site_id)
    
    levels = {
        'full': site_str,
        'no_suffix': re.sub(r'_\d+$', '', site_str),
    }
    
    # Parse structured parts
    parsed = parse_rws_site_id(site_id)
    if parsed and 'road_number' in parsed:
        # Create base location (road + direction + hectometer)
        levels['base_location'] = f"{parsed['provider']}_{parsed['device']}_{parsed['road_number']}{parsed['direction']}{parsed['hectometer']}"
        # Create road level (just road)
        levels['road_only'] = f"{parsed['provider']}_{parsed['device']}_{parsed['road_number']}"
    else:
        # Fallback for non-RWS patterns
        parts = site_str.split('_')
        if len(parts) >= 3:
            levels['base_location'] = '_'.join(parts[:3])
            levels['road_only'] = '_'.join(parts[:2])
    
    return levels


# ============================================================================
# HELPER FUNCTIONS (Updated with new understanding)
# ============================================================================

def normalize_site_id(site_id):
    """
    Normalize site ID by removing trailing index suffix.
    
    Examples:
        RWS01_MONIBAS_0021hrl0802ra_1 → RWS01_MONIBAS_0021hrl0802ra
        GRT02_MORO_1940_2 → GRT02_MORO_1940
    """
    normalized = re.sub(r'_\d+$', '', str(site_id))
    return normalized


def extract_base_code(site_id):
    """
    Extract the base location code (provider + device + road + position).
    
    Examples:
        RWS01_MONIBAS_0021hrl0802ra_1 → RWS01_MONIBAS_0021hrl0802
        GRT02_MORO_1940_2 → GRT02_MORO_1940
    """
    normalized = normalize_site_id(site_id)
    
    # For RWS pattern, remove lane designation (ra, rb, etc.)
    base = re.sub(r'[a-z]{2}$', '', normalized)
    return base


def create_lookup_dict(sensor_df, id_column='dgl_loc'):
    """
    Create multiple lookup dictionaries for flexible matching.
    Uses hierarchical site ID structure for intelligent matching.
    """
    lookups = {
        'exact': {},
        'normalized': {},
        'base': {},
        'road': {}
    }
    
    for idx, row in sensor_df.iterrows():
        site_id = str(row[id_column])
        hierarchy = get_site_hierarchy(site_id)
        
        # Exact match
        lookups['exact'][site_id] = row
        
        # Normalized match (without index suffix)
        normalized = hierarchy['no_suffix']
        if normalized not in lookups['normalized']:
            lookups['normalized'][normalized] = []
        lookups['normalized'][normalized].append(row)
        
        # Base location match (road + direction + hectometer)
        if 'base_location' in hierarchy:
            base = hierarchy['base_location']
            if base not in lookups['base']:
                lookups['base'][base] = []
            lookups['base'][base].append(row)
        
        # Road-only match
        if 'road_only' in hierarchy:
            road = hierarchy['road_only']
            if road not in lookups['road']:
                lookups['road'][road] = []
            lookups['road'][road].append(row)
    
    return lookups


def find_best_match(traffic_site_id, sensor_lookups, sensor_df, id_column='dgl_loc'):
    """
    Find the best matching sensor using hierarchical site ID structure.
    
    Strategy:
    1. Exact match (same sensor, same lane, same index)
    2. Normalized match (same sensor, same lane, different index)
    3. Base location match (same road + direction + position, different lane)
    4. Road match (same road, different position)
    5. Fuzzy match (string similarity)
    """
    traffic_site = str(traffic_site_id)
    hierarchy = get_site_hierarchy(traffic_site)
    
    # Strategy 1: Exact match
    if traffic_site in sensor_lookups['exact']:
        return sensor_lookups['exact'][traffic_site], 'exact'
    
    # Strategy 2: Normalized match (same location, any index)
    normalized = hierarchy['no_suffix']
    if normalized in sensor_lookups['normalized']:
        matches = sensor_lookups['normalized'][normalized]
        return matches[0], 'normalized'
    
    # Strategy 3: Base location match (same road position, any lane)
    if 'base_location' in hierarchy:
        base = hierarchy['base_location']
        if base in sensor_lookups['base']:
            matches = sensor_lookups['base'][base]
            if len(matches) > 1:
                # Find closest by full string similarity
                sensor_ids = [str(m[id_column]) for m in matches]
                closest = get_close_matches(traffic_site, sensor_ids, n=1, cutoff=0.6)
                if closest:
                    matching_row = [m for m in matches if str(m[id_column]) == closest[0]][0]
                    return matching_row, 'base_location'
            return matches[0], 'base_location'
    
    # Strategy 4: Road-only match (same road, different position)
    if 'road_only' in hierarchy:
        road = hierarchy['road_only']
        if road in sensor_lookups['road']:
            matches = sensor_lookups['road'][road]
            # Take first as representative location
            return matches[0], 'road_only'
    
    # Strategy 5: Fuzzy match (last resort)
    all_sensor_ids = sensor_df[id_column].astype(str).tolist()
    fuzzy_matches = get_close_matches(traffic_site, all_sensor_ids, n=1, cutoff=0.85)
    if fuzzy_matches:
        return sensor_df[sensor_df[id_column] == fuzzy_matches[0]].iloc[0], 'fuzzy'
    
    return None, None


def merge_with_sensors(traffic_df, telpunten_df, meetvakken_df, traffic_id_col='site_id'):
    """
    Merge traffic data with sensor locations using intelligent hierarchical matching.
    """
    print("\n" + "="*70)
    print("MERGING TRAFFIC DATA WITH SENSOR LOCATIONS")
    print("="*70)
    
    # Create lookup dictionaries
    print("\n📚 Creating lookup dictionaries...")
    telpunten_lookups = create_lookup_dict(telpunten_df, 'dgl_loc')
    meetvakken_lookups = create_lookup_dict(meetvakken_df, 'dgl_loc')
    
    print(f"   Telpunten: {len(telpunten_df):,} counting points")
    print(f"   Meetvakken: {len(meetvakken_df):,} measurement sections")
    
    # Prepare result dataframe
    result_df = traffic_df.copy()
    
    # Add coordinate columns
    result_df['latitude'] = np.nan
    result_df['longitude'] = np.nan
    result_df['sensor_type'] = None
    result_df['matched_dgl_loc'] = None
    result_df['wegtype'] = None
    result_df['match_strategy'] = None
    
    # Add parsed site ID components
    result_df['provider'] = None
    result_df['device_type'] = None
    result_df['road_number'] = None
    result_df['direction'] = None
    result_df['hectometer'] = None
    result_df['lane'] = None
    
    print(f"\n🔍 Matching {len(traffic_df):,} traffic records...")
    
    # Statistics
    stats = {
        'telpunten_exact': 0,
        'telpunten_normalized': 0,
        'telpunten_base_location': 0,
        'telpunten_road_only': 0,
        'telpunten_fuzzy': 0,
        'meetvakken_exact': 0,
        'meetvakken_normalized': 0,
        'meetvakken_base_location': 0,
        'meetvakken_road_only': 0,
        'meetvakken_fuzzy': 0,
        'no_match': 0
    }
    
    # Iterate through traffic data
    for idx, row in traffic_df.iterrows():
        traffic_site = row[traffic_id_col]
        
        # Parse site ID components
        parsed = parse_rws_site_id(traffic_site)
        if parsed:
            result_df.at[idx, 'provider'] = parsed.get('provider')
            result_df.at[idx, 'device_type'] = parsed.get('device')
            result_df.at[idx, 'road_number'] = parsed.get('road_number')
            result_df.at[idx, 'direction'] = parsed.get('direction')
            result_df.at[idx, 'hectometer'] = parsed.get('hectometer')
            result_df.at[idx, 'lane'] = parsed.get('lane')
        
        # Try telpunten first (exact point locations)
        match, strategy = find_best_match(traffic_site, telpunten_lookups, telpunten_df, 'dgl_loc')
        
        if match is not None:
            result_df.at[idx, 'latitude'] = match['latitude']
            result_df.at[idx, 'longitude'] = match['longitude']
            result_df.at[idx, 'sensor_type'] = 'CountingPoint'
            result_df.at[idx, 'matched_dgl_loc'] = match['dgl_loc']
            result_df.at[idx, 'wegtype'] = match.get('wegtype', None)
            result_df.at[idx, 'match_strategy'] = strategy
            stats[f'telpunten_{strategy}'] += 1
            continue
        
        # Try meetvakken (section centroids) as fallback
        match, strategy = find_best_match(traffic_site, meetvakken_lookups, meetvakken_df, 'dgl_loc')
        
        if match is not None:
            result_df.at[idx, 'latitude'] = match['centroid_lat']
            result_df.at[idx, 'longitude'] = match['centroid_lon']
            result_df.at[idx, 'sensor_type'] = 'MeasurementSection'
            result_df.at[idx, 'matched_dgl_loc'] = match['dgl_loc']
            result_df.at[idx, 'wegtype'] = match.get('wegtype', None)
            result_df.at[idx, 'match_strategy'] = strategy
            stats[f'meetvakken_{strategy}'] += 1
            continue
        
        # No match found
        stats['no_match'] += 1
    
    # Print statistics
    total_matched = len(result_df[result_df['latitude'].notna()])
    match_rate = (total_matched / len(result_df)) * 100
    
    print("\n" + "="*70)
    print("MERGE RESULTS")
    print("="*70)
    
    print(f"\n📊 Overall Statistics:")
    print(f"   Total traffic records: {len(result_df):,}")
    print(f"   Successfully matched: {total_matched:,} ({match_rate:.1f}%)")
    print(f"   No match found: {stats['no_match']:,} ({stats['no_match']/len(result_df)*100:.1f}%)")
    
    print(f"\n📍 Matched with Telpunten (exact points):")
    tel_total = sum(v for k, v in stats.items() if k.startswith('telpunten'))
    print(f"   Total: {tel_total:,}")
    print(f"   - Exact match: {stats['telpunten_exact']:,}")
    print(f"   - Normalized (no index): {stats['telpunten_normalized']:,}")
    print(f"   - Base location (same road position): {stats['telpunten_base_location']:,}")
    print(f"   - Road only (same road): {stats['telpunten_road_only']:,}")
    print(f"   - Fuzzy match: {stats['telpunten_fuzzy']:,}")
    
    print(f"\n📍 Matched with Meetvakken (section centroids):")
    meet_total = sum(v for k, v in stats.items() if k.startswith('meetvakken'))
    print(f"   Total: {meet_total:,}")
    print(f"   - Exact match: {stats['meetvakken_exact']:,}")
    print(f"   - Normalized (no index): {stats['meetvakken_normalized']:,}")
    print(f"   - Base location (same road position): {stats['meetvakken_base_location']:,}")
    print(f"   - Road only (same road): {stats['meetvakken_road_only']:,}")
    print(f"   - Fuzzy match: {stats['meetvakken_fuzzy']:,}")
    
    return result_df, stats


def print_sample_matches(merged_df, n=5):
    """Print sample of matched records with parsed components."""
    print(f"\n📋 Sample of matched records (first {n}):")
    sample = merged_df[merged_df['latitude'].notna()].head(n)
    for idx, row in sample.iterrows():
        print(f"\n   Traffic ID: {row['site_id']}")
        if pd.notna(row.get('road_number')):
            print(f"   Parsed: Road {row['road_number']}, {row['direction']}, " + 
                  f"Hectometer {row['hectometer']}, Lane {row['lane']}")
        print(f"   Matched to: {row['matched_dgl_loc']}")
        print(f"   Coordinates: ({row['latitude']:.6f}, {row['longitude']:.6f})")
        print(f"   Type: {row['sensor_type']}")
        print(f"   Strategy: {row['match_strategy']}")


def print_sample_unmatched(merged_df, n=10):
    """Print sample of unmatched records."""
    unmatched = merged_df[merged_df['latitude'].isna()]
    if len(unmatched) > 0:
        print(f"\n⚠️  Sample of unmatched site IDs (first {n}):")
        for site_id in unmatched['site_id'].unique()[:n]:
            print(f"   - {site_id}")
            hierarchy = get_site_hierarchy(site_id)
            print(f"     Normalized: {hierarchy['no_suffix']}")
            if 'base_location' in hierarchy:
                print(f"     Base location: {hierarchy['base_location']}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("="*70)
    print("TRAFFIC DATA + SENSOR LOCATIONS MERGER")
    print("Enhanced with Site ID Structure Understanding")
    print("="*70)
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {OUTPUT_DIR}")
    
    # Load sensor data
    print("\n📂 Loading sensor data...")
    try:
        telpunten_df = pd.read_csv(TELPUNTEN_CSV)
        print(f"   ✅ Telpunten loaded: {len(telpunten_df):,} records")
    except FileNotFoundError:
        print(f"   ❌ Telpunten file not found: {TELPUNTEN_CSV}")
        print("   Please update the path or run sensor_exploration_and_cleaning_fixed.ipynb first")
        return
    
    try:
        meetvakken_df = pd.read_csv(MEETVAKKEN_CSV)
        print(f"   ✅ Meetvakken loaded: {len(meetvakken_df):,} records")
    except FileNotFoundError:
        print(f"   ❌ Meetvakken file not found: {MEETVAKKEN_CSV}")
        print("   Please update the path or run sensor_exploration_and_cleaning_fixed.ipynb first")
        return
    
    # Check for dgl_loc column
    if 'dgl_loc' not in telpunten_df.columns:
        print("\n   ⚠️  WARNING: 'dgl_loc' column not found in telpunten!")
        print("   Please re-run sensor_exploration_and_cleaning_fixed.ipynb")
        print(f"   Available columns: {telpunten_df.columns.tolist()}")
        return
    
    if 'dgl_loc' not in meetvakken_df.columns:
        print("\n   ⚠️  WARNING: 'dgl_loc' column not found in meetvakken!")
        print("   Please re-run sensor_exploration_and_cleaning_fixed.ipynb")
        print(f"   Available columns: {meetvakken_df.columns.tolist()}")
        return
    
    # Process each traffic data file
    traffic_files = [
        ('traffic_speed', TRAFFIC_SPEED_CSV),
        ('traffic_flow', TRAFFIC_FLOW_CSV),
        ('site_summary', SITE_SUMMARY_CSV)
    ]
    
    for file_name, file_path in traffic_files:
        print(f"\n{'='*70}")
        print(f"Processing: {file_name}")
        print(f"{'='*70}")
        
        try:
            traffic_df = pd.read_csv(file_path)
            print(f"✅ Loaded: {len(traffic_df):,} records")
        except FileNotFoundError:
            print(f"❌ File not found: {file_path}")
            print("   Skipping...")
            continue
        
        # Check for site_id column
        if 'site_id' not in traffic_df.columns:
            print(f"⚠️  WARNING: 'site_id' column not found!")
            print(f"Available columns: {traffic_df.columns.tolist()}")
            continue
        
        # Merge
        merged_df, stats = merge_with_sensors(traffic_df, telpunten_df, meetvakken_df)
        
        # Show samples
        print_sample_matches(merged_df, n=3)
        print_sample_unmatched(merged_df, n=5)
        
        # Save result
        output_file = OUTPUT_DIR / f"{file_name}_with_coordinates.csv"
        merged_df.to_csv(output_file, index=False)
        print(f"\n💾 Saved to: {output_file}")
        print(f"   Columns: {merged_df.columns.tolist()}")
    
    print("\n" + "="*70)
    print("✅ MERGE COMPLETE!")
    print("="*70)
    print(f"\nOutput files in: {OUTPUT_DIR}")
    print("\nColumns added: latitude, longitude, provider, device_type, road_number,")
    print("              direction, hectometer, lane, match_strategy")


if __name__ == "__main__":
    main()
