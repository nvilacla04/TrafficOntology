"""
Final Script to Match BRON Accident Data (2022-2024) to OSM Road Segments.

This is a LOW-MEMORY (16GB RAM safe) version.

It loads the OSM road network ONCE. Then, for each year:
1.  Reads the BRON accidents CSV.
2.  Correctly identifies BRON coordinates as RD New (EPSG:28992) and
    transforms them to WGS84 (EPSG:4326) for initial filtering.
3.  Loops through each unique street name:
    a. Gets a small slice of accidents (WGS84) and OSM roads (WGS84).
    b. Parses the 'other_tags' for ONLY that small OSM slice.
    c. Re-projects both small slices to RD New (EPSG:28992)
       to perform an accurate, meter-based "nearest" join.
4.  Saves the result as a new, year-specific enriched CSV.
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import re
from tqdm import tqdm
from pathlib import Path
import os
import warnings

# -----------------------------------------------------------------------------
# Helper function
# -----------------------------------------------------------------------------
def parse_hstore(hstore_string: str) -> dict:
    """Parse a PostGIS hstore formatted string into a Python dictionary."""
    if hstore_string is None:
        return {}
    try:
        return dict(re.findall(r'"(.*?)"=>"(.*?)"', hstore_string))
    except Exception:
        return {}

# -----------------------------------------------------------------------------
# Main processing function
# -----------------------------------------------------------------------------
def process_year(year: int, gdf_osm_all_wgs84: gpd.GeoDataFrame, data_dir: Path) -> None:
    """
    Loads, processes, and matches BRON data for a specific year
    using a low-memory, high-accuracy method.
    """
    print(f"\n--- Processing Year: {year} ---")
    
    # --- 1. Load BRON Data ---
    bron_csv_file = data_dir / "data_processed" / "BRON_cleaned" / f"ongevallen_{year}_clean.csv"
    try:
        df_bron = pd.read_csv(bron_csv_file, low_memory=False)
    except FileNotFoundError:
        print(f"File not found, skipping: {bron_csv_file}")
        return
        
    # Drop accidents with no street name or location
    df_bron = df_bron.dropna(subset=["longitude", "latitude", "straatnaam"])
    print(f"Loaded {len(df_bron)} accidents for {year}.")

    # --- 2. Prepare BRON GeoDataFrame (WGS84) ---
    # now need to creatre a GeoDataFrame from RD New coordinates
    geometry_points_rdnew = [Point(xy) for xy in zip(df_bron["longitude"], df_bron["latitude"])]
    gdf_bron_wgs84 = gpd.GeoDataFrame(df_bron, geometry=geometry_points_rdnew)
    
    # ** THE COORDINATE FIX **
    gdf_bron_wgs84.set_crs(epsg=28992, inplace=True) # first, set original RD New
    gdf_bron_wgs84 = gdf_bron_wgs84.to_crs(epsg=4326) # second, transform to WGS84
    print(f"Correctly transformed {year} BRON coordinates from EPSG:28992 to 4326.")

    # --- 3. Match Accidents to Roads (Low-Memory) ---
    unique_bron_names = gdf_bron_wgs84["straatnaam"].unique()
    print(f"Found {len(unique_bron_names)} unique street names to process for {year}.")
    matched_data_list = []

    attributes_to_extract = [
        "maxspeed", "surface", "zone:traffic", "bridge", "tunnel"
    ]

    for name in tqdm(unique_bron_names, desc=f"Matching {year}", leave=False):
        # 1. Get slices in WGS84 (Lat/Lon)
        accidents_on_street_wgs84 = gdf_bron_wgs84[gdf_bron_wgs84["straatnaam"] == name]
        roads_slice_wgs84 = gdf_osm_all_wgs84[gdf_osm_all_wgs84["name"] == name].copy()
        
        if roads_slice_wgs84.empty:
            continue
            
        # 2. Parse tags on the small WGS84 slice
        osm_tags_parsed = roads_slice_wgs84["other_tags"].apply(parse_hstore)
        
        # fixing a keyerror
        osm_tags_df = pd.DataFrame.from_records(osm_tags_parsed.tolist(), index=roads_slice_wgs84.index)
        
        roads_slice_wgs84 = roads_slice_wgs84.join(osm_tags_df)
        
        cols_to_keep_join = [
            "geometry", "osm_id", "name", "highway"
        ] + [col for col in attributes_to_extract if col in roads_slice_wgs84.columns]
        
        roads_with_name_wgs84 = roads_slice_wgs84[cols_to_keep_join]

        # fixing userwarning
        # 3. Re-project *both* slices to RD New (meters) for the join
        # suppress warnings fro this operation, keep popping up even tho everything is fine
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            accidents_projected = accidents_on_street_wgs84.to_crs(epsg=28992)
            roads_projected = roads_with_name_wgs84.to_crs(epsg=28992)
        
        # 4. Perform the join on the *projected* (meter-based) data
        matched = gpd.sjoin_nearest(
            accidents_projected,
            roads_projected,
            how="left",
        )
        
        matched_data_list.append(matched)

    print("Matching complete.")

    # --- 4. Clean and Save ---
    if not matched_data_list:
        print(f"Warning: No matches found for {year}.")
        return

    final_matched_gdf = pd.concat(matched_data_list)
    
    if "index_right" in final_matched_gdf.columns:
        final_matched_gdf = final_matched_gdf.dropna(subset=["index_right"])
    else:
        print("Warning: 'index_right' column not found in matched results. No rows dropped.")
    
    final_matched_gdf = final_matched_gdf.rename(columns={"name": "osm_road_name", "straatnaam": "bron_street_name"})
    
    print(f"Successfully matched {len(final_matched_gdf)} out of {len(df_bron)} accidents for {year}.")

    out_path = data_dir / "data_rdf" / f"accidents_enriched_osm_{year}.csv"
    
    # drop the geometry column before saving to CSV
    final_matched_gdf.drop(columns='geometry', errors='ignore').to_csv(out_path, index=False)
    print(f"Saved enriched data to '{out_path}'")


def main() -> None:
    project_root = Path(os.environ.get("TRAFFIC_ONTOLOGY_PROJECT_ROOT", Path.cwd()))
    print(f"Using project root: {project_root}")

    # -------------------------------------------------------------------------
    # Step 1: Load OSM data (ONLY ONCE)
    # -------------------------------------------------------------------------
    gpkg_file = project_root / "data_raw" / "OSM_data_filtered.gpkg"
    # we just load the raw columns and not parse other_tags here
    columns_to_load = ["osm_id", "highway", "name", "other_tags", "geometry"]
    
    print("--- LOADING OSM DATA (ONCE) ---")
    print("This is the main memory load. Please be patient...")
    try:
        gdf_osm_all = gpd.read_file(gpkg_file, layer="lines")
        # filter columns after loading
        gdf_osm_all = gdf_osm_all[columns_to_load]
        print(f"Loaded {len(gdf_osm_all)} total OSM road segments.")
    except Exception as e:
        print(f"Error loading GeoPackage: {e}")
        return
    
    # ran 'ogrinfo' command which confirmed the file is WGS84 (EPSG:4326)
    print("OSM data is in EPSG:4326.")

    # -------------------------------------------------------------------------
    # Step 2: Process each year
    # -------------------------------------------------------------------------
    for year in [2022, 2023, 2024]:
        # pass the full un-parsed gdf_osm_all to the function
        process_year(year, gdf_osm_all, project_root)

    print("\n--- All years processed! ---")


if __name__ == "__main__":
    main()