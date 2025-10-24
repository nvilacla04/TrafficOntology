"""
Super cooked but the signage file is too big to push 
to git so imma just split it into a couple smaller ones

"""

import gzip
import json
from pathlib import Path
from typing import List, Dict, Any


def load_traffic_signs() -> Path:
    """
    Ts will load sings GeoJSON file. Dont really know what tfa GeoJSON is but we will get that sorted out. 
    Assumes its already at data_raw/trafficsigns_wgs84.geojson if u need it go to:
    http://opendata.ndw.nu/verkeersborden_actueel_beeld_wgs84.geojson.gz
    ended up ging with wgs84 bc its a more used format than rd which is only used in the netherlands apparently?
    """
    json_file = Path('data_raw/trafficsigns_wgs84.geojson')
    
    if not json_file.exists():
        raise FileNotFoundError(
            f"File not found: {json_file}\n"
            f"Please ensure trafficsigns_wgs84.geojson is in the data_raw/ directory ☝️🤓"
        )
    
    return json_file





def split_geojson_by_sign_type(
    input_file: Path,
    output_dir: str = 'data_processed/traffic_signs_by_type') -> List[Path]:
    """split GeoJSON by traffic sign type (RVV code) 🤷"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading {input_file.name}...⌛⌛⌛")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    features = data.get('features', [])



    # Group by RVV code
    signs_by_type: Dict[str, List[Dict[Any, Any]]] = {}
    
    for feature in features:
        rvv_code = feature.get('properties', {}).get('rvvCode', 'unknown')
        if rvv_code not in signs_by_type:
            signs_by_type[rvv_code] = []
        signs_by_type[rvv_code].append(feature)
    
    print(f"Found {len(signs_by_type)} sign types!")
    
    output_files = []
    
    for rvv_code, sign_features in sorted(signs_by_type.items()):
        chunk_data = {
            'type': 'FeatureCollection',
            'name': f'traffic_signs_{rvv_code}',
            'crs': data.get('crs'),
            'features': sign_features
        }
        
        safe_code = rvv_code.replace('/', '_').replace(' ', '_')
        output_file = output_path / f'traffic_signs_{safe_code}.geojson'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(chunk_data, f, ensure_ascii=False)
        
        file_size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"  {rvv_code}: {len(sign_features):,} signs ({file_size_mb:.1f} MB)")
        output_files.append(output_file)
    
    return output_files


def create_metadata_file(split_files: List[Path], output_dir: str):
    """create a metadata file listing all chunks"""
    metadata = {
        'total_chunks': len(split_files),
        'chunks': [
            {
                'filename': f.name,
                'path': str(f),
                #if any of these is over 100mb i kms 
                'size_mb': round(f.stat().st_size / (1024 * 1024), 2)
            }
            for f in split_files
        ]
    }
    
    metadata_file = Path(output_dir) / 'metadata.json'
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Metadata: {metadata_file}")


if __name__ == '__main__':
    print("NDW Traffic Signs Splitter")
    print("=" * 60)
    
    #load the traffic signs file
    geojson_file = load_traffic_signs()
    
    #split by sign type
    print("Splitting by RVV code...")
    split_files = split_geojson_by_sign_type(geojson_file)
    create_metadata_file(split_files, 'data_processed/traffic_signs_by_type')
    
    print(f"\n✅ Done WOOOHOOO! {len(split_files)} files in data_processed/traffic_signs_by_type/")
    print("=" * 60)

#Did not expect 175 sign types bruh but thats ok as none of them are even close to 100mb 
