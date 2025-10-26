import gzip
import xml.etree.ElementTree as ET
import pandas as pd
from pathlib import Path

def process_xml_file(filepath):
    """
    Parses a single gzipped XML file and yields data rows.
    This is a memory-efficient generator.
    """
    print(f"Processing {filepath.name}...")
    try:
        # Open the gzipped file in binary-read 'rb' mode
        with gzip.open(filepath, 'rb') as f:
            # Use iterparse for streaming. 'end' event is when
            # the parser finishes a closing tag.
            
            # *** YOU MUST EDIT 'ns:measurement' ***
            # Replace 'ns:measurement' with the *actual* repeating tag 
            # you found in Step 1. You may also need to handle
            # XML namespaces if they exist.
            
            # This is a common way to handle namespaces:
            # {http://your.namespace.com}measurement
            
            context = ET.iterparse(f, events=('end',))
            
            for event, elem in context:
                
                # *** EDIT THIS BLOCK ***
                # Change 'measurement' to your repeating tag
                if elem.tag.endswith('measurement'): 
                    
                    # Extract your data. These are guesses.
                    # You MUST change them to match your XML structure.
                    try:
                        sensor_id = elem.find('sensor_id').text
                        timestamp = elem.find('timestamp').text
                        flow = elem.find('flow').text
                        speed = elem.find('speed').text
                        
                        # Yield the data as a dictionary
                        yield {
                            "sensor_id": sensor_id,
                            "timestamp": timestamp,
                            "flow_rate": flow,
                            "avg_speed": speed
                        }
                    
                    except AttributeError:
                        # Happens if a tag is missing, just skip this record
                        pass

                    # Clear the element from memory to keep usage low
                    elem.clear()

    except Exception as e:
        print(f"Error processing {filepath.name}: {e}")

# --- Main Execution ---
# 1. Define your paths
xml_directory = Path(r"C:\path\to\your\xml_gz_files")
output_csv = Path(r"C:\path\to\output\traffic_flow_all.csv")

all_data = [] # This will hold all data from all files

# 2. Find all .xml.gz files
xml_files = list(xml_directory.glob("*.xml.gz"))
print(f"Found {len(xml_files)} files to process.")

# 3. Loop and process
for file in xml_files:
    # Use the generator to get data and append to our list
    all_data.extend(process_xml_file(file))

# 4. Convert to DataFrame and Save
if all_data:
    print("Converting all data to DataFrame...")
    df = pd.DataFrame(all_data)
    
    # 5. **CRITICAL CLEANUP**:
    # Your 'sensor_id' from the XML *must* be cleaned to match
    # the 'id' or 'naam' column in 'meetvakken_all_columns.csv'.
    # This is just an example, you will need to adapt it.
    # df['sensor_id_clean'] = df['sensor_id'].str.replace('RWS01_', '')
    
    print(f"Processed {len(df)} total measurements.")
    print(df.head())
    
    df.to_csv(output_csv, index=False)
    print(f"Successfully saved all traffic flow data to {output_csv}")
else:
    print("No data was processed.")