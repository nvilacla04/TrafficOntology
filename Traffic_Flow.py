import gzip
import xml.etree.ElementTree as ET
from pathlib import Path
import csv
from collections import defaultdict

def process_xml_file(filepath):
    """
    parse trafficspeed.xml.gz and yields data rows.
    try to be memory efficient 

    DATEX II Format: siteMeasurements contains the repeating measurement data
    """
    
    print(f"Processing {filepath.name}...")
    
    try:
        with gzip.open(filepath, 'rb') as f:


            context = ET.iterparse(f, events=('end',))
            
            #track stats
            total_measurements = 0
            measurements_with_coords = 0
            measurements_without_coords = 0
            
            for event, elem in context:
                #the repeating tag in DATEX II trafficspeed files is siteMeasurements
                #tis contains data for one measurement site at one timestamp
                if elem.tag.endswith('siteMeasurements'):
                    
                    try:
                        #extract measurement site reference site ID
                        site_ref_elem = elem.find('.//{*}measurementSiteReference')
                        if site_ref_elem is not None:
                            site_id = site_ref_elem.get('id')
                        else:
                            site_id = None
                        
                        #extract measurement time
                        time_elem = elem.find('.//{*}measurementTimeDefault')
                        timestamp = time_elem.text if time_elem is not None else None
                        
                        #extract measured values (speed, flow, etc.)
                        #there can be multiple measuredValue elements per site measurement
                        measured_values = elem.findall('.//{*}measuredValue')
                        
                        for measured_value in measured_values:
                            #get the measurement type
                            basic_data = measured_value.find('.//{*}basicData')
                            
                            if basic_data is not None:
                                #check speed
                                speed_elem = basic_data.find('.//{*}averageVehicleSpeed')
                                if speed_elem is not None:
                                    speed_value_elem = speed_elem.find('.//{*}speed')
                                    speed = float(speed_value_elem.text) if speed_value_elem is not None else None
                                else:
                                    speed = None
                                
                                #check flow
                                flow_elem = basic_data.find('.//{*}trafficFlow')
                                if flow_elem is not None:
                                    flow_rate_elem = flow_elem.find('.//{*}vehicleFlowRate')
                                    flow_rate = float(flow_rate_elem.text) if flow_rate_elem is not None else None
                                else:
                                    flow_rate = None
                                
                                #only yield if we have site_id and at least one measurement
                                if site_id and (speed is not None or flow_rate is not None):
                                    total_measurements += 1
                                    
                                    yield {
                                        'site_id': site_id,
                                        'timestamp': timestamp,
                                        'speed': speed,
                                        'flow_rate': flow_rate
                                    }
                    
                    except Exception as e:
                        print(f"Error processing element: {e}")
                        continue
                    
                    # free up memory
                    elem.clear()
                
            
            print(f"\n✅ Processing complete!!")
            print(f"   Total measurements extracted: {total_measurements:,}")
    
    except Exception as e:
        print(f"    🥀Error processing file: {e}")
        raise


def extract_traffic_data(input_file, output_dir):
    """
    main extraction function.
    Reads trafficspeed.xml.gz and creates two CSV files:
    - traffic_speed_clean.csv
    - traffic_flow_clean.csv 
    """
    
    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    #output files
    speed_file = output_path / 'traffic_speed_clean.csv'
    flow_file = output_path / 'traffic_flow_clean.csv'
    summary_file = output_path / 'site_summary.csv'
    
    print("-"*70)
    print("EXTRACTING TRAFFIC DATA FROM XML")
    print("-"*70)
    print(f"Input: {input_path}")
    print(f"Output directory: {output_path}")
    
    #CSV writers
    speed_rows = []
    flow_rows = []
    site_stats = defaultdict(lambda: {
        'speed_count': 0,
        'flow_count': 0,
        'speeds': [],
        'flows': []
    })
    
    #process the XML file
    for data in process_xml_file(input_path):
        site_id = data['site_id']
        
        #collect speed data
        if data['speed'] is not None:
            speed_rows.append({
                'site_id': site_id,
                'timestamp': data['timestamp'],
                'speed': data['speed']
            })
            site_stats[site_id]['speed_count'] += 1
            site_stats[site_id]['speeds'].append(data['speed'])
        
        #collect flow data
        if data['flow_rate'] is not None:
            flow_rows.append({
                'site_id': site_id,
                'timestamp': data['timestamp'],
                'flow_rate': data['flow_rate']
            })
            site_stats[site_id]['flow_count'] += 1
            site_stats[site_id]['flows'].append(data['flow_rate'])
    
    #write speed data
    if speed_rows:
        with open(speed_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['site_id', 'timestamp', 'speed'])
            writer.writeheader()
            writer.writerows(speed_rows)
        print(f"\n  Speed data: {len(speed_rows):,} measurements")
        print(f"   Saved to: {speed_file}")
    
    #write flow data
    if flow_rows:
        with open(flow_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['site_id', 'timestamp', 'flow_rate'])
            writer.writeheader()
            writer.writerows(flow_rows)
        print(f"\n  Flow data: {len(flow_rows):,} measurements")
        print(f"   Saved to: {flow_file}")
    
    #write site summary
    summary_rows = []
    for site_id, stats in site_stats.items():
        summary_rows.append({
            'site_id': site_id,
            'speed_measurements': stats['speed_count'],
            'flow_measurements': stats['flow_count'],
            'avg_speed': sum(stats['speeds']) / len(stats['speeds']) if stats['speeds'] else None,
            'avg_flow': sum(stats['flows']) / len(stats['flows']) if stats['flows'] else None,
            'max_speed': max(stats['speeds']) if stats['speeds'] else None,
            'max_flow': max(stats['flows']) if stats['flows'] else None
        })
    
    if summary_rows:
        with open(summary_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'site_id', 'speed_measurements', 'flow_measurements',
                'avg_speed', 'avg_flow', 'max_speed', 'max_flow'
            ])
            writer.writeheader()
            writer.writerows(summary_rows)
        print(f"\n  Site summary: {len(summary_rows):,} unique sites")
        print(f"   Saved to: {summary_file}")
    
    print("\n" + "-"*70)
    print("✅ extraction done)")
    print(f"\nFiles created:")
    print(f"  - {speed_file.name}")
    print(f"  - {flow_file.name}")
    print(f"  - {summary_file.name}")


if __name__ == '__main__':
    #conf
    INPUT_FILE = r'C:\Users\nicol\Documents\TrafficOntology_Project\TrafficOntology\data_raw\other data\trafficspeed.xml.gz'
    OUTPUT_DIR = r'C:\Users\nicol\Documents\TrafficOntology_Project\TrafficOntology\data_processed'
    
    extract_traffic_data(INPUT_FILE, OUTPUT_DIR)