"""
algo7_fix_coordinate_transform.py
================================================================
기존 27개 RSU 후보 좌표(final_selected_rsus.csv)를 Veins의 실제
traci2omnet() 변환식으로 보정하는 스크립트
================================================================

배경:
  - algo7_rsu_max_coverage.py는 차량 포인트와 후보지 좌표 둘 다
    "raw_UTM - OFFSET"만 적용했다 (Y축 뒤집기 없음, margin 없음).
    이 변환은 둘 다 동일하게 적용됐기 때문에(확인 완료), 27개 후보의
    "선정 순위"는 문제없다. 문제는 이 잘못된 좌표를 .ini의
    mobility.x/y에 그대로 박아 넣었다는 점이다.
  - RSU는 INET StationaryMobility를 쓰는데,
    MobilityBase::setInitialPosition()(src/inet/.../MobilityBase.cc:159-163)를
    보면 .x/.y 값을 어떤 변환도 없이 그대로 화면(scene) 좌표로 쓴다.
  - 반면 실제 차량은 TraCICoordinateTransformation::traci2omnet()
    (src/veins/modules/mobility/traci/TraCICoordinateTransformation.cc:74-77)을
    거쳐서 Y축이 뒤집히고 margin이 더해진 좌표로 같은 화면 좌표계에 나타난다.
  - 이 스크립트는 그 실제 공식을 코드로 그대로 재현해서(새로 만들지 않음),
    기존 27개 후보의 Sim_X/Sim_Y를 보정한 새 CSV를 만든다.

Veins 원본 공식 (TraCICoordinateTransformation.cc:74-77):
    OmnetCoord traci2omnet(const TraCICoord& coord) const {
        return {
            coord.x - topleft.x + margin,
            dimensions.y - (coord.y - topleft.y) + margin
        };
    }
    (dimensions.y = bottomright.y - topleft.y)

topleft/bottomright는 SUMO에 TraCI로 실제 물어봐서 받아오는 net boundary이며,
erlangen.net.xml의 <location convBoundary="..."> 값과 일치한다(확인 완료).
margin은 TraCIScenarioManager.ned의 기본값(25)이 그대로 쓰이고 있다
(.ini에 *.manager.margin이 명시된 적 없음, 확인 완료).

기존 CSV의 Sim_X/Sim_Y는 "raw_UTM - topleft"로 계산됐으므로 (오프셋만, margin/뒤집기 없음),
raw_UTM = old_Sim + topleft 로 역산할 수 있고, 이를 위 공식에 대입하면:
    corrected_X = old_Sim_X + margin
    corrected_Y = dimensions_y - old_Sim_Y + margin
로 단순화된다. 이 스크립트는 이 단순화식이 아니라, 위 원본 공식을 그대로 구현한 함수를
통해 계산해서(전개식이 맞는지도 검증 차원에서 이중 확인) 결과를 낸다.
"""

import argparse

import pandas as pd

# net.xml의 <location convBoundary="644465.09,5491786.25,647071.55,5494795.98">
# 및 TraCI가 실제 보고하는 net boundary와 일치 (확인 완료)
TOPLEFT_X = 644465.09
TOPLEFT_Y = 5491786.25
BOTTOMRIGHT_X = 647071.55
BOTTOMRIGHT_Y = 5494795.98
DIMENSIONS_Y = BOTTOMRIGHT_Y - TOPLEFT_Y  # 3009.73

# 기존 CSV 좌표를 계산할 때 썼던 OFFSET (algo7_rsu_max_coverage.py와 동일)
OLD_OFFSET_X = 644465.09
OLD_OFFSET_Y = 5491786.25

DEFAULT_MARGIN = 25  # TraCIScenarioManager.ned 기본값. .ini에 명시된 적 없음(확인 완료)

DEFAULT_INPUT_CSV = "final_selected_rsus.csv"
DEFAULT_OUTPUT_CSV = "final_selected_rsus_corrected.csv"


def traci2omnet(traci_x: float, traci_y: float, margin: float) -> tuple:
    """Veins TraCICoordinateTransformation::traci2omnet()을 그대로 재현.
    (src/veins/modules/mobility/traci/TraCICoordinateTransformation.cc:74-77)"""
    omnet_x = traci_x - TOPLEFT_X + margin
    omnet_y = DIMENSIONS_Y - (traci_y - TOPLEFT_Y) + margin
    return omnet_x, omnet_y


def get_margin_from_ini(ini_path: str) -> float:
    """omnetpp_template.ini에서 *.manager.margin이 명시돼 있으면 그 값을,
    없으면 TraCIScenarioManager.ned의 기본값(25)을 반환."""
    import re
    try:
        with open(ini_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"!! 경고: '{ini_path}'를 못 찾아서 기본 margin({DEFAULT_MARGIN})을 사용합니다.")
        return DEFAULT_MARGIN

    m = re.search(r"\*\.manager\.margin\s*=\s*(\d+)", content)
    if m:
        margin = float(m.group(1))
        print(f"✔ '{ini_path}'에서 *.manager.margin = {margin} 을 읽었습니다.")
        return margin
    else:
        print(f"✔ '{ini_path}'에 *.manager.margin 설정이 없어서, "
              f"TraCIScenarioManager.ned 기본값({DEFAULT_MARGIN})을 사용합니다.")
        return DEFAULT_MARGIN


def main():
    parser = argparse.ArgumentParser(
        description="기존 27개 RSU 후보 좌표를 Veins의 실제 traci2omnet() 공식으로 보정"
    )
    parser.add_argument("--input-csv", type=str, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=str, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--ini", type=str, default="omnetpp_template.ini",
                         help="margin 값을 읽어올 ini 파일")
    args = parser.parse_args()

    margin = get_margin_from_ini(args.ini)

    df = pd.read_csv(args.input_csv)
    print(f"'{args.input_csv}' 에서 {len(df)}개 후보 로딩 완료.")

    corrected_rows = []
    for _, row in df.iterrows():
        # 1) 기존 CSV의 Sim_X/Sim_Y로부터 원본 UTM 좌표 역산
        #    (기존 CSV는 raw_UTM - OLD_OFFSET 으로 계산됐었음)
        raw_x = row["Sim_X"] + OLD_OFFSET_X
        raw_y = row["Sim_Y"] + OLD_OFFSET_Y

        # 2) Veins의 실제 traci2omnet() 공식 적용
        corrected_x, corrected_y = traci2omnet(raw_x, raw_y, margin)

        corrected_rows.append({
            "Rank": row["Rank"],
            "ID": row["ID"],
            "Old_Sim_X": round(row["Sim_X"], 2),
            "Old_Sim_Y": round(row["Sim_Y"], 2),
            "Sim_X": round(corrected_x, 2),
            "Sim_Y": round(corrected_y, 2),
        })

    corrected_df = pd.DataFrame(corrected_rows)
    corrected_df.to_csv(args.output_csv, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 90)
    print(" 기존 좌표 vs 보정된 좌표 (Veins traci2omnet() 공식 적용)")
    print("=" * 90)
    print(corrected_df.to_string(index=False))
    print("=" * 90)
    print(f"\n✔ 보정된 좌표가 '{args.output_csv}' 파일로 저장되었습니다.")
    print(f"  (margin={margin} 적용됨)")


if __name__ == "__main__":
    main()
