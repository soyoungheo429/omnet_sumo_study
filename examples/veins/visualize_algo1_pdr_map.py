# -*- coding: utf-8 -*-
import pandas as pd
import folium

TREND_CSV = "algo7_isolated_rsu_trend_block4_algo1.csv"
OUT_HTML = "algo1_pdr_map.html"

rsu_locations = [
    {"id": "cluster_15159499_18038479_21113262_347787163_8851291", "lat": 49.576082, "lon": 11.015880},
    {"id": "cluster_12247700_12529558", "lat": 49.577650, "lon": 11.004480},
    {"id": "cluster_347349857_347349858", "lat": 49.576618, "lon": 11.001708},
    {"id": "26841354", "lat": 49.578178, "lon": 11.023730},
    {"id": "17574061", "lat": 49.579060, "lon": 11.020083},
    {"id": "348243041", "lat": 49.577885, "lon": 11.016468},
    {"id": "16933971", "lat": 49.581182, "lon": 11.010784},
    {"id": "19755457", "lat": 49.577864, "lon": 11.007987},
    {"id": "12247702", "lat": 49.580866, "lon": 11.005721},
    {"id": "14319161", "lat": 49.572468, "lon": 11.000520},
    {"id": "19769114", "lat": 49.570403, "lon": 11.000071},
    {"id": "cluster_314448309_824235741", "lat": 49.574876, "lon": 11.009275},
    {"id": "89119479", "lat": 49.574731, "lon": 11.024936},
    {"id": "21970003", "lat": 49.573616, "lon": 11.016800},
    {"id": "17574097", "lat": 49.580694, "lon": 11.024158},
    {"id": "26841336", "lat": 49.578340, "lon": 11.027198},
    {"id": "1154372516", "lat": 49.573137, "lon": 11.030161},
    {"id": "26841358", "lat": 49.575516, "lon": 11.027625},
    {"id": "12452103", "lat": 49.568920, "lon": 11.031449},
    {"id": "1391319738", "lat": 49.576396, "lon": 11.012981},
    {"id": "19755421", "lat": 49.581721, "lon": 11.017490},
    {"id": "21970024", "lat": 49.572838, "lon": 11.019429},
    {"id": "252726522", "lat": 49.569565, "lon": 11.027230},
    {"id": "26841333", "lat": 49.581650, "lon": 11.033591},
    {"id": "314448358", "lat": 49.573159, "lon": 11.007889},
    {"id": "354910587", "lat": 49.569281, "lon": 11.003777},
    {"id": "cluster_1291385696_21971288", "lat": 49.574719, "lon": 11.031625},
]

loc_df = pd.DataFrame(rsu_locations)
loc_df["Rank"] = range(1, len(loc_df) + 1)

trend_df = pd.read_csv(TREND_CSV)
merged = loc_df.merge(trend_df, on="Rank", how="inner")

merged = merged.sort_values(by="PDR_Mean", ascending=False).reset_index(drop=True)
merged["pdr_rank"] = merged.index + 1

m = folium.Map(location=[49.5760, 11.0150], zoom_start=14, tiles="CartoDB Positron")

for _, row in merged.iterrows():
    lat, lon = row["lat"], row["lon"]
    pdr_val = row["PDR_Mean"]
    original_rank = int(row["Rank"])
    pdr_rank = int(row["pdr_rank"])

    if pdr_rank == 1:
        color = "orange"
    elif pdr_rank <= 3:
        color = "green"
    else:
        color = "red"

    folium.Marker(
        location=[lat, lon],
        popup=f"<b>PDR 순위 {pdr_rank}위 (PDR: {pdr_val:.2f}%)</b><br>"
              f"algo1 원래 순위(degree/density): {original_rank}<br>"
              f"ID: {row['id']}",
        icon=folium.DivIcon(
            html=f"""
                <div style="
                    font-family: sans-serif; color: white; background-color: {color};
                    border-radius: 50%; width: 26px; height: 26px;
                    display: flex; justify-content: center; align-items: center;
                    font-size: 12px; font-weight: bold; border: 2px solid white;
                    box-shadow: 0 0 5px rgba(0,0,0,0.5);">
                    {pdr_rank}
                </div>
            """
        ),
    ).add_to(m)

    folium.Circle(
        location=[lat, lon], radius=150, color=color, fill=True,
        fill_opacity=0.3 if pdr_rank <= 3 else 0.1,
    ).add_to(m)

m.save(OUT_HTML)
print("저장 완료:", OUT_HTML)
print(merged[["pdr_rank", "Rank", "id", "PDR_Mean"]].to_string(index=False))
