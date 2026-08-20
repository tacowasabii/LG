# Family Memory Graph Synthetic Dataset v1.0

Family Memory Graph MVP 시연용 완전 가상(synthetic) 가족 데이터입니다.

- photos/: 24 JPG, 원본 해상도 유지, JPEG quality 96, EXIF 삽입
- metadata/media.json: 사진별 시간·GPS·인물·장면·태그 Ground Truth
- metadata/events.json: 8개 가족 이벤트
- metadata/persons.json: 가족 5명 (P01~P05)
- metadata/memories.json: 사건별 회상 메모
- metadata/media.csv, events.csv: ingestion용 CSV

EXIF에는 DateTimeOriginal/DateTimeDigitized, GPS, Make= SyntheticCam, Model=FMG-YYYY, Software, ImageDescription가 포함됩니다. 날짜와 위치는 모두 데모 시나리오용 synthetic ground truth입니다.
