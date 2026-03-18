import xml.etree.ElementTree as ET

def make_net_bidirectional(input_file, output_file):
    tree = ET.parse(input_file)
    root = tree.getroot()

    existing_edges = {edge.get('id') for edge in root.findall('edge')}
    
    for edge in root.findall('edge'):
        edge_id = edge.get('id')
        
        if edge_id.startswith(':') or edge_id.startswith('-') or ("-" + edge_id in existing_edges):
            continue
            
        reverse_id = "-" + edge_id
        
        new_edge = ET.Element('edge', {
            'id': reverse_id,
            'from': edge.get('to'),
            'to': edge.get('from'),
            'priority': edge.get('priority'),
            'type': edge.get('type')
        })
        
        for lane in edge.findall('lane'):
            lane_attr = lane.attrib.copy()
            lane_attr['id'] = reverse_id + "_" + lane_attr['id'].split('_')[-1]
            shape_coords = lane_attr['shape'].split()
            lane_attr['shape'] = " ".join(reversed(shape_coords))
            
            ET.SubElement(new_edge, 'lane', lane_attr)
            
        root.append(new_edge)

    tree.write(output_file, encoding='UTF-8', xml_declaration=True)

make_net_bidirectional('erlangen.net.xml', 'erlangen_bi.net.xml')
