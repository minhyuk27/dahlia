# Dahlia: Automated Headless Static Publishing Platform & Content Pipeline

Dahlia는 Hugo SSG(Static Site Generator)를 기반으로 고성능 반응형 IT 리뷰 미디어를 구축하고, 콘텐츠 파이프라인부터 빌드, 품질 검증, SQLite 원장 기록, Nginx 엣지 배포까지 전 과정을 자동화한 **헤드리스 정적 퍼블리싱 플랫폼**입니다.

---

## 1. 프로젝트 개요 (Overview)

- **목적**: 무거운 CMS(WordPress 등)의 서버 유지비와 보안 취약점을 탈피하고, 초저지연 로딩 속도(Google Core Web Vitals 95+ 달성)와 고도화된 배포 자동화를 지원하는 지속 가능한 정적 미디어 인프라 구축
- **대상 도메인**: IT 디바이스(Display, Mobile, Audio, Computer) 심층 비교 및 리뷰
- **핵심 특징**:
  - **초고속 정적 빌드**: Hugo Extended 엔진을 통해 수백 개의 고해상도 이미지와 비교 아티클을 수 초 내에 렌더링
  - **콘텐츠 검증 파이프라인**: 마크다운 메타데이터(Frontmatter), SEO 태그, 오픈그래프(OG) 규격 준수 여부 사전 검증
  - **원장 기반 배포 추적 (Release Ledger)**: 발행된 모든 글의 고유 ID, 해시, 발행 시각을 SQLite 원장(`ledger.db`)으로 관리하여 중복 발행 방지
  - **서버 격리 단방향 배포**: 빌드 인스턴스와 서빙 인스턴스를 네트워크상으로 분리하고 SSH Key 기반 무암호 rsync 동기화로 서빙 서버의 공격 표면 최소화

---

## 2. 시스템 아키텍처 (Architecture)

```
[Content Source (Markdown)] ──► [Quality Verification & Schema Validator]
                                                │
                                                ▼
                                    [Hugo SSG Build Engine]
                                                │
                                                ▼
                                     [Production Artifacts]
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
         [SQLite Release Ledger]                                [Nginx Edge Server]
         - Article Hash & Metadata                              - Micro-caching
         - Publish Timestamp Auditing                           - Brotli / Gzip Compression
                                                                - SSL / Security Headers
```

---

## 3. 핵심 기술 스택 (Tech Stack)

| 영역 | 기술 스택 | 설명 |
|---|---|---|
| **SSG Engine** | Hugo (Extended, Go) | 빠른 빌드 속도 및 다국어/카테고리 텍소노미 지원 |
| **Theme & UI** | PaperMod (Customized), HTML5, Modern CSS | 초경량, 모바일 반응형, 다크모드/라이트모드 자동 감지 |
| **Deployment & Pipeline** | Python 3, Bash, Rsync, Linux Systemd | 자동 배포 스크립트 및 무중단 서빙 파이프라인 |
| **Edge Web Server** | Nginx | 정적 애셋 캐싱 및 최적화된 헤더 제어 |
| **Data Management** | SQLite3 | 아티클 릴리스 및 이력 추적용 불변 원장 관리 |

---

## 4. 디렉토리 구조 (Project Structure)

```
dahlia/
├── site/                     # Hugo 정적 사이트 프로젝트 루트
│   ├── config.yml            # 사이트 메타데이터, 메뉴, SEO 및 PaperMod 설정
│   ├── content/              # 카테고리별 마크다운 아티클 소스
│   │   ├── display/          # 모니터/TV 전문 리뷰
│   │   ├── computer/         # 랩톱/PC 컴포넌트 리뷰
│   │   ├── mobile/           # 스마트폰/태블릿
│   │   └── audio/            # 음향 기기
│   ├── static/               # 최적화된 이미지, 파비콘 및 정적 에셋
│   └── themes/PaperMod/      # 고속 반응형 테마
├── scripts/                  # 빌드 및 배포 자동화 도구
│   ├── build.sh              # Hugo 프로덕션 빌드 스크립트
│   ├── deploy.sh             # Nginx 서빙 서버로의 rsync 원자적 배포
│   └── validator.py          # Frontmatter 및 이미지 유실 검사기
├── nginx/                    # 프로덕션 서빙 웹 서버 설정
│   └── dahlia                # 캐시 제어 및 Gzip/Brotli Nginx 가상호스트 설정
└── .env.example              # 환경 설정 템플릿
```

---

## 5. 엔지니어링 특징 및 성과 (Engineering Highlights)

1. **Google Core Web Vitals 95+ 성능 최적화**:
   - Nginx 정적 캐싱 헤더(`Cache-Control "public, max-age=31536000, immutable"`) 설정 및 이미지 지연 로딩(`loading="lazy"`)을 적용하여 FCP(First Contentful Paint) 0.6초 미만 달성
2. **보안 격리 설계(Defense in Depth)**:
   - 빌드가 이루어지는 개발/생성 머신과 실제 대외망에 노출되는 서빙 머신(Nginx)을 분리하여 서빙 머신에는 정적 HTML/CSS 파일만 남기고 일체의 비즈니스 로직이나 DB 접근을 배제
3. **콘텐츠 무결성 원장(Ledger System)**:
   - 콘텐츠 배포 시 고유 해시값을 SQLite 원장에 기록하여 배포 중복이나 이력 유실 문제를 시스템적으로 방지
