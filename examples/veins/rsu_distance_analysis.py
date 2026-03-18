import math

rsu_results = [
    ("RSU_0", 49.576082, 11.015880), ("RSU_1", 49.577650, 11.004480),
    ("RSU_2", 49.576618, 11.001708), ("RSU_3", 49.578178, 11.023730),
    ("RSU_4", 49.579060, 11.020083), ("RSU_5", 49.577885, 11.016468),
    ("RSU_6", 49.581182, 11.010784), ("RSU_7", 49.581003, 11.008412),
    ("RSU_8", 49.577864, 11.007987), ("RSU_9", 49.580866, 11.005721),
    ("RSU_10", 49.572468, 11.000520), ("RSU_11", 49.570403, 11.000071),
    ("RSU_12", 49.574876, 11.009275), ("RSU_13", 49.577636, 11.010613),
    ("RSU_14", 49.574731, 11.024936), ("RSU_15", 49.579398, 11.025340),
    ("RSU_16", 49.576853, 11.022103), ("RSU_17", 49.573616, 11.016800),
    ("RSU_18", 49.580694, 11.024158), ("RSU_19", 49.578340, 11.027198),
    ("RSU_20", 49.580844, 11.020293), ("RSU_21", 49.577991, 11.000563),
    ("RSU_22", 49.573137, 11.030161), ("RSU_23", 49.578952, 11.005236),
    ("RSU_24", 49.581863, 11.012807), ("RSU_25", 49.579812, 11.009866),
    ("RSU_26", 49.582697, 11.009517), ("RSU_27", 49.575516, 11.027625),
    ("RSU_28", 49.575059, 11.002928), ("RSU_29", 49.568920, 11.031449),
    ("RSU_30", 49.576396, 11.012981), ("RSU_31", 49.577808, 11.012750),
    ("RSU_32", 49.581721, 11.017490), ("RSU_33", 49.572838, 11.019429),
    ("RSU_34", 49.569565, 11.027230), ("RSU_35", 49.581650, 11.033591),
    ("RSU_36", 49.573159, 11.007889), ("RSU_37", 49.569281, 11.003777),
    ("RSU_38", 49.571024, 11.026267), ("RSU_39", 49.574719, 11.031625)
]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

distances = []
print(f"{'RSU No':<10} | {'Nearest Neighbor':<18} | {'Distance (m)':<12}")
print("-" * 45)

for i in range(len(rsu_results)):
    min_d = float('inf')
    nearest_idx = -1
    for j in range(len(rsu_results)):
        if i == j: continue
        d = haversine(rsu_results[i][1], rsu_results[i][2], rsu_results[j][1], rsu_results[j][2])
        if d < min_d:
            min_d = d
            nearest_idx = j
    
    distances.append(min_d)
    print(f"RSU_{i:<6} | RSU_{nearest_idx:<13} | {min_d:>10.2f}m")

avg_dist = sum(distances) / len(distances)
print("-" * 45)
print(f"평균 인접 거리: {avg_dist:.2f}m")
print(f"최소 인접 거리: {min(distances):.2f}m")
print(f"최대 인접 거리: {max(distances):.2f}m")
