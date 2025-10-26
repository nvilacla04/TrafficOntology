#!/usr/bin/env python3
"""
Quick Test Script: Extract Coordinates from DATEX II XML

This script tests whether your trafficspeed.xml.gz file contains coordinate information.
Run this before the full notebook to check coordinate availability.
"""

import gzip
import xml.etree.ElementTree as ET

def test_coordinate_extraction(xml_file_path):
    """Test if the XML file contains coordinate data."""
    
    print("=" * 70)
    print("DATEX II Coordinate Extraction Test")
    print("=" * 70)
    
    # Read the XML file
    print(f"\n📂 Loading file: {xml_file_path}")
    try:
        with gzip.open(xml_file_path, 'rt', encoding='utf-8') as f:
            xml_content = f.read()
        print(f"✅ File loaded successfully ({len(xml_content):,} characters)")
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return
    
    # Parse XML
    print("\n🔍 Parsing XML...")
    try:
        root = ET.fromstring(xml_content)
        print("✅ XML parsed successfully")
    except Exception as e:
        print(f"❌ Error parsing XML: {e}")
        return
    
    # Define namespaces
    namespaces = {
        'SOAP': 'http://schemas.xmlsoap.org/soap/envelope/',
        'd2': 'http://datex2.eu/schema/2/2_0',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }
    
    # Look for measurement site records
    print("\n📍 Searching for coordinate data...")
    
    site_records = root.findall('.//d2:measurementSiteRecord', namespaces)
    print(f"   Found {len(site_records)} measurement site records")
    
    if len(site_records) == 0:
        print("\n⚠️  No measurement site records found!")
        print("   This XML file may only contain measurements, not site definitions.")
        print("   You'll need to get coordinates from a separate source.")
        return
    
    # Check for coordinates
    coords_found = 0
    sample_sites = []
    
    for site in site_records[:10]:  # Check first 10 sites
        site_id = site.get('id', 'Unknown')
        
        # Method 1: pointByCoordinates
        point = site.find('.//d2:pointByCoordinates', namespaces)
        if point is not None:
            lat = point.find('.//d2:latitude', namespaces)
            lon = point.find('.//d2:longitude', namespaces)
            if lat is not None and lon is not None:
                coords_found += 1
                sample_sites.append({
                    'id': site_id,
                    'lat': lat.text,
                    'lon': lon.text,
                    'method': 'pointByCoordinates'
                })
                continue
        
        # Method 2: locationForDisplay
        lat = site.find('.//d2:locationForDisplay/d2:latitude', namespaces)
        lon = site.find('.//d2:locationForDisplay/d2:longitude', namespaces)
        if lat is not None and lon is not None:
            coords_found += 1
            sample_sites.append({
                'id': site_id,
                'lat': lat.text,
                'lon': lon.text,
                'method': 'locationForDisplay'
            })
    
    # Report results
    print(f"\n📊 Results:")
    print(f"   Total site records: {len(site_records)}")
    print(f"   Sites with coordinates (in first 10): {coords_found}")
    
    if coords_found > 0:
        print(f"\n✅ COORDINATE DATA FOUND!")
        print(f"   Your XML file contains coordinate information.")
        print(f"\n   Sample sites:")
        for site in sample_sites[:3]:
            print(f"   - {site['id']}")
            print(f"     Lat: {site['lat']}, Lon: {site['lon']}")
            print(f"     Method: {site['method']}")
        
        # Validate coordinates are in Netherlands range
        try:
            for site in sample_sites:
                lat_val = float(site['lat'])
                lon_val = float(site['lon'])
                if 50.5 <= lat_val <= 53.7 and 3.0 <= lon_val <= 7.5:
                    print(f"\n✅ Coordinates look valid for Netherlands region")
                    break
                else:
                    print(f"\n⚠️  Warning: Coordinates outside expected Netherlands range")
                    print(f"   Expected: Lat 50.5-53.7, Lon 3.0-7.5")
                    print(f"   Found: Lat {lat_val}, Lon {lon_val}")
        except:
            pass
        
        print(f"\n📝 Next steps:")
        print(f"   1. Run the updated Jupyter notebook")
        print(f"   2. All coordinate columns will be automatically populated")
        print(f"   3. Use the Geographic RDF Guide for RDF conversion")
        
    else:
        print(f"\n⚠️  NO COORDINATE DATA FOUND")
        print(f"   Your XML file does not contain coordinate information.")
        print(f"\n   Alternative solutions:")
        print(f"   1. Get NDW sensor location dataset separately")
        print(f"   2. Use site_id to match with external geographic database")
        print(f"   3. Contact data provider for location information")
        print(f"   4. Use OpenStreetMap to manually locate major sensors")
        print(f"\n   The notebook will still work but coordinate columns will be empty.")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Update this path to match your file location
    xml_file_path = r'C:\Users\nicol\Documents\TrafficOntology_Project\TrafficOntology\data_raw\other data\trafficspeed.xml.gz'
    
    test_coordinate_extraction(xml_file_path)
