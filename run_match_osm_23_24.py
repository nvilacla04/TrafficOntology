"""
Script to match BRON accident data for 2023 and 2024 to OSM road segments.

This script iterates over the accident datasets for the years 2023 and 2024,
converts each to a GeoDataFrame, reprojects the data to a projected CRS for
accurate nearest-neighbour searches, and spatially joins each accident point
to the nearest OSM road segment sharing the same street name.  Selected
attributes from the road segment (e.g. `highway`, `maxspeed`, `surface`,
`zone:traffic`) are appended to the accident records.  Separate enriched
datasets are written out as CSV files for each year.

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


def match_accidents_to_roads(df_bron: pd.DataFrame, gdf_osm_all: gpd.GeoDataFrame, year: int) -> gpd.GeoDataFrame:
    """Match accidents to the nearest road segment sharing the street name.

    The input accident DataFrame is converted to a GeoDataFrame, reprojected to
    a projected CRS (EPSG:28992) for accurate spatial operations, and joined
    to the OSM roads using a nearest spatial join.  Only accidents with valid
    location data and street names are retained.

    Parameters
    ----------
    df_bron : pandas.DataFrame
        The BRON accident data for a specific year.
    gdf_osm_all : geopandas.GeoDataFrame
        The OSM road network with parsed attributes and reprojected to a
        projected CRS.
    year : int
        The year of the accidents (used for logging).

    Returns
    -------
    geopandas.GeoDataFrame
        The matched accidents enriched with road attributes.
    """
    # Filter accidents with valid location and street name
    df_bron = df_bron.dropna(subset=["longitude", "latitude", "straatnaam"])
    print(f"Loaded {len(df_bron)} accidents with valid locations and street names from {year}.")

    # Convert accidents to GeoDataFrame with geometry
    geometry_points = [Point(xy) for xy in zip(df_bron["longitude"], df_bron["latitude"])]
    gdf_bron = gpd.GeoDataFrame(df_bron, geometry=geometry_points, crs="EPSG:4326")

    # Reproject accidents and roads to a projected CRS (RD New / Amersfoort)
    gdf_bron = gdf_bron.to_crs(epsg=28992)
    gdf_osm_proj = gdf_osm_all.to_crs(epsg=28992)

    # Perform nearest spatial join for each unique street name
    unique_bron_names = gdf_bron["straatnaam"].unique()
    print(f"Found {len(unique_bron_names)} unique street names to process for {year}.")
    matched_data_list = []
    for name in tqdm(unique_bron_names, desc=f"Matching streets for {year}"):
        accidents_on_street = gdf_bron[gdf_bron["straatnaam"] == name]
        roads_with_name = gdf_osm_proj[gdf_osm_proj["name"] == name]
        if roads_with_name.empty:
            continue
        matched = gpd.sjoin_nearest(
            accidents_on_street,
            roads_with_name,
            how="left",
        )
        matched_data_list.append(matched)

    if not matched_data_list:
        raise RuntimeError(f"No matches were found between accidents and roads for {year}.")

    final_matched_gdf = pd.concat(matched_data_list)
    final_matched_gdf = final_matched_gdf.dropna(subset=["index_right"])
    final_matched_gdf = final_matched_gdf.rename(columns={"name": "osm_road_name"})
    print(f"Successfully matched {len(final_matched_gdf)} out of {len(gdf_bron)} accidents for {year}.")
    return final_matched_gdf


def main() -> None:
    # -------------------------------------------------------------------------
    # File paths for accidents and output by year
    # -------------------------------------------------------------------------
    accidents_files = {
        2023: r"C:\\Users\\nicol\\Documents\\TrafficOntology_Project\\TrafficOntology\\data_processed\\BRON_cleaned\\ongevallen_2023_clean.csv",
        2024: r"C:\\Users\\nicol\\Documents\\TrafficOntology_Project\\TrafficOntology\\data_processed\\BRON_cleaned\\ongevallen_2024_clean.csv",
    }
    output_files = {
        2023: r"C:\\Users\\nicol\\Documents\\TrafficOntology_Project\\TrafficOntology\\data_rdf\\accidents_enriched_with_osm_2023.csv",
        2024: r"C:\\Users\\nicol\\Documents\\TrafficOntology_Project\\TrafficOntology\\data_rdf\\accidents_enriched_with_osm_2024.csv",
    }

    # -------------------------------------------------------------------------
    # Load OSM road network once (common for all years)
    # -------------------------------------------------------------------------
    gpkg_file = r"C:\\Users\\nicol\\Documents\\TrafficOntology_Project\\TrafficOntology\\OSM_data_filtered.gpkg"
    columns_to_load = [
        "osm_id",
        "highway",
        "name",
        "other_tags",
        "geometry",
    ]
    print(f"Loading OSM road network from '{gpkg_file}'...")
    gdf_osm_all = gpd.read_file(gpkg_file, layer="lines", columns=columns_to_load)
    print(f"Loaded {len(gdf_osm_all)} OSM road segments.")

    # Parse 'other_tags' to extract attributes
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
    # Process each year
    # -------------------------------------------------------------------------
    for year, accidents_path in accidents_files.items():
        print(f"\n=== Processing accidents for {year} ===")
        try:
            df_bron_year = pd.read_csv(accidents_path)
        except FileNotFoundError:
            print(f"WARNING: accidents file not found for {year}: {accidents_path}")
            continue
        # Match accidents to roads
        matched_gdf = match_accidents_to_roads(df_bron_year, gdf_osm_all, year)
        # Save the enriched dataset
        out_path = output_files[year]
        matched_gdf.to_csv(out_path, index=False)
        print(f"Saved enriched data for {year} to '{out_path}'")


if __name__ == "__main__":
    main()