import xml.etree.ElementTree as ET

tree = ET.parse('erlangen.net.xml')
root = tree.getroot()

all_junctions = root.findall('junction')

real_junctions = [j for j in all_junctions if not j.get('id').startswith(':')]
internal_junctions = [j for j in all_junctions if j.get('id').startswith(':')]

print(f"전체 태그 개수: {len(all_junctions)}")
print(f"실제 교차로 개수: {len(real_junctions)}")
print(f"내부 연결점 개수: {len(internal_junctions)}")

types = {}
for j in real_junctions:
    j_type = j.get('type')
    types[j_type] = types.get(j_type, 0) + 1

print("\n--- 타입별 정션 개수 ---")
for t, count in types.items():
    print(f"{t}: {count}")
