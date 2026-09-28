import xml.etree.ElementTree as ET
import math

def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def generate_rsu_configs(net_file, min_dist=150):
    try:
        tree = ET.parse(net_file)
        root = tree.getroot()
    except FileNotFoundError:
        print(f"Error: {net_file} not found.")
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
            
            if degree >= 2:
                junction_candidates.append({
                    'id': j_id,
                    'pos': (x, y),
                    'degree': degree
                })

    junction_candidates.sort(key=lambda x: x['degree'], reverse=True)

    final_rsu_list = []
    for current in junction_candidates:
        is_too_close = False
        for chosen in final_rsu_list:
            if calculate_distance(current['pos'], chosen['pos']) < min_dist:
                is_too_close = True
                break
        
        if not is_too_close:
            final_rsu_list.append(current)

    print(f"# Results: {len(final_rsu_list)} optimized locations selected.")
    
    for i, rsu in enumerate(final_rsu_list):
        print(f"[Config RSU_Location_{i}]")
        print(f"*.rsu.mobility.x = {rsu['pos'][0]:.2f}")
        print(f"*.rsu.mobility.y = {rsu['pos'][1]:.2f}")
        print(f"*.rsu.mobility.z = 3")
        print(f"# Junction ID: {rsu['id']}, Degree: {rsu['degree']}\n")

generate_rsu_configs('erlangen.net.xml', min_dist=150)
