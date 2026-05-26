import math
import folium

rsu_results = [
    ("cluster_15159499_18038479_21113262_347787163_8851291", 49.576082, 11.015880, 8, 7),
    ("cluster_12247700_12529558", 49.577650, 11.004480, 6, 3),
    ("cluster_347349857_347349858", 49.576618, 11.001708, 4, 8),
    ("26841354", 49.578178, 11.023730, 4, 7),
    ("17574061", 49.579060, 11.020083, 4, 3),
    ("348243041", 49.577885, 11.016468, 4, 3),
    ("16933971", 49.581182, 11.010784, 4, 2),
    ("17573721", 49.581003, 11.008412, 4, 2),
    ("19755457", 49.577864, 11.007987, 4, 2),
    ("12247702", 49.580866, 11.005721, 4, 1),
    ("14319161", 49.572468, 11.000520, 4, 1),
    ("19769114", 49.570403, 11.000071, 4, 1),
    ("cluster_314448309_824235741", 49.574876, 11.009275, 4, 1),
    ("21969082", 49.577636, 11.010613, 4, 0),
    ("89119479", 49.574731, 11.024936, 3, 9),
    ("17574090", 49.579398, 11.025340, 3, 7),
    ("26841356", 49.576853, 11.022103, 3, 7),
    ("21970003", 49.573616, 11.016800, 3, 6),
    ("17574097", 49.580694, 11.024158, 3, 5),
    ("26841336", 49.578340, 11.027198, 3, 5),
    ("17574059", 49.580844, 11.020293, 3, 4),
    ("347349917", 49.577991, 11.000563, 3, 4),
    ("1154372516", 49.573137, 11.030161, 3, 2),
    ("13493753", 49.578952, 11.005236, 3, 2),
    ("15420062", 49.581863, 11.012807, 3, 2),
    ("19755477", 49.579812, 11.009866, 3, 2),
    ("21262677", 49.582697, 11.009517, 3, 2),
    ("26841358", 49.575516, 11.027625, 3, 2),
    ("14319163", 49.575059, 11.002928, 3, 1),
    ("12452103", 49.568920, 11.031449, 3, 0),
    ("1391319738", 49.576396, 11.012981, 3, 0),
    ("16933976", 49.577808, 11.012750, 3, 0),
    ("19755421", 49.581721, 11.017490, 3, 0),
    ("21970024", 49.572838, 11.019429, 3, 0),
    ("252726522", 49.569565, 11.027230, 3, 0),
    ("26841333", 49.581650, 11.033591, 3, 0),
    ("314448358", 49.573159, 11.007889, 3, 0),
    ("354910587", 49.569281, 11.003777, 3, 0),
    ("39537846", 49.571024, 11.026267, 3, 0),
    ("cluster_1291385696_21971288", 49.574719, 11.031625, 3, 0)
]

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

sorted_candidates = sorted(rsu_results, key=lambda x: (x[3], x[4]), reverse=True)

MIN_DISTANCE = 150

for candidate in sorted_candidates:
    cand_id, cand_lat, cand_lon, cand_deg, cand_dens = candidate
    
    is_too_close = False
    for selected in filtered_rsus:
        sel_id, sel_lat, sel_lon, sel_deg, sel_dens = selected
        dist = calculate_distance(cand_lat, cand_lon, sel_lat, sel_lon)
        
        if dist < MIN_DISTANCE:
            is_too_close = True
            break
            
    if not is_too_close:
        filtered_rsus.append(candidate)

print("\n" + "="*50)
print("시뮬레이션용 솎아낸 RSU 리스트")
print("="*50)
print("rsu_locations = [")
for i, cand in enumerate(filtered_rsus):
    comma = "," if i < len(filtered_rsus) - 1 else ""
    print(f'    {{"id": "{cand[0]}", "lat": {cand[1]:.6f}, "lon": {cand[2]:.6f}}}{comma}')
print("]\n")
print(f"초기 {len(rsu_results)}개 중 {len(filtered_rsus)}개의 핵심 교차로가 선별되었습니다.\n")

m = folium.Map(location=[49.576, 11.015], zoom_start=14, tiles='CartoDB Positron')

for i, (name, lat, lon, deg, dens) in enumerate(filtered_rsus):
    folium.Marker(
        location=[lat, lon],
        popup=f"Rank {i+1}<br>ID: {name}<br>Deg: {deg}, Dens: {dens}",
        icon=folium.Icon(color="green" if i < 3 else "blue", icon="ok-sign")
    ).add_to(m)
    
    folium.Circle(
        location=[lat, lon],
        radius=150,
        color="royalblue",
        weight=2,
        fill=True,
        fill_opacity=0.2
    ).add_to(m)

m.save("erlangen_filtered_rsu_map2.html")
print("깔끔하게 정리된 지도가 'erlangen_filtered_rsu_map.html'로 저장되었습니다!")
