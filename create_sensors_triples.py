"""
Script to Generate RDF Triples for Sensors (Layer 3b).

1.  Loads sensor inventory from `site_summary_with_coordinates.csv`.
2.  Loads road network geometry from `OSM_data_filtered.gpkg`.
3.  Spatially joins sensors to the nearest road segment to get the `osm_id`.
4.  Generates RDF triples for each sensor, linking it to the road it monitors.
5.  Saves the output to `sensors.ttl`.
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.wkt import dumps as wkt_dumps
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD, GEO
from pathlib import Path
import os
from tqdm import tqdm
import warnings
import numpy as np

# --- Configuration ---
project_root = Path(os.environ.get("TRAFFIC_ONTOLOGY_PROJECT_ROOT", Path.cwd()))
data_rdf_dir = project_root / "data_rdf"
source_data_dir = project_root / "data_processed" / "merged"
osm_gpkg_file = project_root / "OSM_data_filtered.gpkg"
sensor_csv_file = source_data_dir / "site_summary_with_coordinates.csv"
output_ttl_file = data_rdf_dir / "sensors.ttl" 

# Define Namespaces
TRAFFIC = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/")
INST = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/instance/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

# --- Mappings ---
# Maps the 'sensor_type' string to the ontology class URI
sensor_type_mapping = {
    "CountingPoint": TRAFFIC.CountingPoint,
    "MeasurementSection": TRAFFIC.MeasurementSection,
}
default_sensor_class = TRAFFIC.Sensor # fallback if type is unknown

def main():
    print("--- 1. LOADING SENSOR DATA ---")
    if not sensor_csv_file.exists():
        print(f"Error: Sensor file not found at {sensor_csv_file}")
        return
    
    df_sensors = pd.read_csv(sensor_csv_file)
    df_sensors = df_sensors.dropna(subset=['site_id', 'longitude', 'latitude', 'sensor_type'])
    print(f"Loaded {len(df_sensors)} sensor locations from CSV.")

    print("--- 2. PREPARING SENSOR GEODATAFRAME ---")
    # Convert sensor locations to a GeoDataFrame
    geometry_points = [Point(xy) for xy in zip(df_sensors["longitude"], df_sensors["latitude"])]
    gdf_sensors_wgs84 = gpd.GeoDataFrame(df_sensors, geometry=geometry_points)
    gdf_sensors_wgs84.set_crs(epsg=4326, inplace=True) # data is in WGS84 (Lat/Lon)
    print("Sensor GeoDataFrame created (EPSG:4326).")

    print("--- 3. LOADING ROAD NETWORK DATA ---")
    if not osm_gpkg_file.exists():
        print(f"Error: OSM GeoPackage not found at {osm_gpkg_file}")
        return
        
    # we are now loading only necessary columns from the road network to save memory
    gdf_roads_wgs84 = gpd.read_file(osm_gpkg_file, layer='lines', columns=['osm_id', 'geometry'])
    # ensure it's WGS84
    gdf_roads_wgs84 = gdf_roads_wgs84.to_crs(epsg=4326)
    print(f"Loaded {len(gdf_roads_wgs84)} road segments (geometry only).")

    print("--- 4. RE-PROJECTING FOR ACCURATE SPATIAL JOIN ---")
    # re-project both GeoDataFrames to the Dutch grid (EPSG:28992) for a meter-based join
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning) # suppress annoying CRSUserWarning
        sensors_proj = gdf_sensors_wgs84.to_crs(epsg=28992)
        roads_proj = gdf_roads_wgs84.to_crs(epsg=28992)
    print("Re-projected both datasets to EPSG:28992 (Dutch Grid).")

    print("--- 5. PERFORMING SPATIAL JOIN (sjoin_nearest) ---")
    # join sensors (left) to the nearest road segment (right)
    # this transfers 'osm_id' from roads_proj to the sensors_matched DataFrame
    sensors_matched = gpd.sjoin_nearest(sensors_proj, roads_proj, how='left')
    
    # We joined on projected data, but we want the original WGS84 lat/lon
    # for the WKT literal. We now merge the join results back onto the original WGS84 sensor GDF.
    # The 'index_right' column from sjoin_nearest corresponds to the index of 'roads_proj'.
    # We need to map this back to the 'osm_id' from 'roads_proj'.
    
    # Create a mapping from index to osm_id from the road data
    osm_id_map = roads_proj['osm_id'].to_dict()
    
    # Map the 'index_right' to get the 'osm_id' for each sensor
    sensors_matched['osm_id'] = sensors_matched['index_right'].map(osm_id_map)
    
    # drop the projected geometry and merge the osm_id back onto the original WGS84 GDF
    final_sensors = gdf_sensors_wgs84.join(sensors_matched[['osm_id']])
    final_sensors = final_sensors.dropna(subset=['osm_id']) # drop sensors that found no road
    
    print(f"Successfully matched {len(final_sensors)} out of {len(df_sensors)} sensors to a road segment.")
    
    # clean osm_id to clean string
    final_sensors['osm_id'] = final_sensors['osm_id'].astype(float).astype(int).astype(str)

    print("--- 6. GENERATING RDF TRIPLES ---")
    g = Graph()
    g.bind("traffic", TRAFFIC)
    g.bind("inst", INST)
    g.bind("geo", GEO)
    g.bind("xsd", XSD)
    g.bind("rdfs", RDFS)

    for index, sensor in tqdm(final_sensors.iterrows(), total=len(final_sensors), desc="Generating Triples"):
        
        site_id = str(sensor['site_id']).strip()
        osm_id_str = str(sensor['osm_id']).strip()
        sensor_type_str = str(sensor['sensor_type']).strip()
        
        # --- Create URIs ---
        sensor_uri = INST[f"sensor_{site_id}"]
        geom_uri = INST[f"geom_sensor_{site_id}"]
        road_uri = INST[f"road_{osm_id_str}"]

        # 1. Define the instance and its base class
        g.add((sensor_uri, RDF.type, TRAFFIC.Sensor))

        # 2. Define its specific subclass
        sensor_class = sensor_type_mapping.get(sensor_type_str, default_sensor_class)
        g.add((sensor_uri, RDF.type, sensor_class))

        # 3. Add its human-readable label
        g.add((sensor_uri, RDFS.label, Literal(site_id, lang="en")))

        # 4. Add its machine-readable identifier (the new property)
        g.add((sensor_uri, TRAFFIC.sensorId, Literal(site_id, datatype=XSD.string)))

        # 5. Link it to the road segment it monitors
        g.add((sensor_uri, TRAFFIC.monitors, road_uri))

        # 6. Create its geometry instance link
        g.add((sensor_uri, GEO.hasGeometry, geom_uri))

        # 7. Define the geometry instance's type and WKT literal
        geom = sensor['geometry']
        if geom and geom.is_valid:
            wkt_literal = Literal(wkt_dumps(geom), datatype=GEO.wktLiteral)
            g.add((geom_uri, RDF.type, GEO.Geometry))
            g.add((geom_uri, GEO.asWKT, wkt_literal))
        
    print("RDF triple generation complete.")

    print("--- 7. SAVING RDF FILE ---")
    output_ttl_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        g.serialize(destination=str(output_ttl_file), format="turtle")
        print(f"Successfully saved {len(g)} triples for {len(final_sensors)} sensors to '{output_ttl_file}'")
    except Exception as e:
        print(f"Error saving file: {e}")

    print("\n--- Script Finished ---")


if __name__ == "__main__":
    main()