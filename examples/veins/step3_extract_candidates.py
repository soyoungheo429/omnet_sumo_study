import xml.etree.ElementTree as ET
import math
from pyproj import Transformer

def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def generate_rsu_configs(net_file, min_dist=150):
    OFFSET_X = 644465.09
    OFFSET_Y = 5491786.25
    
    proj_str = "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"
    transformer = Transformer.from_crs(proj_str, "epsg:4326", always_xy=True)
    
    try:
        tree = ET.parse(net_file)
        root = tree.getroot()
    except FileNotFoundError:
        print(f"Error: {net_file} 파일을 찾을 수 없습니다.")
        return

    junction_candidates = []

    for junction in root.findall('junction'):
        j_id = junction.get('id')
        j_type = junction.get('type')
        
        if j_type in ['priority', 'traffic_light', 'right_before_left']:
            x = float(junction.get('x'))
            y = float(junction.get('y'))
            
            inc_lanes = junction.get('incLanes', '').split()
            degree = len(inc_lanes)
            
            if degree >= 3:
                junction_candidates.append({
                    'id': j_id,
                    'pos': (x, y),
                    'degree': degree
                })
    
    for cand in junction_candidates:
        density = sum(1 for other in junction_candidates 
                     if cand != other and calculate_distance(cand['pos'], other['pos']) < min_dist)
        cand['density'] = density

    junction_candidates.sort(key=lambda x: (x['degree'], x['density']), reverse=True)

    final_rsu_list = []
    for current in junction_candidates:
        if not any(calculate_distance(current['pos'], chosen['pos']) < min_dist for chosen in final_rsu_list):
            final_rsu_list.append(current)

    print(f"\n# 추출 결과: {len(final_rsu_list)}개의 최적 지점이 선정되었습니다.\n")
    print(f"{'No':<4} | {'ID':<25} | {'Deg':<4} | {'Dens':<4} | {'Latitude':<12} | {'Longitude':<12}")
    print("-" * 80)

    for i, rsu in enumerate(final_rsu_list):
        lon, lat = transformer.transform(rsu['pos'][0], rsu['pos'][1])
        print(f"{i:<4} | {rsu['id']:<25} | {rsu['degree']:<4} | {rsu['density']:<4} | {lat:<12.6f} | {lon:<12.6f}")

    print("\n[Config]")
    for i, rsu in enumerate(final_rsu_list):
        lon, lat = transformer.transform(rsu['pos'][0], rsu['pos'][1])
        local_x = rsu['pos'][0] - OFFSET_X + 50
        local_y = rsu['pos'][1] - OFFSET_Y - 300
        
        print(f"# RSU_{i} | ID: {rsu['id']} | 위치: {lat:.6f}, {lon:.6f}")
        print(f"*.rsu[{i}].mobility.x = {local_x:.2f}") 
        print(f"*.rsu[{i}].mobility.y = {local_y:.2f}")
        print(f"*.rsu[{i}].mobility.z = 3")
generate_rsu_configs('erlangen.net.xml', min_dist=150)
