import fiona # needed for low-memory reading of the gpkg file. using pandas library would use too much RAM so we decided for this less-efficient option
import geopandas as gpd # still needed for CRS checks if necessary
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD, GEO
from shapely.geometry import shape 
from shapely.wkt import dumps as wkt_dumps
import re
from pathlib import Path
import os
from tqdm import tqdm
import warnings

# --- Helper function ---
def parse_hstore(hstore_string: str) -> dict:
    """Parse a PostGIS hstore formatted string into a Python dictionary."""
    if hstore_string is None:
        return {}
    try:
        return dict(re.findall(r'"(.*?)"=>"(.*?)"', hstore_string))
    except Exception:
        return {}

# --- Configuration ---
project_root = Path(os.environ.get("TRAFFIC_ONTOLOGY_PROJECT_ROOT", Path.cwd()))
gpkg_file = project_root / "OSM_data_filtered.gpkg"
output_ttl_file = project_root / "data_rdf" / "road_network.ttl" 
target_crs = "EPSG:4326" # need WGS84 for GeoSPARQL WKT literals

# Define Namespaces
TRAFFIC = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/")
INST = Namespace("http://www.semanticweb.org/nicol/ontologies/2025/9/traffic/instance/")
# GEO namespace is already defined in rdflib.namespace

# Mapping from OSM highway values to ontology classes
highway_mapping = {
    "motorway": TRAFFIC.Motorway,"trunk": TRAFFIC.Trunk,"primary": TRAFFIC.Primary,"secondary": TRAFFIC.Secondary,
    "tertiary": TRAFFIC.Tertiary,"residential": TRAFFIC.Residential,"living_street": TRAFFIC.LivingStreet,"unclassified": TRAFFIC.Unclassified,
    "motorway_link": TRAFFIC.MotorwayLink,"trunk_link": TRAFFIC.TrunkLink,"primary_link": TRAFFIC.PrimaryLink,"secondary_link": TRAFFIC.SecondaryLink,"tertiary_link": TRAFFIC.TertiaryLink,
}

print("--- 1. INITIALIZING RDF GRAPH ---")
# Initialize RDF graph
g = Graph()
g.bind("traffic", TRAFFIC)
g.bind("inst", INST)
g.bind("geo", GEO)
g.bind("xsd", XSD)
g.bind("rdfs", RDFS)

print(f"--- 2. PROCESSING ROADS FROM '{gpkg_file}' (LOW MEMORY) ---")

# open  gpkg file with fiona
try:
    with fiona.open(gpkg_file, layer='lines') as layer:
        source_crs = layer.crs_wkt
        if target_crs not in source_crs: # Basic check
             print(f"Warning: Source CRS ({layer.crs}) might not be {target_crs}. Assuming WGS84 for WKT.")

        # total number of features for progress bar
        total_features = len(layer)
        print(f"Found {total_features:,} road segments to process.")

        for feature in tqdm(layer, total=total_features, desc="Generating Triples"):
            properties = feature.get('properties', {})
            geometry_dict = feature.get('geometry')

            other_tags_string = properties.get('other_tags')
            parsed_tags = parse_hstore(other_tags_string)
            all_props = {**properties, **parsed_tags} # parsed tags overwrite originals if needed

            # --- Create URIs ---
            osm_id_str = str(all_props.get('osm_id'))
            if not osm_id_str or osm_id_str == 'None':
                continue

            road_uri = INST[f"road_{osm_id_str}"]
            geom_uri = INST[f"geom_{osm_id_str}"]

            # --- Add Base Type ---
            g.add((road_uri, RDF.type, TRAFFIC.RoadSegment))

            # --- Add Specific Road Type ---
            highway_type = all_props.get('highway')
            if highway_type in highway_mapping:
                g.add((road_uri, RDF.type, highway_mapping[highway_type]))

            # --- Add Label (Name) ---
            road_name = all_props.get('name')
            if road_name:
                g.add((road_uri, RDFS.label, Literal(road_name, lang="nl")))

            # --- Add Data Properties ---
            g.add((road_uri, TRAFFIC.osmId, Literal(osm_id_str)))

            # Max Speed Limit
            maxspeed = all_props.get('maxspeed')
            if maxspeed:
                try:
                    speed_val = int(re.match(r"^\d+", str(maxspeed)).group())
                    g.add((road_uri, TRAFFIC.maxSpeedLimit, Literal(speed_val, datatype=XSD.integer)))
                except (ValueError, AttributeError): pass

            # Surface
            surface = all_props.get('surface')
            if surface:
                g.add((road_uri, TRAFFIC.surface, Literal(surface)))

            # Zone:Traffic
            zone = all_props.get('zone:traffic')
            if zone:
                g.add((road_uri, TRAFFIC.zoneTraffic, Literal(zone)))

            # --- Add Bridge/Tunnel Types ---
            if str(all_props.get('bridge', 'no')).lower() != 'no':
                 g.add((road_uri, RDF.type, TRAFFIC.Bridge))
            if str(all_props.get('tunnel', 'no')).lower() != 'no':
                 g.add((road_uri, RDF.type, TRAFFIC.Tunnel))

            # --- Add Geometry ---
            if geometry_dict:
                try:
                    # convert fiona geometry dict to shapely object
                    shapely_geom = shape(geometry_dict)
                    # convert shapely object to WKT Literal
                    wkt_literal = Literal(wkt_dumps(shapely_geom), datatype=GEO.wktLiteral)
                    # add triples
                    g.add((geom_uri, RDF.type, GEO.Geometry))
                    g.add((geom_uri, GEO.asWKT, wkt_literal))
                    g.add((road_uri, GEO.hasGeometry, geom_uri))
                except Exception as e:
                    print(f"Warning: Could not process geometry for osm_id {osm_id_str}: {e}")


except Exception as e:
    print(f"Error reading GeoPackage file: {e}")
    exit()

print("\n--- 3. SAVING RDF FILE ---")
output_ttl_file.parent.mkdir(parents=True, exist_ok=True)

# serialize the graph to turtle format
try:
    g.serialize(destination=str(output_ttl_file), format="turtle")
    print(f"Successfully saved road network triples to '{output_ttl_file}'")
except Exception as e:
    print(f"Error saving file: {e}")

print("\n--- Script Finished ---")