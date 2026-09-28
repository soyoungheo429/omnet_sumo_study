# -*- coding: utf-8 -*-
"""
patch_config_logging.py
================================================================
algo7_evaluate_k_pdr.py / algo7_isolated_rsu_pdr.py 에
"이번 실행이 몇 Mbps / avoidBeaconSynchronization=?" 였는지를
결과 CSV에 자동으로 같이 기록하는 패치.
VM에서 실행: python3 patch_config_logging.py
================================================================
"""
import os

BASE_PATH = "algo7_evaluate_k_pdr.py"
ISOLATED_PATH = "algo7_isolated_rsu_pdr.py"


def patch_base():
    with open(BASE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "get_run_config" in content:
        print(f"-- {BASE_PATH}: 이미 패치되어 있습니다. 건너뜁니다.")
        return True

    ok = True

    # 1) get_run_config() 함수 추가
    old1 = '''# .sca에서 차량(node) 개수를 못 찾았을 때 사용할 안전한 기본값
# (본 시나리오의 SUMO 라우트가 고정 50대 차량을 사용하는 것과 동일)
FALLBACK_NUM_VEHICLES = 50'''
    new1 = '''# .sca에서 차량(node) 개수를 못 찾았을 때 사용할 안전한 기본값
# (본 시나리오의 SUMO 라우트가 고정 50대 차량을 사용하는 것과 동일)
FALLBACK_NUM_VEHICLES = 50

# 결과 CSV에 실행 당시 설정을 같이 기록하기 위한 정규식.
# [algo7] 여러 조건(bitrate, 동기화 여부)을 오가며 실험하다가 나중에 결과 CSV만
# 봐서는 "이게 몇 Mbps였지?"를 알 수 없어 데이터 신뢰성 문제가 생겼던 적이 있어서 추가.
RE_BITRATE = re.compile(r"nic\\.mac1609_4\\.bitrate\\s*=\\s*([\\w.]+)")
RE_AVOID_SYNC = re.compile(r"avoidBeaconSynchronization\\s*=\\s*(true|false)")


def get_run_config(ini_path: str = None) -> dict:
    """omnetpp_template.ini에서 이번 실행에 실제로 적용되는 핵심 설정
    (bitrate, avoidBeaconSynchronization)을 읽어온다.
    generate_ini()가 numRSUs/rsu 좌표/seed-set만 바꿔 끼우고 나머지는 템플릿을
    그대로 복사하므로, 템플릿에 적힌 값이 곧 실제 실행에 쓰이는 값이다."""
    if ini_path is None:
        ini_path = INI_TEMPLATE
    if not os.path.exists(ini_path):
        return {"Bitrate": "UNKNOWN", "AvoidBeaconSync": "UNKNOWN"}
    with open(ini_path, "r", encoding="utf-8") as f:
        content = f.read()
    bitrate_m = RE_BITRATE.search(content)
    sync_m = RE_AVOID_SYNC.search(content)
    return {
        "Bitrate": bitrate_m.group(1) if bitrate_m else "UNKNOWN",
        "AvoidBeaconSync": sync_m.group(1) if sync_m else "UNKNOWN",
    }'''
    if old1 in content:
        content = content.replace(old1, new1)
    else:
        print(f"!! {BASE_PATH}: [1] FALLBACK_NUM_VEHICLES 블록을 못 찾았습니다.")
        ok = False

    # 2) main()에서 배너 출력 + run_config 확보
    old2 = '''    print("=" * 70)
    print(f" K={args.k_min}~{args.k_max} RSU 배치 대수별 PDR 반복 평가 시작 "
          f"(K당 {args.repeats}회 반복, 후보 CSV: '{args.candidates_csv}')")
    print("=" * 70)'''
    new2 = '''    run_config = get_run_config(INI_TEMPLATE)
    print("=" * 70)
    print(f" [실행 설정 확인] bitrate={run_config['Bitrate']}, "
          f"avoidBeaconSynchronization={run_config['AvoidBeaconSync']}  "
          f"('{INI_TEMPLATE}' 에서 직접 읽음, 결과 CSV에도 그대로 기록됨)")
    print("=" * 70)
    print(f" K={args.k_min}~{args.k_max} RSU 배치 대수별 PDR 반복 평가 시작 "
          f"(K당 {args.repeats}회 반복, 후보 CSV: '{args.candidates_csv}')")
    print("=" * 70)'''
    if old2 in content:
        content = content.replace(old2, new2)
    else:
        print(f"!! {BASE_PATH}: [2] 배너 출력 블록을 못 찾았습니다.")
        ok = False

    # 3) raw_df에 컬럼 추가
    old3 = '''    raw_df = pd.DataFrame(raw_results)
    raw_df.to_csv(args.raw_out, index=False, encoding="utf-8-sig")
    print(f"\\n✔ 반복별 원본 결과가 '{args.raw_out}' 파일로 저장되었습니다.")'''
    new3 = '''    raw_df = pd.DataFrame(raw_results)
    # [algo7] 결과만 봐서는 어떤 bitrate/동기화 조건이었는지 알 수 없어 데이터
    # 신뢰성 문제가 생겼던 적이 있어서, 실행 시점 설정을 모든 행에 그대로 기록.
    raw_df["Bitrate"] = run_config["Bitrate"]
    raw_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]
    raw_df.to_csv(args.raw_out, index=False, encoding="utf-8-sig")
    print(f"\\n✔ 반복별 원본 결과가 '{args.raw_out}' 파일로 저장되었습니다.")'''
    if old3 in content:
        content = content.replace(old3, new3)
    else:
        print(f"!! {BASE_PATH}: [3] raw_df 저장 블록을 못 찾았습니다.")
        ok = False

    # 4) summary_df에 컬럼 추가
    old4 = '''    summary_df = summary_df.round(2)

    display_df = summary_df.rename(columns={
        "K": "K (RSU 대수)",'''
    new4 = '''    summary_df = summary_df.round(2)
    summary_df["Bitrate"] = run_config["Bitrate"]
    summary_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]

    display_df = summary_df.rename(columns={
        "K": "K (RSU 대수)",'''
    if old4 in content:
        content = content.replace(old4, new4)
    else:
        print(f"!! {BASE_PATH}: [4] summary_df 블록을 못 찾았습니다.")
        ok = False

    with open(BASE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    if ok:
        print(f"OK {BASE_PATH} 패치 완료 (4/4)")
    else:
        print(f"!! {BASE_PATH} 일부만 패치됨. 위 실패 항목을 직접 확인하세요.")
    return ok


def patch_isolated():
    with open(ISOLATED_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "get_run_config" in content:
        print(f"-- {ISOLATED_PATH}: 이미 패치되어 있습니다. 건너뜁니다.")
        return True

    ok = True

    old1 = '''    n_candidates = len(all_candidates_df)
    print(f"'{args.candidates_csv}' 에서 후보 좌표 {n_candidates}개 로딩 완료.")
    print("=" * 70)
    print(f" 후보지 {n_candidates}개 각각을 단독(K=1)으로 배치하여 PDR 평가 시작 "
          f"(후보지당 {args.repeats}회 반복)")
    print("=" * 70)'''
    new1 = '''    n_candidates = len(all_candidates_df)
    print(f"'{args.candidates_csv}' 에서 후보 좌표 {n_candidates}개 로딩 완료.")

    run_config = base.get_run_config(base.INI_TEMPLATE)
    print("=" * 70)
    print(f" [실행 설정 확인] bitrate={run_config['Bitrate']}, "
          f"avoidBeaconSynchronization={run_config['AvoidBeaconSync']}  "
          f"('{{base.INI_TEMPLATE}}' 에서 직접 읽음, 결과 CSV에도 그대로 기록됨)")
    print("=" * 70)
    print(f" 후보지 {n_candidates}개 각각을 단독(K=1)으로 배치하여 PDR 평가 시작 "
          f"(후보지당 {args.repeats}회 반복)")
    print("=" * 70)'''
    # base.INI_TEMPLATE 는 f-string 안에서 그대로 평가되어야 하므로 이스케이프 정리
    new1 = new1.replace("'{{base.INI_TEMPLATE}}'", "'{base.INI_TEMPLATE}'")
    if old1 in content:
        content = content.replace(old1, new1)
    else:
        print(f"!! {ISOLATED_PATH}: [1] 배너 출력 블록을 못 찾았습니다.")
        ok = False

    old2 = '''    raw_df = pd.DataFrame(raw_results)
    raw_df.to_csv(args.raw_out, index=False, encoding="utf-8-sig")
    print(f"\\n✔ 반복별 원본 결과가 '{args.raw_out}' 파일로 저장되었습니다.")'''
    new2 = '''    raw_df = pd.DataFrame(raw_results)
    raw_df["Bitrate"] = run_config["Bitrate"]
    raw_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]
    raw_df.to_csv(args.raw_out, index=False, encoding="utf-8-sig")
    print(f"\\n✔ 반복별 원본 결과가 '{args.raw_out}' 파일로 저장되었습니다.")'''
    if old2 in content:
        content = content.replace(old2, new2)
    else:
        print(f"!! {ISOLATED_PATH}: [2] raw_df 저장 블록을 못 찾았습니다.")
        ok = False

    old3 = '''    summary_df["Received_Std"] = summary_df["Received_Std"].fillna(0.0)
    summary_df = summary_df.round(2)'''
    new3 = '''    summary_df["Received_Std"] = summary_df["Received_Std"].fillna(0.0)
    summary_df = summary_df.round(2)
    summary_df["Bitrate"] = run_config["Bitrate"]
    summary_df["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]'''
    if old3 in content:
        content = content.replace(old3, new3)
    else:
        print(f"!! {ISOLATED_PATH}: [3] summary_df 블록을 못 찾았습니다.")
        ok = False

    with open(ISOLATED_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    if ok:
        print(f"OK {ISOLATED_PATH} 패치 완료 (3/3)")
    else:
        print(f"!! {ISOLATED_PATH} 일부만 패치됨. 위 실패 항목을 직접 확인하세요.")
    return ok


if __name__ == "__main__":
    ok1 = patch_base()
    ok2 = patch_isolated()
    if ok1 and ok2:
        print("\n두 파일 모두 패치 완료. 이제부터는 결과 CSV에 Bitrate/AvoidBeaconSync 컬럼이 자동으로 남습니다.")
    else:
        print("\n!! 일부 패치 실패. 실패한 블록은 위 메시지를 참고해서 수동으로 확인/수정해주세요.")
