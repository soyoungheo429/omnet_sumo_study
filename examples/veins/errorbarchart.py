import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# =========================================================
# 1. 파일 설정 (사용자 결과 수치와 대조하여 최적의 파일 선택)
# =========================================================
results_config = {
    "GA (Junction-based)": "ga_multirun_results_confirm.csv",
    "SA (Junction-based)": "algo3_sa_confirm_avg_results2.csv",
    "GA (Standard)": "ga_multirun_results2.csv",
    "SA (Standard)": "ms_asa_multirun_results2.csv"
}

def get_robustness_stats(file_path):
    if not os.path.exists(file_path):
        print(f"경고: {file_path} 파일을 찾을 수 없습니다.")
        return None
    
    df = pd.read_csv(file_path)
    
    # PDR 컬럼 찾기 (PDR 또는 Max_PDR)
    pdr_col = 'Max_PDR' if 'Max_PDR' in df.columns else 'PDR' if 'PDR' in df.columns else None
    if not pdr_col:
        print(f"경고: {file_path}에서 PDR 관련 컬럼을 찾을 수 없습니다.")
        return None
        
    # 독립 실행 단위를 나타내는 컬럼 찾기 (Run, AgentID, RunIdx 순서로 확인)
    run_col = None
    for col in ['Run', 'AgentID', 'RunIdx']:
        if col in df.columns:
            run_col = col
            break
    
    if run_col:
        # 각 독립 실행(Run/Agent)별로 도달한 최고 PDR 추출
        best_pdrs = df.groupby(run_col)[pdr_col].max()
        print(f"  -> '{file_path}' 분석 완료: '{run_col}' 컬럼 기준 {len(best_pdrs)}개 샘플 확인")
    else:
        # 만약 구분 컬럼이 아예 없다면 전체를 하나의 샘플로 간주
        best_pdrs = pd.Series([df[pdr_col].max()])
        print(f"  -> '{file_path}' 분석 완료: 구분 컬럼 없음. 전체 최고점 1개 샘플 사용")
        
    return {
        "mean": best_pdrs.mean(),
        "std": best_pdrs.std() if len(best_pdrs) > 1 else 0,
        "max": best_pdrs.max(),
        "min": best_pdrs.min(),
        "count": len(best_pdrs)
    }

# =========================================================
# 2. 데이터 집계
# =========================================================
labels = []
means = []
stds = []
maxs = []
mins = []

print("알고리즘별 통계 요약:")
for name, path in results_config.items():
    stats = get_robustness_stats(path)
    if stats:
        labels.append(name)
        means.append(stats['mean'])
        stds.append(stats['std'])
        maxs.append(stats['max'])
        mins.append(stats['min'])
        print(f"- {name:20s}: 평균 {stats['mean']:.2f}%, 표준편차 {stats['std']:.2f}% (Runs: {stats['count']})")

# =========================================================
# 3. 에러 바 차트 시각화
# =========================================================
if not means:
    print("오류: 시각화할 데이터가 없습니다.")
    exit()

plt.figure(figsize=(10, 7))
plt.rcParams['font.sans-serif'] = ['Malgun Gothic'] # 한글 깨짐 방지 (Windows)
plt.rcParams['axes.unicode_minus'] = False

x_pos = np.arange(len(labels))

# 에러 바 그리기
plt.errorbar(x_pos, means, yerr=stds, fmt='o', color='royalblue',
            ecolor='lightcoral', elinewidth=3, capsize=10, 
            markersize=10, label='평균 PDR ± 표준편차')

# 개별 실행의 최대/최소값 표시
plt.scatter(x_pos, maxs, marker='^', color='green', s=100, label='최고 PDR', zorder=3)
plt.scatter(x_pos, mins, marker='v', color='red', s=100, label='최저 PDR', zorder=3)

# 차트 디테일
plt.xticks(x_pos, labels, fontsize=12)
plt.ylabel("Packet Delivery Ratio (PDR) %", fontsize=13)
plt.title("Meta-Heuristic Algorithms Robustness Comparison", fontsize=15, pad=25)
plt.ylim(0, max(maxs) * 1.2 if maxs else 40)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.legend(loc='best')

# 바 위에 평균값 텍스트 표시
for i, v in enumerate(means):
    plt.text(i, v + 1, f"{v:.2f}%", ha='center', color='blue', fontweight='bold', fontsize=11)

plt.tight_layout()

output_filename = "errorbar_mh_comparison.png"
plt.savefig(output_filename)
print(f"\n성공: 에러 바 차트가 '{output_filename}'으로 저장되었습니다.")
plt.show()

