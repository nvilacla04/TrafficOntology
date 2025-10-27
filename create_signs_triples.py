"""
Script to Generate RDF Triples for Traffic Signs (Layer 3a).

1.  Loads and combines all 'traffic_signs_*.csv' files from the directory.
2.  Loads road network geometry from `OSM_data_filtered.gpkg`.
3.  Spatially joins signs to the nearest road segment to get the `osm_id`.
4.  Generates RDF triples for each sign, including its type (rvvCode), value
    (blackCode), a human-readable label, and links it to the road it's on.
5.  Saves the output to `traffic_signs.ttl`.
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

# --- Configuration ---
project_root = Path(os.environ.get("TRAFFIC_ONTOLOGY_PROJECT_ROOT", Path.cwd()))
data_rdf_dir = project_root / "data_rdf"
source_data_dir = project_root / "data_processed" / "traffic_signs_by_type_cleaned"
osm_gpkg_file = project_root / "OSM_data_filtered.gpkg"
output_ttl_file = data_rdf_dir / "traffic_signs.ttl" 
file_to_exclude = "traffic_signs_G13.csv"

# Define Namespaces
TRAFFIC = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/")
INST = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/instance/")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

# --- Mappings (from traffic signs dictionary) ---
sign_meanings = {
    'A1': 'Speed limit', 'A2': 'End of speed limit', 'A3': 'Speed limit on electronic display',
    'A4': 'Recommended speed', 'A5': 'End of recommended speed',
    'B1': 'Priority road', 'B2': 'End of priority road', 'B3': 'Crossroads with priority',
    'B4': 'Priority over minor road from left', 'B5': 'Priority over minor road from right',
    'B6': 'Give way sign', 'B7': 'Stop sign',
    'C1': 'Road closed in both directions', 'C2': 'No entry (one direction)', 'C3': 'One-way street',
    'C4': 'One-way street (alternative)', 'C5': 'Access permitted both sides', 'C6': 'No vehicles with >2 wheels',
    'C7': 'No goods vehicles', 'C7a': 'No buses', 'C7b': 'No buses and goods vehicles',
    'C8': 'No slow vehicles (<25 km/h)', 'C9': 'No riders, cattle, agricultural vehicles, bikes, mopeds',
    'C10': 'No motor vehicles on wheels', 'C11': 'No motorcycles', 'C12': 'No motor vehicles',
    'C13': 'No mopeds', 'C14': 'No bicycles', 'C15': 'No bicycles and mopeds', 'C16': 'No pedestrians',
    'C17': 'No goods vehicles over weight shown', 'C18': 'No vehicles wider than indicated',
    'C19': 'No vehicles higher than indicated', 'C20': 'No vehicles over axle load indicated',
    'C21': 'No vehicles over total weight indicated', 'C22': 'No hazardous substances vehicles',
    'C22a': 'Environmental zone', 'C22b': 'End of environmental zone',
    'D1': 'Roundabout', 'D2': 'Keep right/left of sign', 'D3': 'Pass either side', 'D4': 'Mandatory cycle lane',
    'D5': 'Mandatory path for riders', 'D6': 'Mandatory path for pedestrians', 'D7': 'Follow arrow direction',
    'E1': 'No parking', 'E2': 'No parking and stopping', 'E3': 'No parking for bicycles/mopeds',
    'E4': 'Parking area', 'E5': 'Taxi rank', 'E6': 'Disabled parking', 'E7': 'Loading/unloading only',
    'E8': 'Parking for specific vehicles', 'E9': 'Permit holders only', 'E10': 'Controlled parking zone entry',
    'E11': 'End of controlled parking zone', 'E12': 'Park and ride', 'E13': 'Car sharing parking',
    'F1': 'No overtaking', 'F2': 'End of no overtaking', 'F3': 'No overtaking by trucks',
    'F4': 'End of no overtaking by trucks', 'F5': 'Give way to oncoming traffic', 'F6': 'Priority over oncoming traffic',
    'F7': 'No U-turns', 'F8': 'End of all restrictions', 'F10': 'Stop (with additional info)',
    'F11': 'Slow vehicle lane', 'F13': 'Bus lane', 'F15': 'Tram lane', 'F19': 'Truck and bus lane',
    'F21': 'Truck lane',
    'G1': 'Motorway', 'G2': 'End of motorway', 'G3': 'Expressway', 'G4': 'End of expressway',
    'G5': 'Living street', 'G6': 'End of living street', 'G7': 'Footpath', 'G8': 'End of footpath',
    'G9': 'Bridleway', 'G10': 'End of bridleway', 'G11': 'Cycle route', 'G12': 'End of cycle route',
    'G12a': 'Cycle and moped route', 'G12b': 'End of cycle and moped route',
    'H1': 'Built-up area', 'H2': 'End of built-up area',
    'J1': 'Uneven road', 'J2': 'Bend to right', 'J3': 'Bend to left', 'J4': 'Double bend (right first)',
    'J5': 'Double bend (left first)', 'J6': 'Steep hill upward', 'J7': 'Steep hill downward',
    'J8': 'Dangerous crossing', 'J9': 'Roundabout ahead', 'J10': 'Level crossing with barriers',
    'J11': 'Level crossing without barriers', 'J12': 'Level crossing single track',
    'J13': 'Level crossing multiple tracks', 'J14': 'Cattle crossing', 'J15': 'Falling rocks',
    'J16': 'Slippery road', 'J17': 'Road narrows both sides', 'J18': 'Road narrows right',
    'J19': 'Road narrows left', 'J20': 'Road works', 'J21': 'Two-way traffic ahead',
    'J22': 'Traffic queues likely', 'J23': 'Pedestrian crossing', 'J24': 'Children crossing',
    'J25': 'Cyclist crossing', 'J26': 'Crossing for riders', 'J27': 'Wild animals',
    'J28': 'Livestock', 'J29': 'Two-way traffic', 'J30': 'Low-flying aircraft', 'J31': 'Crosswind',
    'J32': 'Traffic lights', 'J33': 'Drawbridge', 'J34': 'Danger of accidents',
    'J35': 'Quayside/riverbank', 'J36': 'Ice or snow risk', 'J37': 'Danger (general)',
    'J38': 'Speed bump', 'J39': 'Retractable bollard warning',
    'K1': 'Motorway info sign', 'K2': 'Advance motorway exit sign', 'K3': 'Service area sign',
    'K4': 'Lane instructions', 'K5': 'Non-motorway advance info', 'K6': 'Non-motorway directions',
    'K7': 'Cyclist signposts', 'K8': 'Multiple cyclist signposts', 'K9': 'Diversion route',
    'K10': 'Urban area directions', 'K11': 'Lane instructions (non-motorway)', 'K12': 'District names',
    'K13': 'District numbers', 'K14': 'Hazardous materials route',
    'L1': 'Height restriction (underpass)', 'L2': 'Pedestrian crossing', 'L3': 'Public transport stop',
    'L3a': 'Tram/bus stop', 'L3b': 'Bus stop', 'L3c': 'Tram stop', 'L4': 'Get in lane', 'L5': 'End of lane',
    'L6': 'Lane fork', 'L7': 'Number of lanes', 'L8': 'Pre-sorting', 'L9': 'No through road',
    'L10': 'Traffic info ahead', 'L11': 'Lane-specific info', 'L12': 'Single lane info',
    'L13': 'Tunnel info', 'L14': 'Hard shoulder', 'L15': 'Emergency facilities', 'L16': 'Emergency telephone',
    'L17': 'Fire extinguisher', 'L18': 'Phone and extinguisher', 'L19': 'Exit distances',
    'L20': 'Passing area right', 'L21': 'Passing area left',
    'onbekend': 'Unknown/unclassified sign'
}

def load_all_signs(directory: Path, exclude_file: str) -> pd.DataFrame:
    """Loads and combines all traffic sign CSVs from a directory."""
    print(f"Loading all CSVs from: {directory}")
    all_files = list(directory.glob("traffic_signs_*.csv"))
    # filter out the excluded file (we couldn't map it to a name)
    all_files = [f for f in all_files if f.name != exclude_file]
    
    if not all_files:
        raise FileNotFoundError(f"No 'traffic_signs_*.csv' files found in {directory}")

    df_list = []
    for f in all_files:
        try:
            df_list.append(pd.read_csv(f, low_memory=False))
        except Exception as e:
            print(f"Warning: Could not read {f.name}. Error: {e}")
            
    full_df = pd.concat(df_list, ignore_index=True)
    # drop records essential for linking and identification
    full_df = full_df.dropna(subset=['id', 'longitude', 'latitude', 'rvvCode'])
    print(f"Loaded a total of {len(full_df)} traffic sign records from {len(all_files)} files.")
    return full_df


def main():
    print("--- 1. LOADING TRAFFIC SIGN DATA ---")
    try:
        df_signs = load_all_signs(source_data_dir, file_to_exclude)
    except Exception as e:
        print(e)
        return

    print("--- 2. PREPARING SIGN GEODATAFRAME ---")
    # and now convert sign locations to a GeoDataFrame (they are WGS84)
    geometry_points = [Point(xy) for xy in zip(df_signs["longitude"], df_signs["latitude"])]
    gdf_signs_wgs84 = gpd.GeoDataFrame(df_signs, geometry=geometry_points)
    gdf_signs_wgs84.set_crs(epsg=4326, inplace=True)
    print("Sign GeoDataFrame created (EPSG:4326).")

    print("--- 3. LOADING ROAD NETWORK DATA ---")
    if not osm_gpkg_file.exists():
        print(f"Error: OSM GeoPackage not found at {osm_gpkg_file}")
        return
        
    gdf_roads_wgs84 = gpd.read_file(osm_gpkg_file, layer='lines', columns=['osm_id', 'geometry'])
    gdf_roads_wgs84 = gdf_roads_wgs84.to_crs(epsg=4326)
    print(f"Loaded {len(gdf_roads_wgs84)} road segments (geometry only).")

    print("--- 4. RE-PROJECTING FOR ACCURATE SPATIAL JOIN ---")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        signs_proj = gdf_signs_wgs84.to_crs(epsg=28992)
        roads_proj = gdf_roads_wgs84.to_crs(epsg=28992)
    print("Re-projected both datasets to EPSG:28992 (Dutch Grid).")

    print("--- 5. PERFORMING SPATIAL JOIN (sjoin_nearest) ---")
    # memory-intensive step but also necessary
    sensors_matched = gpd.sjoin_nearest(signs_proj, roads_proj, how='left')
    
    # map 'index_right' (from roads_proj) back to 'osm_id'
    osm_id_map = roads_proj['osm_id'].to_dict()
    sensors_matched['osm_id'] = sensors_matched['index_right'].map(osm_id_map)
    
    # join the 'osm_id' column back to the original WGS84 GDF
    final_signs = gdf_signs_wgs84.join(sensors_matched[['osm_id']])
    final_signs = final_signs.dropna(subset=['osm_id'])
    
    print(f"Successfully matched {len(final_signs)} out of {len(df_signs)} signs to a road segment.")
    
    # clean osm_id to clean string
    final_signs['osm_id'] = final_signs['osm_id'].astype(float).astype(int).astype(str)

    print("--- 6. GENERATING RDF TRIPLES ---")
    g = Graph()
    g.bind("traffic", TRAFFIC)
    g.bind("inst", INST)
    g.bind("geo", GEO)
    g.bind("xsd", XSD)
    g.bind("rdfs", RDFS)

    for index, sign in tqdm(final_signs.iterrows(), total=len(final_signs), desc="Generating Triples"):
        
        sign_id = str(sign['id']).strip()
        osm_id_str = str(sign['osm_id']).strip()
        rvv_code = str(sign['rvvCode']).strip()
        
        # --- Create URIs ---
        sign_uri = INST[f"sign_{sign_id}"]
        geom_uri = INST[f"geom_sign_{sign_id}"]
        road_uri = INST[f"road_{osm_id_str}"]

        # 1. Define the instance and its class
        g.add((sign_uri, RDF.type, TRAFFIC.TrafficSign))

        # 2. Add its machine-readable identifier
        g.add((sign_uri, TRAFFIC.signId, Literal(sign_id, datatype=XSD.string)))

        # 3. Add the RVV code (the type of sign)
        g.add((sign_uri, TRAFFIC.rvvCode, Literal(rvv_code, datatype=XSD.token)))
        
        # 4. Add the human-readable label
        sign_label = sign_meanings.get(rvv_code, "Unknown Sign")
        g.add((sign_uri, RDFS.label, Literal(sign_label, lang="en")))

        # 5. Add the sign's value
        black_code = sign.get('blackCode')
        if pd.notna(black_code):
            g.add((sign_uri, TRAFFIC.signValue, Literal(str(black_code), datatype=XSD.string)))

        # 6. Link the ROAD to the SIGN
        g.add((road_uri, TRAFFIC.hasTrafficSign, sign_uri))

        # 7. Create its geometry instance link
        g.add((sign_uri, GEO.hasGeometry, geom_uri))

        # 8. Define the geometry instance's type and WKT literal
        geom = sign['geometry']
        if geom and geom.is_valid:
            wkt_literal = Literal(wkt_dumps(geom), datatype=GEO.wktLiteral)
            g.add((geom_uri, RDF.type, GEO.Geometry))
            g.add((geom_uri, GEO.asWKT, wkt_literal))
        
    print("RDF triple generation complete.")

    print("--- 7. SAVING RDF FILE ---")
    output_ttl_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        g.serialize(destination=str(output_ttl_file), format="turtle")
        print(f"Successfully saved {len(g)} triples for {len(final_signs)} signs to '{output_ttl_file}'")
    except Exception as e:
        print(f"Error saving file: {e}")

    print("\n--- Script Finished ---")


if __name__ == "__main__":
    main()