# 기존 서버용 스키마 변경분

새 서버는 상위 폴더의 정본(`mk2_*.sql`)만으로 최신 스키마가 선다. 이 폴더에는 **이미 운영 중인 DB** 에 같은 변경을
반영하는 `ALTER` 류 파일을 `YYYYMMDD_<주제>.sql`(TimescaleDB 용은 `_tsdb` 접미사)로 둔다. 재실행해도 안전하게 쓴다.

절차: [`docs/deployment/database.md` §4](../../../../docs/deployment/database.md#4-스키마-변경-절차-마이그레이션)
