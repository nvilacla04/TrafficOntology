# Transportation Knowledge Graph: Ontologies and Endpoints

## Ontologies

### OTN (Ontology for Transportation Networks)

- **URL:** <https://enterpriseintegrationlab.github.io/icity/OTN/doc/index-en.html>
- **Description:**
  - Formalises and extends **GDF (Geographic Data Files)**, which is a standard for transportation network data.
  - Provides a formal **OWL representation** for transportation systems.
  - Defines **domain-specific classes** for transportation networks such as `Route`, `Junction`, `Link`, and `NetworkElement`.
  - Slightly older ontology, but still provides a strong conceptual basis for modelling structured road data.

- **Why use it:**
  OTN helps model the physical and logical structure of roads, intersections, and connections, which can be reused and aligned with other semantic data sources such as OpenStreetMap, NDW, and Rijkswaterstaat data.

---

### GeoSPARQL

- **URL:** <https://www.ogc.org/standards/geosparql/>
- **Description:**
  - Designed by the **OGC (Open Geospatial Consortium)** to represent and query **geospatial data** on the Semantic Web.
  - Provides **core spatial classes** (`Feature`, `Geometry`) and **topological vocabularies** (`sfWithin`, `sfTouches`, `sfIntersects`, etc.).
  - Supports multiple **geometry serialisations**, including **WKT (Well-Known Text)** and **GML (Geography Markup Language)**.
  - Enables **complex spatial queries** directly in SPARQL.

- **Why use it:**
  GeoSPARQL is the key for performing spatial reasoning — you can ask questions such as *“Which accidents occurred within 100 m of a motorway?”* or *“Which traffic sensors are located along the A10?”*.

---

## External Datasets

### Rijkswaterstaat Accident Dataset

- **URL:** <https://data.overheid.nl/en/dataset/a516ffaf-fbcc-44bc-88cb-fca799c5cd29>
- **Summary:**
  - Rijkswaterstaat publishes **Verkeersongevallen Nederland** (*Traffic Accidents Netherlands*), built from the **BRON** (Nationaal Bestand Register Ongevallen Nederland – National Accident Register).
  - Linked to the **NWB** (Nationaal Wegenbestand – National Road Network).
  - Data available from **2003 – 2024** (older years use a legacy format).
  - Newer data (2022–2024) provided as `.zip` archives containing:
    - `.shp` (Shapefile)
    - `.gpkg` (GeoPackage)
    - `.csv` or `.xml` (occasionally)

| Field | Meaning (English in parentheses) |
|-------|----------------------------------|
| **VKL_NUMMER** | Unique accident number |
| **JAAR_VKL** | Year of accident |
| **AP3_CODE** | Outcome class — 1 = fatal, 2 = injury, 3 = material damage only |
| **ANTL_PTJ** | Number of involved parties / vehicles |
| **AOL_ID** | Accident type (single vehicle, flank collision, etc.) |
| **BEBKOM** | Built-up-area indicator (1 = inside urban, 0 = outside) |
| **MAXSNELHD** | Posted speed limit (km/h) |
| **WSE_ID** | Road situation (straight road, bend, etc.) |
| **WVL_ID / WVG_ID / WDK_ID** | Lighting / surface / condition codes |
| **LGD_ID & ZAD_ID** | Light and visibility conditions |
| **WGD_CODE_1 / WGD_CODE_2** | Weather condition codes |
| **BZD_ID_VM1..VM3** | Special traffic measures (variable signs, etc.) |

- **Why use it:**
  It’s the authoritative record of Dutch road accidents, ideal for spatial or temporal analysis and machine-learning models on accident risk.

---

### NDW – Nationale Databank Wegverkeersgegevens (National Road Traffic Database)

- **Portal:** <https://opendata.ndw.nu/>
- **Docs:** <https://docs.ndw.nu/>

- **Summary:**
  NDW offers **real-time and historical traffic data** from nationwide road sensors.  
  Files are updated every minute and use the **DATEX II** standard (the EU format for traffic information).

| File | Content | Purpose |
|------|----------|----------|
| `measurement.xml.gz` | Traffic flow (vehicles/hour), speed (km/h), travel time | Analyse congestion and flow |
| `incidents.xml.gz` | Accidents, disruptions | Add incident context |
| `roadworks.xml.gz` | Roadworks (planned and active) | Correlate maintenance with traffic effects |
| `drip.xml.gz` | DRIP = *Dynamische Route Informatiepanelen* (Dynamic Route Info Panels) | Track driver information signage |
| `srti.xml.gz` | Safety-related traffic information | Include warnings (e.g. slippery road) |

- **How to use:**
  1. Download `.gz` file from NDW portal.  
  2. Decompress to `.xml`.  
  3. Parse in Python:

```python
import xml.etree.ElementTree as ET
tree = ET.parse('measurement.xml')
root = tree.getroot()
for site in root.findall('.//measurementSiteRecord'):
    site_id = site.find('measurementSiteReference').attrib['id']
    speed = site.find('.//averageVehicleSpeed/value')
    flow = site.find('.//vehicleFlow/value')
    print(site_id, speed.text if speed is not None else None, flow.text if flow is not None else None)

Endpoints
Wikidata SPARQL Endpoint

URL: https://query.wikidata.org/

Endpoint: https://query.wikidata.org/bigdata/namespace/wdq/sparql

Example – Cities in the Netherlands

```
SELECT ?city ?cityLabel WHERE {
  ?city wdt:P31/wdt:P279* wd:Q515 .
  ?city wdt:P17 wd:Q55 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
```

Purpose: retrieve reference data such as city names, coordinates, and provinces for linking to accident or traffic datasets.


OpenStreetMap Overpass API

URL: https://overpass-turbo.eu/

Endpoint: https://overpass-api.de/api/interpreter

Example queries for Amsterdam

Major roads

```
[out:json][timeout:90];
{{geocodeArea:Amsterdam}}->.a;
way(area.a)["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"];
out geom;
```

Residential streets

```
[out:json][timeout:90];
{{geocodeArea:Amsterdam}}->.a;
way(area.a)["highway"~"^(unclassified|residential|living_street|service)$"];
out geom;
```

Non-motorized and miscellaneous

```
[out:json][timeout:90];
{{geocodeArea:Amsterdam}}->.a;
way(area.a)["highway"~"^(pedestrian|track|path|footway|cycleway|steps|bridleway|bus_guideway)$"];
out geom;
```
