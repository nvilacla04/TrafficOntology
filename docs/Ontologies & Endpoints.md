# Ontologies


## OTN (ontology for transportation network)
https://enterpriseintegrationlab.github.io/icity/OTN/doc/index-en.html


- formalises and extends Geographic Data Files (GDF)
- provides formal OWL representation for transportation systems
- provides domain specific classes for transportation networks
- kinda old 

## GeoSPARQL
https://www.ogc.org/standards/geosparql/

- supports representing and querying geospatial data on semantic web 
- offers core classes 
- topological vacabularies and geometry serialisation
- allows complex spacial queries which should be really cool

# External Datasets

## Rijkswaterstraat Accident Dataset

- Rijkswaterstaat publishes a Verkeersongevallen Nederland dataset that compiles all road‑traffic accidents from the national BRON register.

- It is derived from the BRON database and contains accidents linked to the national digital road network (NWB).

- The dataset is packaged as several geo‑files. The 2022‑2024 compilation includes four year‑specific files (verkeersongevallen_2022, verkeersongevallen_2023, verkeersongevallen_2024) plus a combined file (verkeersongevallen_2022_2024) and a road‑section geography file.

- Problem maybe: data goes back to 2003 but its in a different format 

| Field                        | Description                                                    |
| ---------------------------- | -------------------------------------------------------------- |
| **VKL_NUMMER**               | Unique accident number                                         |
| **JAAR_VKL**                 | Accident year                                                  |
| **AP3_CODE**                 | Outcome class: fatal (1), injury (2), material damage only (3) |
| **ANTL_PTJ**                 | Number of involved parties/vehicles                            |
| **AOL_ID**                   | Accident type category (single vehicle, flank collision, etc.) |
| **BEBKOM**                   | Indicator for built‑up area (1 = inside, 0 = outside)          |
| **MAXSNELHD**                | Posted speed limit (km/h)                                      |
| **WSE_ID**                   | Road situation (straight road, bend, etc.)                     |
| **WVL_ID / WVG_ID / WDK_ID** | Road lighting, surface and condition codes                     |
| **LGD_ID & ZAD_ID**          | Light and visibility conditions                                |
| **WGD_CODE_1 / WGD_CODE_2**  | Weather condition codes                                        |
| **BZD_ID_VM1..VM3**          | Special traffic measures (variable message signs, etc.)        |


https://data.overheid.nl/en/dataset/a516ffaf-fbcc-44bc-88cb-fca799c5cd29

Alright Big Bro — here’s the full walkthrough on how to **actually use** the Rijkswaterstaat and NDW datasets in practice, from download to working inside Python or GIS. I’ll keep it practical and ordered, so you can go from zero to plotting or analyzing.

---

## 🧭 1. Rijkswaterstaat Accident Dataset (BRON / Verkeersongevallen)

### Step 1. Go to the source

1. Visit:
   👉 [https://data.overheid.nl/en/dataset/9841-verkeersongevallen---bestand-geregistreerde-ongevallen-nederland](https://data.overheid.nl/en/dataset/9841-verkeersongevallen---bestand-geregistreerde-ongevallen-nederland)
2. Scroll to **Downloads / Data bestanden**.
3. Choose the **most recent “Ongevallen” (accidents)** file. It’s usually offered as:

   * `.zip` → contains `.shp` (Shapefile) or `.gpkg` (GeoPackage)
   * Sometimes `.csv` or `.xml`

Example: `Verkeersongevallen_Nederland_2023.zip`

---

### Step 2. Inspect the contents

After unzipping, you’ll see files like:

```
Verkeersongevallen_Nederland_2023/
  ├── Ongevallen.shp
  ├── Ongevallen.dbf
  ├── Ongevallen.prj
  ├── Wegvakken.shp
  ├── Wegvakken.dbf
```

* `Ongevallen.shp` → individual accidents
* `Wegvakken.shp` → road segment geography
* Attributes: `JAAR`, `MAAND`, `DAG`, `AANTAL_DODEN`, `WEGTYPE`, `WEERSOMST`, etc.

---

### Step 3. Load into Python or QGIS

**Option A: Python (GeoPandas)**

```python
import geopandas as gpd

# Load shapefile or geopackage
gdf = gpd.read_file("Verkeersongevallen_Nederland_2023/Ongevallen.shp")

# Check first few columns
print(gdf.head())

# Plot accidents
gdf.plot(figsize=(8,8), markersize=1)
```

You can filter:

```python
amsterdam = gdf[gdf['GEMEENTE'] == 'Amsterdam']
severe = gdf[gdf['AANTAL_DODEN'] > 0]
```

**Option B: QGIS**

1. Open QGIS → “Data Source Manager” → “Vector”.
2. Load `Ongevallen.shp` or `Ongevallen.gpkg`.
3. Add a basemap (OpenStreetMap).
4. Style accidents by severity or year.

---

### Step 4. What you can do with it

* Map all fatal accidents (`AANTAL_DODEN > 0`)
* Identify hotspots using **heatmap** plugin or spatial clustering
* Join with NDW traffic flow data to see if high flow correlates with more crashes
* Export to CSV for machine learning models

---

## 🚦 2. NDW (Nationale Databank Wegverkeersgegevens)

### Step 1. Go to open portal

👉 [https://opendata.ndw.nu/](https://opendata.ndw.nu/)

You’ll see datasets like:

```
measurement.xml.gz         (traffic flow, speeds)
incidents.xml.gz           (accidents, disruptions)
roadworks.xml.gz           (planned works)
drip.xml.gz                (dynamic signs)
```

They update every minute or every 5 minutes.

---

### Step 2. Download and decompress

1. Click `measurement.xml.gz` → save locally.
2. Unzip with `gunzip measurement.xml.gz` or a tool like 7-Zip.
3. You’ll get `measurement.xml`.

Each XML file is a **DATEX II** structure (a European standard for traffic data).

---

### Step 3. Parse XML in Python

```python
import xml.etree.ElementTree as ET

tree = ET.parse('measurement.xml')
root = tree.getroot()

for site in root.findall('.//measurementSiteRecord'):
    site_id = site.find('measurementSiteReference').attrib['id']
    speed = site.find('.//averageVehicleSpeed/value')
    flow = site.find('.//vehicleFlow/value')
    print(site_id, speed.text if speed is not None else None, flow.text if flow is not None else None)
```

This gives you **flow (vehicles/hour)** and **speed (km/h)** per measurement station.

---

### Step 4. Historical or live data

* **Live data** → directly from `https://opendata.ndw.nu/measurement.xml.gz`
* **Historical (Dexter)** → use `https://historical.ndw.nu/`
  There you can pick date ranges and download archived `.csv` or `.xml` files for a given period.

---

### Step 5. Typical joins with accident data

You can join the NDW station nearest to each accident to get context variables:

| Accident_ID | Date       | Flow | Speed | RoadWorks | IncidentNearby |
| ----------- | ---------- | ---- | ----- | --------- | -------------- |
| A001        | 2023-07-14 | 3400 | 95    | 0         | 1              |

Use `geopandas.sjoin_nearest()` for spatial joins or match by `road_id`.

---

## 🧩 3. Why use both together

| Dataset                       | Type                                    | Purpose                                                                |
| ----------------------------- | --------------------------------------- | ---------------------------------------------------------------------- |
| **Rijkswaterstaat accidents** | Historical accidents (point data)       | Identify where, when, and how severe crashes occur                     |
| **NDW traffic flow**          | Real-time / historical speeds and flows | Understand congestion, volume, and speed variation near accident sites |
| **NDW incidents & roadworks** | Real-time disruptions                   | Add context (e.g., roadworks causing traffic density spikes)           |
| **NDW signs (DRIP/matrix)**   | Dynamic signage                         | Correlate driver information with safety outcomes                      |

Together they form the foundation for a **semantic / RDF knowledge graph** or an **AI prediction model** on accident risk.

---

## ⚙️ 4. Recommended folder structure

```
TrafficData/
├── Rijkswaterstaat/
│   ├── 2023_Ongevallen/
│   ├── 2024_Ongevallen/
├── NDW/
│   ├── measurement_2024-10-22.xml
│   ├── incidents_2024-10-22.xml
│   ├── roadworks_2024-10-22.xml
```

Then parse and store them into CSV or SQLite for easy querying.

# OpenStreetMap API endpoint 
https://overpass-turbo.eu/

All for in Amsterdam

Major roads
---

[out:json][timeout:90];
{{geocodeArea:Amsterdam}}->.a;
way(area.a)["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"];
out geom;

Streets
---
[out:json][timeout:90];
{{geocodeArea:Amsterdam}}->.a;
way(area.a)["highway"~"^(unclassified|residential|living_street|service)$"];
out geom;

Non-moterized and misc.
---
[out:json][timeout:90];
{{geocodeArea:Amsterdam}}->.a;
way(area.a)["highway"~"^(pedestrian|track|path|footway|cycleway|steps|bridleway|bus_guideway)$"];
out geom;




# wikidata 
https://query.wikidata.org/
Get every city in the netherlands 
---
```
SELECT ?city ?cityLabel WHERE {
  ?city wdt:P31/wdt:P279* wd:Q515 .
  ?city wdt:P17 wd:Q55 .
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en" .
  }
}
```

