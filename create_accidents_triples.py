"""
Final Script to Generate RDF Triples for Accidents (Layer 2) - v4 (Fixes)

Reads enriched accident CSVs (2022-2024), maps BRON data to the ontology
using simplified vehicle categories, creates Accident instances, links them
to RoadSegment instances, and adds relevant properties including involved
vehicles (Party 1 & 2) and context (Severity, Road Condition).

Uses LOW-MEMORY approach for coordinate transformation.
Links classifications to pre-defined instances (e.g., inst:Dry).
Creates specific, uniquely URI'd vehicle instances for each involved party,
typed according to the simplified vehicle class mapping.
Speed Limit from BRON ('maximum_snelheid') is NOT added to accident triples.
Includes fixes for geometry processing errors and RDF term validation.
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString # Import base types for checking
from shapely.wkt import dumps as wkt_dumps # Correct import
from rdflib import Graph, Literal, Namespace, URIRef, BNode # Import Node types
from rdflib.namespace import RDF, RDFS, XSD, GEO
from rdflib.term import Node # Import Node for type checking
from pathlib import Path
import os
from tqdm import tqdm
import warnings
import numpy as np
import re

# --- Configuration ---
project_root = Path(os.environ.get("TRAFFIC_ONTOLOGY_PROJECT_ROOT", Path.cwd()))
data_rdf_dir = project_root / "data_rdf"
output_ttl_file = data_rdf_dir / "accidents.ttl" # Output file
years_to_process = [2022, 2023, 2024]

# Define Namespaces
TRAFFIC = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/")
INST = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/instance/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

# --- Helper function ---
def parse_hstore(hstore_string: str) -> dict:
    if hstore_string is None: return {}
    try: return dict(re.findall(r'"(.*?)"=>"(.*?)"', hstore_string))
    except Exception: return {}

# --- Mappings ---
severity_mapping = {
    "Uitsluitend materiele schade": INST.MaterialDamageOnly,
    "Letsel": INST.Injury,
    "Dodelijk": INST.Fatal,
}

# --- Simplified Vehicle Mapping to CLASSES ---
vehicle_class_mapping = {
    # Car Group
    "Personenauto": TRAFFIC.Car,
    "Bestelauto": TRAFFIC.Car,
    "Brommobiel": TRAFFIC.Car,
    # Bicycle Group
    "Fiets": TRAFFIC.Bycicle,
    "e-bike": TRAFFIC.Bycicle,
    # Moped Group
    "Bromfiets": TRAFFIC.Moped,
    "Snorfiets": TRAFFIC.Moped,
    "Scootmobiel": TRAFFIC.Moped,
    # Pedestrian
    "Voetganger": TRAFFIC.Pedestrian,
    # Truck Group
    "Trekker": TRAFFIC.Truck,
    "Vrachtauto": TRAFFIC.Truck,
    "Trekker met oplegger": TRAFFIC.Truck,
    "Landbouwvoertuig": TRAFFIC.Truck, # Simplified grouping
    # Other Vehicle (explicitly mapped)
    "Motor": TRAFFIC.otherVehicle,
    "Bus": TRAFFIC.otherVehicle,
    "Trein/tram": TRAFFIC.otherVehicle,
    "Onbekend voertuig i.g.v. doorrijder": TRAFFIC.otherVehicle,
    # --- Non-Vehicles to Ignore ---
    "Dier": None, "Boom": None, "Lichtmast": None,
    "Overig wegmeubilair": None, "Overig vast object": None, "Los voorwerp": None,
}
default_vehicle_class = TRAFFIC.otherVehicle

road_condition_mapping = {
    "Droog": INST.Dry, "Nat": INST.Wet, "Sneeuw/ijzel": INST.Snow,
}

print("--- 1. INITIALIZING RDF GRAPH ---")
g = Graph()
g.bind("traffic", TRAFFIC)
g.bind("inst", INST)
g.bind("geo", GEO)
g.bind("xsd", XSD)
g.bind("rdfs", RDFS)

# Pre-declare instances (if not loading category_instances.ttl separately)
# for uri in severity_mapping.values(): g.add((uri, RDF.type, TRAFFIC.Severity))
# for uri in road_condition_mapping.values(): g.add((uri, RDF.type, TRAFFIC.RoadCondition))
# g.add((INST.Dry, RDF.type, TRAFFIC.RoadCondition)); g.add((INST.Wet, RDF.type, TRAFFIC.RoadCondition)); g.add((INST.Snow, RDF.type, TRAFFIC.RoadCondition))

total_accidents_processed = 0

print("--- 2. PROCESSING ENRICHED ACCIDENT FILES ---")

for year in years_to_process:
    csv_file = data_rdf_dir / f"accidents_enriched_osm_{year}.csv"
    print(f"\n--- Processing: {csv_file.name} ---")
    if not csv_file.exists(): continue
    try:
        df_accidents = pd.read_csv(csv_file, low_memory=False, dtype={'osm_id': str, 'verkeersongeval_nummer': str})
        df_accidents = df_accidents.dropna(subset=['verkeersongeval_nummer', 'osm_id', 'longitude', 'latitude'])
        df_accidents.replace({np.nan: None}, inplace=True)
        print(f"Loaded {len(df_accidents)} accidents for {year}.")
        total_accidents_processed += len(df_accidents)
    except Exception as e:
        print(f"Error loading {csv_file.name}: {e}"); continue

    # --- Convert coordinates back to GeoDataFrame for WKT ---
    try:
        geometry_points_rdnew = [Point(xy) for xy in zip(df_accidents["longitude"], df_accidents["latitude"])]
        gdf_accidents = gpd.GeoDataFrame(df_accidents, geometry=geometry_points_rdnew)
        gdf_accidents.set_crs(epsg=28992, inplace=True)
        gdf_accidents = gdf_accidents.to_crs(epsg=4326) # WGS84 for POINT literal
    except Exception as e:
        print(f"ERROR during coordinate conversion for {year}: {e}. Skipping year.")
        continue

    # --- Iterate and create triples ---
    for index, acc in tqdm(gdf_accidents.iterrows(), total=len(gdf_accidents), desc=f"Generating {year} triples"):
        bron_id_str = str(acc.get('verkeersongeval_nummer', '')).strip()
        osm_id_val = acc.get('osm_id')
        if osm_id_val is None: continue
        osm_id_str = str(osm_id_val).split('.')[0]
        if not bron_id_str or not osm_id_str or osm_id_str.lower() == 'nan': continue

        acc_uri = INST[f"acc_{bron_id_str}"]
        road_uri = INST[f"road_{osm_id_str}"]
        acc_geom_uri = INST[f"geom_acc_{bron_id_str}"]

        g.add((acc_uri, RDF.type, TRAFFIC.Accident))
        g.add((acc_uri, TRAFFIC.occursOn, road_uri))
        g.add((acc_uri, TRAFFIC.bronID, Literal(bron_id_str)))

        acc_year = acc.get('jaar_ongeval')
        if acc_year is not None:
             try: g.add((acc_uri, TRAFFIC.year, Literal(int(acc_year), datatype=XSD.integer)))
             except (ValueError, TypeError): pass
        party_count = acc.get('aantal_partijen')
        if party_count is not None:
            try:
                party_count_int = int(party_count)
                if party_count_int > 0: g.add((acc_uri, TRAFFIC.partyCount, Literal(party_count_int, datatype=XSD.positiveInteger)))
            except (ValueError, TypeError): pass
        location_type = acc.get('bebouwde_kom')
        if location_type is not None: g.add((acc_uri, TRAFFIC.locationType, Literal(str(location_type), lang="nl")))

        severity_str = acc.get('verkeersongeval_afloop')
        if severity_str in severity_mapping: g.add((acc_uri, TRAFFIC.hasSeverity, severity_mapping[severity_str]))
        condition_str = acc.get('wegdek')
        if condition_str in road_condition_mapping: g.add((acc_uri, TRAFFIC.hasRoadCondition, road_condition_mapping[condition_str]))

        # --- Vehicle Mapping (Party 1 and Party 2) ---
        for i, party_col in enumerate(['partij_1_objecttype', 'partij_2_objecttype']):
            vehicle_str = acc.get(party_col)
            if vehicle_str is not None and str(vehicle_str).strip():
                vehicle_str_clean = str(vehicle_str).strip()
                if vehicle_class_mapping.get(vehicle_str_clean) is None: continue # Skip ignored types

                vehicle_class_uri = vehicle_class_mapping.get(vehicle_str_clean, default_vehicle_class)
                vehicle_inst_uri = INST[f"vehicle_{bron_id_str}_p{i+1}"]

                # --- ASSERTION FIX: Check if URIs are valid Nodes ---
                if not isinstance(vehicle_inst_uri, Node):
                    print(f"ERROR: vehicle_inst_uri {vehicle_inst_uri} is not a valid Node for {bron_id_str}")
                    continue
                if not isinstance(vehicle_class_uri, Node):
                    print(f"ERROR: vehicle_class_uri {vehicle_class_uri} (from '{vehicle_str_clean}') is not a valid Node for {bron_id_str}")
                    continue
                if not isinstance(TRAFFIC.Vehicle, Node):
                    print(f"ERROR: TRAFFIC.Vehicle {TRAFFIC.Vehicle} is not a valid Node for {bron_id_str}")
                    continue
                # --- END FIX ---

                g.add((vehicle_inst_uri, RDF.type, vehicle_class_uri)) # Specific type class
                g.add((vehicle_inst_uri, RDF.type, TRAFFIC.Vehicle)) # General type class
                g.add((acc_uri, TRAFFIC.involvesVehicle, vehicle_inst_uri))

        # --- Add Geometry ---
        geom = acc.get('geometry')
        if geom and hasattr(geom, 'is_valid'): # Check if it's a valid Shapely geometry object
            try:
                if geom.is_valid:
                    # --- GEOMETRY FIX: Ensure wkt_dumps is callable ---
                    if callable(wkt_dumps):
                         wkt_literal = Literal(wkt_dumps(geom), datatype=GEO.wktLiteral)
                         g.add((acc_geom_uri, RDF.type, GEO.Geometry))
                         g.add((acc_geom_uri, GEO.asWKT, wkt_literal))
                         g.add((acc_uri, GEO.hasGeometry, acc_geom_uri))
                    else:
                        print(f"ERROR: wkt_dumps is not callable for accident {bron_id_str}. Check imports.")
                    # --- END FIX ---
                else:
                    print(f"Warning: Invalid geometry object for accident {bron_id_str}. Type: {type(geom)}. Skipping geometry.")
            except Exception as e:
                 # --- GEOMETRY FIX: Print the actual exception ---
                 print(f"Warning: Could not process geometry for accident {bron_id_str}. Error: {e!r}") # Use !r for detailed error
                 # --- END FIX ---
        elif geom:
            print(f"Warning: Non-geometry object found in geometry column for accident {bron_id_str}. Type: {type(geom)}. Skipping geometry.")


print(f"\n--- 3. SAVING RDF FILE ({total_accidents_processed} total accidents processed) ---")
output_ttl_file.parent.mkdir(parents=True, exist_ok=True)
try:
    g.serialize(destination=str(output_ttl_file), format="turtle")
    print(f"Successfully saved accident triples to '{output_ttl_file}'")
except Exception as e:
    print(f"Error saving file: {e}")
print("\n--- Script Finished ---")