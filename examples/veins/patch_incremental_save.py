# -*- coding: utf-8 -*-
"""
patch_incremental_save.py
================================================================
algo7_evaluate_k_pdr.py 가 결과를 끝까지 메모리에 모아뒀다가 마지막에만
CSV로 저장하던 걸, 매 반복 직후 즉시 CSV에 한 줄씩 append하도록 패치.
(예전에 크래시로 269/810개 결과를 통째로 날린 적이 있어서 재방지용)
VM에서 실행: python3 patch_incremental_save.py
================================================================
"""
import os

BASE_PATH = "algo7_evaluate_k_pdr.py"


def patch():
    with open(BASE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if "append_row_to_csv" in content:
        print(f"-- {BASE_PATH}: 이미 패치되어 있습니다. 건너뜁니다.")
        return True

    ok = True

    # 1) append_row_to_csv() 헬퍼 추가
    old1 = "def reset_results_dir() -> None:"
    new1 = '''def append_row_to_csv(row: dict, csv_path: str) -> None:
    """[algo7] 크래시로 269/810개 결과를 통째로 날렸던 적이 있어서(로그 파싱으로
    겨우 복구), 매 반복 결과를 그 즉시 CSV에 한 줄씩 append한다. 헤더는 파일이
    없을 때만 쓴다 (mode='a'). 이러면 중간에 죽어도 그때까지의 결과는 남는다."""
    row_df = pd.DataFrame([row])
    write_header = not os.path.exists(csv_path)
    row_df.to_csv(csv_path, mode="a", header=write_header, index=False, encoding="utf-8-sig")


def reset_results_dir() -> None:'''
    if old1 in content:
        content = content.replace(old1, new1)
    else:
        print(f"!! [1] reset_results_dir 정의를 못 찾았습니다.")
        ok = False

    # 2) main() 시작 시 이전 raw_out 파일 정리
    old2 = '''    print(f" K={args.k_min}~{args.k_max} RSU 배치 대수별 PDR 반복 평가 시작 "
          f"(K당 {args.repeats}회 반복, 후보 CSV: '{args.candidates_csv}')")
    print("=" * 70)

    raw_results = []'''
    new2 = '''    print(f" K={args.k_min}~{args.k_max} RSU 배치 대수별 PDR 반복 평가 시작 "
          f"(K당 {args.repeats}회 반복, 후보 CSV: '{args.candidates_csv}')")
    print("=" * 70)

    # [algo7] 중간에 죽어도 그때까지 결과가 남도록 매 반복마다 즉시 append하므로,
    # 이번 실행 시작 시점에 이전 raw_out 파일이 있다면 지우고 깨끗하게 새로 쓴다.
    if os.path.exists(args.raw_out):
        os.remove(args.raw_out)

    raw_results = []'''
    if old2 in content:
        content = content.replace(old2, new2)
    else:
        print(f"!! [2] raw_results = [] 초기화 지점을 못 찾았습니다.")
        ok = False

    # 3) ini 생성 실패 시 즉시 append
    old3 = '''            except FileNotFoundError as e:
                print(f"!! [K={k} / repeat {repeat}] ini 생성 실패: {e}")
                raw_results.append({
                    "K": k, "Repeat": repeat, "Seed": seed,
                    "Total_Generated": 0, "Num_Vehicles": 0,
                    "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
                    "Elapsed_Sec": 0.0,
                })
                completed_runs += 1
                log_progress()
                continue'''
    new3 = '''            except FileNotFoundError as e:
                print(f"!! [K={k} / repeat {repeat}] ini 생성 실패: {e}")
                row = {
                    "K": k, "Repeat": repeat, "Seed": seed,
                    "Total_Generated": 0, "Num_Vehicles": 0,
                    "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
                    "Elapsed_Sec": 0.0,
                    "Bitrate": run_config["Bitrate"], "AvoidBeaconSync": run_config["AvoidBeaconSync"],
                }
                raw_results.append(row)
                append_row_to_csv(row, args.raw_out)
                completed_runs += 1
                log_progress()
                continue'''
    if old3 in content:
        content = content.replace(old3, new3)
    else:
        print(f"!! [3] ini 생성 실패 처리 블록을 못 찾았습니다.")
        ok = False

    # 4) 시뮬레이션 실패/성공 시 즉시 append
    old4 = '''            if not success:
                raw_results.append({
                    "K": k, "Repeat": repeat, "Seed": seed,
                    "Total_Generated": 0, "Num_Vehicles": 0,
                    "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
                    "Elapsed_Sec": round(elapsed_sec, 2),
                })
                log_progress()
                continue

            # 4) PDR 파싱 및 계산
            result = parse_pdr(k, repeat, seed, elapsed_sec)
            raw_results.append(result)
            print(f"   [K={k} / repeat {repeat}] 총 발신: {result['Total_Generated']}, "
                  f"차량 대수: {result['Num_Vehicles']}, "
                  f"기대 수신: {result['Expected_Received']}, "
                  f"실제 수신: {result['Actual_Received']}, "
                  f"PDR: {result['PDR(%)']:.2f}%, "
                  f"실측 소요시간: {result['Elapsed_Sec']:.1f}s")'''
    new4 = '''            if not success:
                row = {
                    "K": k, "Repeat": repeat, "Seed": seed,
                    "Total_Generated": 0, "Num_Vehicles": 0,
                    "Expected_Received": 0, "Actual_Received": 0, "PDR(%)": 0.0,
                    "Elapsed_Sec": round(elapsed_sec, 2),
                    "Bitrate": run_config["Bitrate"], "AvoidBeaconSync": run_config["AvoidBeaconSync"],
                }
                raw_results.append(row)
                append_row_to_csv(row, args.raw_out)
                log_progress()
                continue

            # 4) PDR 파싱 및 계산
            result = parse_pdr(k, repeat, seed, elapsed_sec)
            result["Bitrate"] = run_config["Bitrate"]
            result["AvoidBeaconSync"] = run_config["AvoidBeaconSync"]
            raw_results.append(result)
            append_row_to_csv(result, args.raw_out)
            print(f"   [K={k} / repeat {repeat}] 총 발신: {result['Total_Generated']}, "
                  f"차량 대수: {result['Num_Vehicles']}, "
                  f"기대 수신: {result['Expected_Received']}, "
                  f"실제 수신: {result['Actual_Received']}, "
                  f"PDR: {result['PDR(%)']:.2f}%, "
                  f"실측 소요시간: {result['Elapsed_Sec']:.1f}s")'''
    if old4 in content:
        content = content.replace(old4, new4)
    else:
        print(f"!! [4] 시뮬레이션 결과 처리 블록을 못 찾았습니다.")
        ok = False

    with open(BASE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    if ok:
        print(f"OK {BASE_PATH} 즉시-저장 패치 완료 (4/4)")
    else:
        print(f"!! {BASE_PATH} 일부만 패치됨. 위 실패 항목을 직접 확인하세요.")
    return ok


if __name__ == "__main__":
    patch()
