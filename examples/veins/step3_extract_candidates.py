import math
import xml.etree.ElementTree as ET

try:
    from pyproj import Transformer
except ModuleNotFoundError:
    Transformer = None


def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def to_latlon(transformer, net_offset, pos):
    if transformer is None:
        return None, None
    projected_x = pos[0] - net_offset[0]
    projected_y = pos[1] - net_offset[1]
    return transformer.transform(projected_x, projected_y)


def format_geo(value):
    if value is None:
        return "N/A"
    return f"{value:.6f}"


def generate_rsu_configs(net_file, min_dist=150):
    try:
        tree = ET.parse(net_file)
        root = tree.getroot()
    except FileNotFoundError:
        print(f"Error: {net_file} 파일을 찾을 수 없습니다.")
        return

    location = root.find("location")
    if location is None:
        print("Error: net.xml location 정보를 찾을 수 없습니다.")
        return

    net_offset = tuple(
        float(v) for v in location.get("netOffset", "0.0,0.0").split(",")
    )
    proj_str = location.get(
        "projParameter",
        "+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs",
    )
    transformer = None
    if Transformer is not None:
        transformer = Transformer.from_crs(proj_str, "epsg:4326", always_xy=True)

    junction_candidates = []

    for junction in root.findall("junction"):
        j_id = junction.get("id")
        j_type = junction.get("type")

        if j_type in ["priority", "traffic_light", "right_before_left"]:
            x = float(junction.get("x"))
            y = float(junction.get("y"))

            inc_lanes = junction.get("incLanes", "").split()
            degree = len(inc_lanes)

            if degree >= 3:
                junction_candidates.append(
                    {"id": j_id, "pos": (x, y), "degree": degree}
                )

    for cand in junction_candidates:
        density = sum(
            1
            for other in junction_candidates
            if cand != other
            and calculate_distance(cand["pos"], other["pos"]) < min_dist
        )
        cand["density"] = density

    junction_candidates.sort(key=lambda x: (x["degree"], x["density"]), reverse=True)

    final_rsu_list = []
    for current in junction_candidates:
        if not any(
            calculate_distance(current["pos"], chosen["pos"]) < min_dist
            for chosen in final_rsu_list
        ):
            final_rsu_list.append(current)

    print(f"\n# 추출 결과: {len(final_rsu_list)}개의 최적 지점이 선정되었습니다.\n")
    print(
        f"{'No':<4} | {'ID':<25} | {'Deg':<4} | {'Dens':<4} | {'Sim X':<10} | {'Sim Y':<10} | {'Latitude':<12} | {'Longitude':<12}"
    )
    print("-" * 110)

    for i, rsu in enumerate(final_rsu_list):
        lon, lat = to_latlon(transformer, net_offset, rsu["pos"])
        print(
            f"{i:<4} | {rsu['id']:<25} | {rsu['degree']:<4} | {rsu['density']:<4} | {rsu['pos'][0]:<10.2f} | {rsu['pos'][1]:<10.2f} | {format_geo(lat):<12} | {format_geo(lon):<12}"
        )

    print("\n[Config]")
    for i, rsu in enumerate(final_rsu_list):
        lon, lat = to_latlon(transformer, net_offset, rsu["pos"])
        print(
            f"# RSU_{i} | ID: {rsu['id']} | 위치: {format_geo(lat)}, {format_geo(lon)}"
        )
        print(f"*.rsu[{i}].mobility.x = {rsu['pos'][0]:.2f}")
        print(f"*.rsu[{i}].mobility.y = {rsu['pos'][1]:.2f}")
        print(f"*.rsu[{i}].mobility.z = 3")


generate_rsu_configs("joined_buslanes.net.xml", min_dist=150)
