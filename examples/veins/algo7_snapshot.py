# -*- coding: utf-8 -*-
"""
[V4] SUMO XML 데이터에서 10초 ~ 200초 구간 동안
정확히 2초(2.0s) 간격으로 스냅샷을 추출하는 스크립트
"""
import xml.etree.ElementTree as ET
import pandas as pd

def parse_snapshots_2sec(xml_file, csv_output_file, start_time=10.0, end_time=200.0, interval=2.0):
    print(f"[{xml_file}] 파싱을 시작합니다... (목표: {start_time}초부터 {interval}초 간격)")
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    data = []
    snapshot_count = 0
    next_target_time = start_time  # 첫 스냅샷 목표 시간 (10.0초)
    
    for timestep in root.findall('timestep'):
        time_val = float(timestep.get('time'))
        
        # 200초를 넘어가면 더 이상 파싱할 필요 없이 루프 종료
        if time_val > end_time:
            break
            
        # 현재 타임스텝이 목표 시간(next_target_time)에 도달했거나 지났을 때 추출
        # (부동소수점 오차 보정을 위해 약간의 마진 -0.01을 줍니다)
        if time_val >= next_target_time - 0.01:
            # 차량 데이터가 존재하는지 확인
            vehicles = timestep.findall('vehicle')
            if vehicles:
                snapshot_count += 1
                for vehicle in vehicles:
                    data.append({
                        'snapshot_no': snapshot_count,
                        'time': time_val,
                        'vehicle_id': vehicle.get('id'),
                        'x': float(vehicle.get('x')),
                        'y': float(vehicle.get('y'))
                    })
            
            # 다음 목표 시간 설정 (예: 10.0초 찰칵 완료 -> 다음 목표는 12.0초)
            next_target_time += interval
            
    df = pd.DataFrame(data)
    df.to_csv(csv_output_file, index=False, encoding='utf-8-sig')
    
    print("-" * 50)
    print(f"✔ 파싱 완료!")
    print(f"✔ 추출된 스냅샷 수: {snapshot_count}장")
    print(f"✔ 실제 데이터 수집 구간: {start_time}초 ~ {time_val}초 ({interval}초 간격)")
    print(f"✔ 총 수집된 차량 좌표 데이터(스티커) 수: {len(df)}개")
    print(f"✔ 결과 파일 저장 완료: {csv_output_file}")
    print("-" * 50)
    
    return df

if __name__ == "__main__":
    INPUT_XML = "vehicle_snapshots.xml"  # SUMO에서 뽑아낸 원본 XML 파일명
    OUTPUT_CSV = "vehicle_snapshots.csv" # 저장할 CSV 파일명
    
    # 10초부터 200초까지 2초 간격으로 추출 실행
    parse_snapshots_2sec(INPUT_XML, OUTPUT_CSV, start_time=10.0, end_time=200.0, interval=2.0)
