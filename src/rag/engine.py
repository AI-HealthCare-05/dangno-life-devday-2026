from __future__ import annotations

import re
from dataclasses import dataclass

from app.core import config
from src.rag.chunking import Chunk, split_into_chunks
from src.rag.embeddings import EmbeddingError, get_embedding_provider
from src.rag.generation import AnswerGenerationError, get_generation_provider
from src.rag.qdrant import QdrantError, qdrant_search
from src.rag.retrieval import hybrid_search, top_chunks
from src.rag.verification import cited_document_ids, verify_sentences


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    title: str
    url: str
    text: str
    keywords: tuple[str, ...]
    # 정보 확인일(YYYY-MM-DD). 근거 문서·링크가 갱신되면 이 값도 함께 갱신한다
    # (docs/frontend/challenge-evidence.md의 "근거 확인일과 버전" 관리 원칙과 동일).
    checked_at: str


APPROVED_DOCUMENTS = (
    KnowledgeDocument(
        "kdca-diabetes",
        "질병관리청 국가건강정보포털 - 당뇨병",
        "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=5292",
        "당뇨병 예방과 관리를 위해 규칙적인 신체활동, 균형 있는 식사, 적정 체중 유지가 중요합니다.",
        ("당뇨", "혈당", "예방", "생활습관", "식사"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "kdca-diabetes-exercise",
        "질병관리청 국가건강정보포털 - 당뇨환자의 운동요법",
        "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=3390",
        "당뇨병 위험이 높은 사람은 중등도 강도의 유산소 운동을 주 150분 이상, 근력 운동을 주 2회 이상 하면 당뇨병 예방에 도움이 됩니다.",
        ("당뇨", "운동", "예방", "유산소", "근력운동", "혈당"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-exercise",
        "대한당뇨병학회 - 당뇨병과 운동",
        "https://www.diabetes.or.kr/general/exercise/exercise_01.php",
        "당뇨병 환자는 일주일에 3일 이상, 숨이 조금 찰 정도의 강도로 하루 30~60분 정도 운동하는 것이 좋습니다. 산책, 조깅, 맨손체조, 자전거 타기 같은 가벼운 전신 운동이 권장됩니다.",
        ("당뇨", "운동", "빈도", "강도", "예방", "혈당"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-exercise-intensity",
        "대한당뇨병학회 - 혈당 낮추는 가장 효과적인 유산소 운동은?",
        "https://www.diabetes.or.kr/bbs/?code=news&mode=view&number=1196",
        "운동 강도는 '약간 힘들다'고 느껴지는 정도(자각인지도 12~14)가 적당하며, 숨이 약간 차고 옆 사람과 대화가 가능한 정도가 좋습니다. 목표 심박수는 최대심박수(220-나이)에 원하는 운동 강도(%)를 곱해서 계산할 수 있습니다.",
        ("당뇨", "운동", "강도", "심박수", "유산소운동", "혈당"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "kdca-diabetes-diet",
        "질병관리청 국가건강정보포털 - 당뇨환자의 식이요법",
        "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=3388",
        "당뇨병 환자는 탄수화물을 전체 에너지의 55~65% 정도로 섭취하면 혈당 개선에 도움이 됩니다. 채소는 즙보다 생채소로, 과일은 주스보다 생과일로 섭취하는 것이 좋으며, 음주는 남자 2잔, 여자 1잔을 넘지 않도록 합니다.",
        ("당뇨", "식이요법", "탄수화물", "식사", "음주", "혈당"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "kdca-prediabetes",
        "질병관리청 국가건강정보포털 - 당뇨병전단계, 정상으로 되돌릴 수 있을까요?",
        "https://health.kdca.go.kr/healthinfo/biz/health/ntcnInfo/healthSourc/thtimtCntnts/thtimtCntntsView.do?thtimt_cntnts_sn=41",
        "당뇨병전단계는 매년 약 8%가 당뇨병으로 진행하지만, 체중을 5~7% 이상 줄이고 지방 섭취를 전체 열량의 25% 이하로, 신체활동을 주 150분 이상으로 늘리는 생활습관 교정을 통해 당뇨병으로의 진행을 58%까지 억제할 수 있습니다. 당뇨병전단계인 경우 매년 1회 정도 정기적으로 혈당 검사를 받는 것이 좋습니다.",
        ("당뇨", "전단계", "예방", "위험군", "체중감량", "생활습관"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "kdca-diabetes-complications",
        "질병관리청 국가건강정보포털 - 당뇨병 만성합병증",
        "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=2351",
        "당뇨병의 만성합병증은 망막병증·신장질환·신경병증 같은 미세혈관 합병증과 관상동맥질환·뇌졸중 같은 대혈관 합병증으로 나뉩니다. 2형당뇨병은 진단과 동시에 안과검진을 받아야 하며, 식사는 제때에 반찬은 골고루 양은 알맞게 섭취하고 규칙적으로 운동하며 정기적으로 병원을 방문하는 것이 중요합니다.",
        ("당뇨", "합병증", "검진", "망막", "신장", "신경병증"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "samsunghospital-diabetes-management",
        "삼성서울병원 당뇨교육실 - 당뇨병 관리방법",
        "https://www.samsunghospital.com/dept/main/index.do?DP_CODE=DM&MENU_ID=008",
        "당뇨병 관리는 혈당뿐 아니라 혈압, 체중, 콜레스테롤을 함께 관리하는 것이 중요합니다. 당뇨인의 일반적인 혈압조절 목표는 130/80mmHg 미만이며, 콜레스테롤은 적어도 1년에 한 번 이상 검사받아야 합니다. 비만한 당뇨인이 체중감량을 통해 표준체중을 유지하면 혈당뿐 아니라 혈압과 콜레스테롤도 함께 낮아질 수 있습니다.",
        ("당뇨", "혈압", "콜레스테롤", "체중", "관리목표", "합병증"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-definition",
        "대한당뇨병학회 - 당뇨병이란",
        "https://www.diabetes.or.kr/general/info/info_01.php",
        "당뇨병은 인슐린이 부족하거나 제대로 작용하지 못해 혈액 속 포도당(혈당)이 높아지고 소변으로 넘쳐 나오는 질환입니다. 국내에는 이미 수백만 명의 당뇨병 환자가 있지만 상당수가 진단받지 못한 채 지내고 있어, 증상이 없어도 정기적인 검진이 중요합니다.",
        ("당뇨", "정의", "원인", "인슐린", "혈당"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-symptoms",
        "대한당뇨병학회 - 당뇨병의 증상",
        "https://www.diabetes.or.kr/general/info/info_01.php?con=3",
        "당뇨병의 대표 증상은 다뇨(소변량 증가), 다음(갈증으로 물을 많이 마심), 다식(공복감이 심해짐)의 '3다 증상'입니다. 다만 특별한 증상 없이 진행되는 경우도 많아, 증상이 없다고 안심하기보다 정기 검진으로 조기에 확인하는 것이 중요합니다.",
        ("당뇨", "증상", "다뇨", "다음", "다식"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-diagnosis",
        "대한당뇨병학회 - 당뇨병 진단기준",
        "https://www.diabetes.or.kr/general/info/info_01.php?con=5",
        "당뇨병은 공복혈당 126mg/dL 이상, 75g 경구당부하검사 2시간 후 혈당 200mg/dL 이상, 당화혈색소 6.5% 이상 중 하나를 만족하면 진단됩니다. 정확한 확진을 위해서는 의료기관에서의 검사와 재확인이 필요합니다.",
        ("당뇨", "진단", "진단기준", "공복혈당", "당화혈색소"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-type1",
        "대한당뇨병학회 - 제1형 당뇨병",
        "https://www.diabetes.or.kr/general/info/info_04.php",
        "제1형 당뇨병은 자가면역이나 바이러스 감염 등으로 췌장의 베타세포가 파괴되어 인슐린이 거의 분비되지 않는 상태로, 주로 소아·청소년기에 발생하며 인슐린 주사 치료가 반드시 필요합니다. 생활습관 교정만으로 조절되는 제2형 당뇨병과는 관리 방법이 다릅니다.",
        ("당뇨", "제1형", "소아당뇨", "인슐린"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-treatment-goals",
        "대한당뇨병학회 - 당뇨병 관리 목표수치",
        "https://www.diabetes.or.kr/general/info/treat/treat_01.php",
        "당뇨병 관리 목표는 식전 혈당 80~130mg/dL, 식후 2시간 혈당 180mg/dL 미만, 당화혈색소 6.5% 미만이며, 혈압은 130/80mmHg 미만, LDL 콜레스테롤은 100mg/dL 미만으로 유지하는 것이 권장됩니다.",
        ("당뇨", "혈당", "목표", "목표수치", "당화혈색소", "혈압", "콜레스테롤"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-hypoglycemia",
        "대한당뇨병학회 - 저혈당 대처법",
        "https://www.diabetes.or.kr/general/info/treat/treat_03.php",
        "저혈당은 혈당이 70mg/dL 이하로 떨어져 식은땀, 떨림, 심한 공복감, 어지럼 등이 나타나는 상태입니다. 이런 증상이 있으면 즉시 혈당을 확인하고 사탕이나 주스처럼 흡수가 빠른 당질을 15~20g 섭취한 뒤 15분 후에도 증상이 계속되면 다시 섭취하며, 의식이 흐려지는 등 심한 경우에는 억지로 먹이지 말고 즉시 119에 연락해야 합니다.",
        ("당뇨", "저혈당", "대처법", "혈당"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-footcare",
        "대한당뇨병학회 - 당뇨병 발관리",
        "https://www.diabetes.or.kr/general/info/treat/treat_05.php",
        "당뇨병으로 신경·혈관 합병증이 생기면 발에 상처가 잘 생기고 잘 낫지 않으므로, 매일 따뜻한 물로 씻고 발가락 사이까지 잘 말리며 밝은 곳에서 발 상태를 살피는 것이 중요합니다. 맨발로 다니거나 뜨거운 물·전열기구를 직접 대는 것은 피하고, 굽이 낮고 발볼이 넉넉한 신발과 순면 양말을 착용하는 것이 좋습니다.",
        ("당뇨", "발관리", "족부병증", "합병증"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-gestational",
        "대한당뇨병학회 - 임신성 당뇨병",
        "https://www.diabetes.or.kr/general/info/info_05.php",
        "임신성 당뇨병은 원래 당뇨병이 없던 사람이 임신 중, 주로 임신 20주 이후에 처음 혈당이 높아지는 경우로, 비만·당뇨 가족력·과거 임신성 당뇨병 경험이 있으면 위험이 높아집니다. 우선 식사·운동요법으로 관리하고 목표 혈당에 도달하지 못하면 인슐린 치료를 시작하며, 출산 후에는 대부분 정상 혈당으로 돌아옵니다.",
        ("당뇨", "임신성당뇨", "임신", "출산"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-stress",
        "대한당뇨병학회 - 당뇨병과 스트레스",
        "https://www.diabetes.or.kr/general/info/info_08.php",
        "스트레스를 받으면 혈당을 높이는 호르몬(에피네프린, 코르티솔)이 분비되어 혈당이 오르고, 이는 다시 스트레스로 이어지는 악순환을 만들 수 있습니다. 식사 시간 관리나 합병증에 대한 걱정처럼 당뇨병 관리 자체가 스트레스 요인이 될 수 있으므로, 스트레스를 관리 가능한 것으로 받아들이고 대처 방법을 찾는 것이 혈당 관리에도 도움이 됩니다.",
        ("당뇨", "스트레스", "혈당", "정신건강"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "kda-guideline-screening",
        "Diabetes & Metabolism Journal - 2023 당뇨병 진료지침(선별검사 대상)",
        "https://e-dmj.org/journal/view.php?number=2862",
        "대한당뇨병학회의 2023년 당뇨병 진료지침은 35세 이상 모든 성인과, 19세 이상이라도 비만·고혈압·대사증후군·당뇨병 가족력·복부비만(허리둘레 남성 90cm·여성 85cm 이상) 같은 위험요인이 있으면 당뇨병 선별검사를 받도록 권고합니다. 전당뇨병은 공복혈당 100~125mg/dL, 경구당부하검사 2시간 혈당 140~199mg/dL, 당화혈색소 5.7~6.4% 중 하나에 해당하면 진단됩니다.",
        ("당뇨", "전당뇨병", "선별검사", "위험인자", "복부비만"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "kda-guideline-glycemic-targets",
        "Diabetes & Metabolism Journal - 2023 당뇨병 진료지침(혈당조절 목표)",
        "https://e-dmj.org/journal/view.php?number=2862",
        "2023년 대한당뇨병학회 진료지침은 당화혈색소 목표를 제2형 당뇨병은 6.5% 미만, 제1형 당뇨병은 7.0% 미만으로 제시하되, 고령이거나 합병증이 심하거나 기대여명이 짧은 경우에는 저혈당 위험과 삶의 질을 고려해 목표를 상향 조정할 수 있다고 권고합니다.",
        ("당뇨", "당화혈색소", "혈당목표", "고령자"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "kda-guideline-cgm",
        "Diabetes & Metabolism Journal - 2023 당뇨병 진료지침(지속혈당측정 목표)",
        "https://e-dmj.org/journal/view.php?number=2862",
        "지속혈당측정(CGM)을 사용하는 경우 목표범위 시간(70~180mg/dL, TIR)을 70% 이상, 목표 미만 시간(TBR)을 4% 미만, 심각한 저혈당(54mg/dL 미만) 시간을 1% 미만으로 유지하는 것이 2023년 진료지침의 권고 목표입니다. 특히 제1형 당뇨병 환자에게는 저혈당 위험을 줄이기 위해 CGM 사용이 권장됩니다.",
        ("당뇨", "지속혈당측정", "연속혈당측정", "목표범위", "혈당변동", "저혈당"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "dbpia-prediabetes-young-adults",
        "Journal of Nutrition and Health(2025) - 당뇨병전단계 청년의 식습관·생활습관 비교연구",
        "https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE12452583",
        "국내 청년 대상 연구에 따르면 당뇨병전단계 집단은 건강한 집단보다 정기적인 혈당 관리, 운동 시간, 수면 시간, 체중조절 시도가 부족했고 하루 평균 음주량도 더 많았습니다. 특히 20~30대에서는 식사의 균형과 절제 같은 식습관 차이가 뚜렷했던 반면 40대에서는 그 차이가 크지 않아, 연령대에 맞는 생활습관 개선이 당뇨병전단계 관리에 중요하다는 점을 보여줍니다.",
        ("당뇨", "전당뇨병", "청년", "음주", "수면"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "dbpia-htn-diabetes-lifestyle",
        "대한가정의학회(2025) - 고혈압과 2형 당뇨병의 생활습관 관리",
        "https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE12532852",
        "가정의학과 리뷰 논문에 따르면 고혈압에는 저염식과 채소·과일을 통한 칼륨 섭취, 중강도 유산소 운동이 혈압을 낮추는 데 도움이 되고, 당뇨병에는 정제 탄수화물을 줄이고 식이섬유 섭취를 늘리는 것이 혈당 조절에 도움이 됩니다. 유산소 운동과 저항운동은 체중 감량 여부와 관계없이 당화혈색소를 낮추는 효과가 있으며, 금연과 절주도 심혈관질환·대사질환 위험을 낮추는 데 중요합니다.",
        ("당뇨", "고혈압", "저염식", "식이섬유", "저항운동", "금연"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "dbpia-cgm-exercise-pilot",
        "의공학회지(2026) - 연속혈당측정 기반 운동 유형별 식후 혈당 반응 파일럿 연구",
        "https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE12706453",
        "과체중 성인을 대상으로 한 소규모 파일럿 연구에서는 식후 30분 뒤 유산소·저항·고강도인터벌(HIIT)·필라테스 중 어떤 운동을 하더라도 식후 혈당 상승이 줄어드는 경향이 있었지만, 운동 강도가 세다고 혈당 조절 효과가 더 크지는 않았고 사람마다 가장 효과적인 운동 종류가 달랐습니다. 연구진은 연속혈당측정(CGM)으로 자신에게 맞는 운동을 찾는 것이 도움이 될 수 있다고 제안합니다(소규모 파일럿 연구로 통계적 유의성은 확인되지 않음).",
        ("당뇨", "연속혈당측정", "운동", "식후혈당"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-smoking",
        "대한당뇨병학회 - 당뇨병과 흡연",
        "https://www.diabetes.or.kr/general/info/treat/treat_04.php",
        "담배는 폐암 외에도 인후암·구강암·식도암과 관련이 있고, 니코틴은 혈관을 수축시켜 심장질환과 뇌혈관질환 위험을 높입니다. 당뇨병 환자에게 흡연은 동맥경화와 혈관 합병증을 악화시키는 중요한 위험요소이므로, 특히 합병증이 있다면 금연이 필수적입니다.",
        ("당뇨", "흡연", "담배", "금연", "동맥경화"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-checkup-schedule",
        "대한당뇨병학회 - 당뇨병 정기검진 항목과 주기",
        "https://www.diabetes.or.kr/general/info/treat/treat_04.php",
        "당뇨병 합병증을 조기에 발견하려면 매 외래 방문 때 혈당 검사와 혈압 측정을, 2~3개월마다 당화혈색소 검사를, 매년 간기능·지질·안과·신장기능·심전도 검사를 받는 것이 좋습니다.",
        ("당뇨", "정기검진", "검사주기", "안과검진", "신장기능"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "diabetes-or-kr-mind",
        "대한당뇨병학회 - 당뇨병과 나의 마음",
        "https://www.diabetes.or.kr/general/info/info_06.php",
        "당뇨병을 진단받으면 부정, 두려움, 분노, 죄책감, 우울, 수용의 감정을 차례로 겪는 것이 자연스러운 과정입니다. 우울감은 완치되지 않는다는 절망에서 비롯될 수 있는데, 이런 감정을 억누르기보다 인정하고 받아들이는 것이 당뇨병 관리에 도움이 되며, 이 과정은 환자 본인뿐 아니라 가족에게도 함께 나타날 수 있습니다.",
        ("당뇨", "마음", "우울", "심리", "수용"),
        checked_at="2026-09-10",
    ),
    KnowledgeDocument(
        "who-activity",
        "WHO Guidelines on physical activity and sedentary behaviour",
        "https://www.who.int/publications/i/item/9789240015128",
        "성인은 건강 상태와 능력에 맞는 신체활동을 하고, 앉아 있는 시간을 줄이는 것이 권장됩니다.",
        ("운동", "걷기", "활동", "앉기", "신체활동"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "cdc-prevent-t2",
        "CDC PreventT2 Curriculum",
        "https://www.cdc.gov/diabetes-prevention/php/lifestyle-change-resources/t2-curriculum.html",
        "작고 구체적인 목표를 기록하고 실패 원인을 살펴 목표를 조정하는 방식은 생활습관 실천에 도움이 됩니다.",
        ("챌린지", "목표", "기록", "실패", "습관"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "kdca-hypertension",
        "질병관리청 국가건강정보포털 - 고혈압",
        "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=5300",
        "혈압은 올바른 방법으로 반복 측정하고, 높은 수치가 확인되면 의료진과 상담해야 합니다.",
        ("혈압", "고혈압", "측정", "상담"),
        checked_at="2026-09-09",
    ),
    KnowledgeDocument(
        "kdca-hyperglycemia-emergency",
        "질병관리청 국가건강정보포털 - 고혈당",
        "https://health.kdca.go.kr/healthinfo/biz/health/gnrlzHealthInfo/gnrlzHealthInfo/gnrlzHealthInfoView.do?cntnts_sn=5304",
        "고혈당이 미진단 상태로 의심되면 의료기관에서 확인해야 하며, 의식 변화 등 응급상황이 나타나면 즉시 응급조치가 필요합니다.",
        ("고혈당", "응급", "의식", "저혈당", "쇼크"),
        checked_at="2026-08-19",
    ),
)

# 지혜의 샘 하이브리드 검색용 색인. APPROVED_DOCUMENTS는 프로세스 실행 중 바뀌지 않으므로
# 모듈 로드 시 한 번만 문장 단위 청크로 쪼개 둔다.
ALL_CHUNKS: tuple[Chunk, ...] = tuple(
    chunk for document in APPROVED_DOCUMENTS for chunk in split_into_chunks(document.document_id, document.text)
)
KEYWORDS_BY_DOCUMENT: dict[str, tuple[str, ...]] = {
    document.document_id: document.keywords for document in APPROVED_DOCUMENTS
}
DOCUMENTS_BY_ID: dict[str, KnowledgeDocument] = {document.document_id: document for document in APPROVED_DOCUMENTS}

EMERGENCY_SYMPTOM_PATTERN = re.compile(
    r"의식(을|이)?\s*(잃|없|흐려|저하)"
    r"|정신(을|이)?\s*(잃|없)"
    r"|숨(을|이)?\s*(못\s*쉬|쉬기\s*힘들|가쁘|막히)"
    r"|호흡\s*곤란"
    r"|가슴\s*(통증|답답|조이)"
    r"|흉통"
    r"|(팔|다리|얼굴)\s*마비|마비.{0,4}(팔|다리|얼굴)|반신\s*마비|편측\s*마비"
    r"|경련|발작"
    r"|말이\s*어눌|발음이\s*이상"
    r"|심한\s*어지럼|어지러워서\s*(쓰러|주저앉)|쓰러졌"
    r"|저혈당\s*쇼크|혼수(상태)?"
    r"|응급실|119"
)

MEDICATION_PATTERN = re.compile(
    r"(약|복용|용량|처방).*(시작|중단|끊|늘|줄|변경)|(시작|중단|끊|늘|줄|변경).*(약|복용|용량|처방)"
)


def _citation(document: KnowledgeDocument) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "title": document.title,
        "url": document.url,
        "checked_at": document.checked_at,
    }


def _retrieval_method() -> str:
    if config.HEALTH_EDUCATION_RETRIEVER == "qdrant":
        return "qdrant_dense_hnsw_v1"
    return "hybrid_keyword_embedding_v2"


def _insufficient_evidence() -> dict[str, object]:
    return {
        "answer": "승인된 자료에서 질문과 충분히 가까운 근거를 찾지 못했습니다. 질문을 운동·식사·혈압·생활습관처럼 구체적으로 적어 주세요.",
        "answer_status": "insufficient_evidence",
        "citations": [],
        "retrieval_method": _retrieval_method(),
    }


async def _hybrid_answer(question: str) -> dict[str, object]:
    """②~⑥단계: 하이브리드 검색 → 관련도 검사 → 재정렬 → LLM 제한 생성 → 문장별 출처 검사."""
    try:
        embedding_provider = get_embedding_provider()
        if config.HEALTH_EDUCATION_RETRIEVER == "memory":
            scored = await hybrid_search(
                question,
                chunks=ALL_CHUNKS,
                keyword_lookup=KEYWORDS_BY_DOCUMENT,
                embedding_provider=embedding_provider,
            )
        elif config.HEALTH_EDUCATION_RETRIEVER == "qdrant":
            scored = await qdrant_search(question, embedding_provider=embedding_provider)
        else:
            raise QdrantError(f"지원하지 않는 RAG retriever입니다: {config.HEALTH_EDUCATION_RETRIEVER}")
    except (EmbeddingError, QdrantError):
        return {
            "answer": "지금은 근거를 검색하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "answer_status": "insufficient_evidence",
            "citations": [],
            "retrieval_method": _retrieval_method(),
        }
    top_score = scored[0].combined_score if scored else 0.0
    if top_score < config.HEALTH_EDUCATION_RELEVANCE_THRESHOLD:
        return _insufficient_evidence()

    selected_chunks = top_chunks(scored)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in selected_chunks}

    try:
        generated = await get_generation_provider().generate(question, selected_chunks)
    except AnswerGenerationError:
        # 프론트(normalizeHealthEducationResult)가 grounded/insufficient_evidence/medical_safety_refusal
        # 세 가지 answer_status만 허용 목록으로 처리하므로(그 외 값은 fail-closed로 에러 처리됨),
        # 새 상태값을 만들지 않고 insufficient_evidence로 안전하게 폴백한다.
        return {
            "answer": "지금은 답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "answer_status": "insufficient_evidence",
            "citations": [],
            "retrieval_method": _retrieval_method(),
        }

    verified_sentences = verify_sentences(generated, chunks_by_id)
    if not verified_sentences:
        return _insufficient_evidence()

    document_ids = cited_document_ids(generated, chunks_by_id, verified_sentences)
    document_ids = document_ids[: config.HEALTH_EDUCATION_MAX_CITATIONS]
    citations = [_citation(DOCUMENTS_BY_ID[document_id]) for document_id in document_ids]

    return {
        "answer": " ".join(verified_sentences),
        "answer_status": "grounded",
        "citations": citations,
        "retrieval_method": _retrieval_method(),
    }


async def answer_with_sources(question: str) -> dict[str, object]:
    normalized = question.strip().casefold()

    if EMERGENCY_SYMPTOM_PATTERN.search(normalized):
        emergency_doc = next(doc for doc in APPROVED_DOCUMENTS if doc.document_id == "kdca-hyperglycemia-emergency")
        return {
            "answer": (
                "가슴 통증, 의식 저하, 심한 호흡곤란, 마비, 경련 같은 증상은 응급상황일 수 있습니다. "
                "이 서비스의 답변을 기다리지 말고 지금 바로 119에 연락하거나 가까운 응급실을 방문하세요."
            ),
            "answer_status": "emergency_redirect",
            "citations": [_citation(emergency_doc)],
            "retrieval_method": "approved_document_keyword_v1",
        }

    if MEDICATION_PATTERN.search(normalized):
        return {
            "answer": "약의 시작·중단·용량 변경은 이 서비스가 안내할 수 없습니다. 처방한 의료진이나 약사와 상의해 주세요.",
            "answer_status": "medical_safety_refusal",
            "citations": [],
            "retrieval_method": "approved_document_keyword_v1",
        }

    return await _hybrid_answer(question)
