import xml.etree.ElementTree as ET

def generate_infinite_sequence(edge_str, cycles=2):
    edges = edge_str.split()
    full_path = list(edges)
    
    for _ in range(cycles):
        backward = []
        for e in reversed(edges):
            new_e = e[1:] if e.startswith("-") else "-" + e
            backward.append(new_e)
        
        full_path.extend(backward)
        full_path.extend(edges)
        
    return " ".join(full_path)

tree = ET.parse('erlangen.rou.xml')
root = tree.getroot()

for route in root.iter('route'):
    old_edges = route.get('edges')
    route.set('edges', generate_infinite_sequence(old_edges, cycles=2))

tree.write('erlangen_infinite.rou.xml', encoding='UTF-8', xml_declaration=True)
