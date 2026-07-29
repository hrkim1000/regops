# Cosmetic Regulation Regions — scope reference

RegOps 화장품 도메인의 대상 규제권역은 **4개로 고정**되어 있다. 각 권역의 확정 소스 목록은 `../../import-source-map.md`, 권역별 raw catalog는 형제 디렉터리에 있다.

## In scope (4)

| # | 규제권역 | Raw catalog |
| - | -------- | ----------- |
| 1 | 대한민국 MFDS | `../mfds/mfds-cosmetic-regulation-source.md` |
| 2 | 미국 FDA | `../fda/fda-cosmetic-regulation-source.md` |
| 3 | EU EC / CPNP | `../eu/eu-cosmetic-regulation-source.md` |
| 4 | 중국 NMPA | `../china/china-cosmetic-regulation-source.md` |

## Out of scope

아래 권역은 **범위 밖**이다. '나중에 확장'이 아니라, 범위 결정을 다시 하기 전까지 모델링·수집·커넥터 작성을 하지 않는다 — [RegOps.md](../../RegOps.md) § Scope.

* 일본 MHLW/PMDA
* ASEAN Cosmetic Directive (ACD)
* 영국 UK OPSS / SCPN
* 캐나다 Health Canada
* 호주 NICNAS/AICIS
* 브라질 ANVISA

> 이 목록은 범위를 다시 논의할 때의 후보를 기록해 둔 것이지 로드맵이 아니다. 글로벌 커버리지를 목표로 삼는 순간 8개 셀의 탐지 커버리지 ≥ 95% 게이트가 측정 불가능해진다.
