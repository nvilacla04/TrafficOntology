"""
Script to Generate RDF Triples for Traffic Flow & Speed (Layer 4).

1.  Loads cleaned flow data from `traffic_flow_with_coordinates.csv`.
2.  Loads cleaned speed data from `traffic_speed_with_coordinates.csv`.
3.  Cleans and merges the two datasets, grouping by 'site_id' and 'timestamp'
    to create a single, unified measurement for each time point.
4.  Generates RDF triples for each measurement, creating a 'VehicleFlow' instance.
5.  Links each 'VehicleFlow' to the 'Sensor' that measured it (`traffic:measuredBy`).
6.  Saves the output to `traffic_flow.ttl`.
"""

import pandas as pd
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD, GEO
from pathlib import Path
import os
from tqdm import tqdm
import warnings
import numpy as np
import re # For sanitizing timestamps for URIs

# --- Configuration ---
project_root = Path(os.environ.get("TRAFFIC_ONTOLOGY_PROJECT_ROOT", Path.cwd()))
source_data_dir = project_root / "data_processed" / "merged"
output_ttl_file = project_root / "data_rdf" / "traffic_flow.ttl" # Output file

flow_csv_file = source_data_dir / "traffic_flow_with_coordinates.csv"
speed_csv_file = source_data_dir / "traffic_speed_with_coordinates.csv"

# Define Namespaces
TRAFFIC = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/")
INST = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/instance/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

def sanitize_for_uri(text: str) -> str:
    """Cleans a timestamp string to be a valid URI component."""
    # Replaces ':', '+', ' ' with safe characters
    return re.sub(r"[:\+ ]", "_", text)

def main():
    print("--- 1. LOADING TRAFFIC DATA ---")
    if not flow_csv_file.exists():
        print(f"Error: Flow file not found at {flow_csv_file}")
        return
    if not speed_csv_file.exists():
        print(f"Error: Speed file not found at {speed_csv_file}")
        return

    try:
        df_flow = pd.read_csv(flow_csv_file, low_memory=False)
        df_speed = pd.read_csv(speed_csv_file, low_memory=False)
        print(f"Loaded {len(df_flow)} flow records and {len(df_speed)} speed records.")
    except Exception as e:
        print(f"Error loading CSVs: {e}")
        return

    print("--- 2. CLEANING AND MERGING DATA ---")
    
    # Clean data: Drop rows with missing 'measurement_index' (they seem to be duplicates)
    df_flow_clean = df_flow.dropna(subset=['measurement_index'])
    df_speed_clean = df_speed.dropna(subset=['measurement_index'])

    # Select only the columns we need before merging
    df_flow_clean = df_flow_clean[['site_id', 'timestamp', 'flow_rate']].dropna()
    df_speed_clean = df_speed_clean[['site_id', 'timestamp', 'speed']].dropna()

    # Group by site_id and timestamp and calculate the mean
    # This handles multiple measurements for the same sensor at the same time
    df_flow_agg = df_flow_clean.groupby(['site_id', 'timestamp']).mean().reset_index()
    df_speed_agg = df_speed_clean.groupby(['site_id', 'timestamp']).mean().reset_index()
    print(f"Aggregated to {len(df_flow_agg)} unique flow events and {len(df_speed_agg)} unique speed events.")

    # Merge the aggregated flow and speed data
    df_merged = pd.merge(df_flow_agg, df_speed_agg, on=['site_id', 'timestamp'], how='outer')
    
    # Convert timestamp to proper datetime objects for formatting
    try:
        df_merged['timestamp_dt'] = pd.to_datetime(df_merged['timestamp'])
    except Exception as e:
        print(f"Warning: Could not parse all timestamps: {e}. Attempting to continue.")
        df_merged['timestamp_dt'] = pd.to_datetime(df_merged['timestamp'], errors='coerce')

    # Drop any rows that failed timestamp conversion or have no data
    df_merged = df_merged.dropna(subset=['timestamp_dt', 'site_id'])
    
    # Drop rows where both speed and flow are missing
    df_merged = df_merged.dropna(subset=['flow_rate', 'speed'], how='all')
    
    print(f"Created {len(df_merged)} merged VehicleFlow events.")

    print("--- 3. GENERATING RDF TRIPLES ---")
    g = Graph()
    g.bind("traffic", TRAFFIC)
    g.bind("inst", INST)
    g.bind("geo", GEO) # Although not used here, good practice
    g.bind("xsd", XSD)
    g.bind("rdfs", RDFS)
    
    flow_instances_created = 0
    
    for index, row in tqdm(df_merged.iterrows(), total=len(df_merged), desc="Generating Triples"):
        
        site_id = str(row['site_id']).strip()
        timestamp_obj = row['timestamp_dt']
        
        # Format timestamp to ISO 8601 (which it should already be)
        # and create a sanitized version for the URI
        try:
            timestamp_iso = timestamp_obj.isoformat()
            timestamp_uri_part = sanitize_for_uri(timestamp_iso)
        except Exception:
            continue # Skip if timestamp is invalid

        # --- Create URIs ---
        flow_uri = INST[f"flow_{site_id}_{timestamp_uri_part}"]
        sensor_uri = INST[f"sensor_{site_id}"] # Link to the sensor instance

        # --- Create Triples ---
        
        # 1. Define the instance and its class
        g.add((flow_uri, RDF.type, TRAFFIC.VehicleFlow))

        # 2. Link to the Sensor that took the measurement
        g.add((flow_uri, TRAFFIC.measuredBy, sensor_uri))

        # 3. Add the flow rate (if it exists)
        flow_rate_val = row.get('flow_rate')
        if pd.notna(flow_rate_val):
            try:
                g.add((flow_uri, TRAFFIC.flowRate, Literal(int(flow_rate_val), datatype=XSD.integer)))
            except (ValueError, TypeError): pass # Skip if not a valid integer

        # 4. Add the average speed (if it exists)
        speed_val = row.get('speed')
        if pd.notna(speed_val):
            try:
                g.add((flow_uri, TRAFFIC.avgSpeed, Literal(float(speed_val), datatype=XSD.float)))
            except (ValueError, TypeError): pass # Skip if not a valid float

        # 5. Add the exact time of the measurement
        g.add((flow_uri, TRAFFIC.timestamp, Literal(timestamp_iso, datatype=XSD.dateTime)))
        
        flow_instances_created += 1

    print("RDF triple generation complete.")

    print("--- 4. SAVING RDF FILE ---")
    output_ttl_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        g.serialize(destination=str(output_ttl_file), format="turtle")
        print(f"Successfully saved {len(g)} triples for {flow_instances_created} VehicleFlow instances to '{output_ttl_file}'")
    except Exception as e:
        print(f"Error saving file: {e}")

    print("\n--- Script Finished ---")


if __name__ == "__main__":
    main()