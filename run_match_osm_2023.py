"""
Script to match BRON accident data for 2023 to OSM road segments.

This script reads a cleaned BRON accidents CSV for the year 2023, converts it
to a GeoDataFrame, and spatially joins each accident point to the nearest OSM
road segment sharing the same street name.  Selected attributes from the road
segment (e.g. `highway`, `maxspeed`, `surface`, `zone:traffic`) are appended
to the accident records.  The enriched dataset is then written out as a CSV
file to the specified `out_path`.

Update the paths below to point at your local files.  Raw strings are used
for Windows paths so that backslashes do not escape characters.
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import re
from tqdm import tqdm


# -----------------------------------------------------------------------------
# Helper function to parse hstore strings in OSM's `other_tags` column
# -----------------------------------------------------------------------------
def parse_hstore(hstore_string: str) -> dict:
    """Parse a PostGIS hstore formatted string into a Python dictionary.

    Each key/value pair in the hstore string is enclosed in double quotes
    and separated by a comma.  If the input is None or cannot be parsed,
    an empty dictionary is returned.

    Parameters
    ----------
    hstore_string : str
        The hstore string to parse (e.g. '"maxspeed"=>"50","surface"=>"asphalt"').

    Returns
    -------
    dict
        A dictionary mapping keys to values extracted from the hstore string.
    """
    if hstore_string is None:
        return {}
    try:
        return dict(re.findall(r'"(.*?)"=>"(.*?)"', hstore_string))
    except Exception:
        return {}


def main() -> None:
    # -------------------------------------------------------------------------
    # Step 1: Load the BRON accident data for 2023
    # -------------------------------------------------------------------------
    bron_csv_file = r"C:\Users\nicol\Documents\TrafficOntology_Project\TrafficOntology\data_processed\BRON_cleaned\ongevallen_2023_clean.csv"

    print("--- 1. LOADING DATA ---")
    try:
        df_bron = pd.read_csv(bron_csv_file)
    except FileNotFoundError:
        raise FileNotFoundError(f"BRON accidents file not found: {bron_csv_file}")
    # Filter out accidents without usable location information
    df_bron = df_bron.dropna(subset=["longitude", "latitude", "straatnaam"])
    print(f"Loaded {len(df_bron)} accidents with valid locations and street names from 2023.")

    # -------------------------------------------------------------------------
    # Step 1b: Load OSM road network data
    # -------------------------------------------------------------------------
    gpkg_file = r"C:\Users\nicol\Documents\TrafficOntology_Project\TrafficOntology\OSM_data_filtered.gpkg"
    # Only load the columns we need to keep memory usage down
    columns_to_load = [
        "osm_id",
        "highway",
        "name",
        "other_tags",
        "geometry",
    ]
    print(f"Loading OSM road network from '{gpkg_file}'...")
    # The layer name 'lines' corresponds to road segments in the GeoPackage
    gdf_osm_all = gpd.read_file(gpkg_file, layer="lines", columns=columns_to_load)
    print(f"Loaded {len(gdf_osm_all)} OSM road segments.")

    # -------------------------------------------------------------------------
    # Step 2: Prepare data by converting to GeoDataFrames and parsing tags
    # -------------------------------------------------------------------------
    print("\n--- 2. PREPARING DATA ---")
    # Convert the BRON DataFrame into a GeoDataFrame
    geometry_points = [Point(xy) for xy in zip(df_bron["longitude"], df_bron["latitude"])]
    gdf_bron = gpd.GeoDataFrame(df_bron, geometry=geometry_points)
    # Set the CRS to WGS84 (EPSG:4326)
    gdf_bron.set_crs(epsg=4326, inplace=True)

    # Ensure the OSM GeoDataFrame uses the same CRS
    gdf_osm_all = gdf_osm_all.to_crs(epsg=4326)
    print("Converted both datasets to CRS EPSG:4326 (standard Lon/Lat).")

    # Parse the 'other_tags' column to extract useful attributes
    print("Parsing 'other_tags' to extract maxspeed, surface, etc...")
    osm_tags_parsed = gdf_osm_all["other_tags"].apply(parse_hstore)
    osm_tags_df = pd.DataFrame.from_records(osm_tags_parsed, index=gdf_osm_all.index)
    gdf_osm_all = gdf_osm_all.join(osm_tags_df)
    # Select only the columns we want to retain
    columns_to_keep = [
        "geometry",
        "osm_id",
        "name",
        "highway",
        "maxspeed",
        "surface",
        "zone:traffic",
    ]
    final_osm_columns = [col for col in columns_to_keep if col in gdf_osm_all.columns]
    gdf_osm_all = gdf_osm_all[final_osm_columns]
    print("OSM data prepared and attributes extracted.")

    # -------------------------------------------------------------------------
    # Step 3: Match accidents to roads based on street name and proximity
    # -------------------------------------------------------------------------
    print("\n--- 3. MATCHING ACCIDENTS TO ROADS ---")
    unique_bron_names = gdf_bron["straatnaam"].unique()
    print(f"Found {len(unique_bron_names)} unique street names to process.")
    matched_data_list = []
    for name in tqdm(unique_bron_names, desc="Matching streets"):
        accidents_on_street = gdf_bron[gdf_bron["straatnaam"] == name]
        roads_with_name = gdf_osm_all[gdf_osm_all["name"] == name]
        if roads_with_name.empty:
            continue
        matched = gpd.sjoin_nearest(
            accidents_on_street,
            roads_with_name,
            how="left",
        )
        matched_data_list.append(matched)
    print("Matching complete.")

    # -------------------------------------------------------------------------
    # Step 4: Clean up the matched data and output
    # -------------------------------------------------------------------------
    print("\n--- 4. CLEANING FINAL DATA ---")
    if not matched_data_list:
        raise RuntimeError("No matches were found between accidents and roads.")
    final_matched_gdf = pd.concat(matched_data_list)
    final_matched_gdf = final_matched_gdf.dropna(subset=["index_right"])
    final_matched_gdf = final_matched_gdf.rename(columns={"name": "osm_road_name"})
    print(f"Successfully matched {len(final_matched_gdf)} out of {len(gdf_bron)} accidents.")
    print("\n--- SAMPLE OF MATCHING RESULTS ---")
    print(final_matched_gdf.head())

    # Save the enriched dataset to CSV
    out_path = r"C:\Users\nicol\Documents\TrafficOntology_Project\TrafficOntology\data_rdf\accidents_enriched_with_osm_2023.csv"
    final_matched_gdf.to_csv(out_path, index=False)
    print(f"\nSaved enriched data to '{out_path}'")


if __name__ == "__main__":
    main()