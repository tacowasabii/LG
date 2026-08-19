# Family Memory Graph Synthetic Dataset v1.0

Family Memory Graph MVP 시연용 완전 가상(synthetic) 가족 데이터입니다.

- photos/: 24 JPG, 원본 해상도 유지, JPEG quality 96, EXIF 삽입
- metadata/media.json: 사진별 시간·GPS·인물·장면·태그 Ground Truth
- metadata/events.json: 8개 가족 이벤트
- metadata/persons.json: 인물 7명 (가족 5 + 친구 1 + 연인 1)
  - P06 최민지(친구)·P07 이준호(연인)은 합성 사진에 등장하지 않습니다.
    관계 스키마가 가족에 한정되지 않음을 보이기 위해 추가했고, 사진의 인물
    라벨은 조작하지 않았습니다.
- metadata/memories.json: 사건별 회상 메모
- metadata/media.csv, events.csv: ingestion용 CSV

EXIF에는 DateTimeOriginal/DateTimeDigitized, GPS, Make= SyntheticCam, Model=FMG-YYYY, Software, ImageDescription가 포함됩니다. 날짜와 위치는 모두 데모 시나리오용 synthetic ground truth입니다.
