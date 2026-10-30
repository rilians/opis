<div align="center">
  <img src="docs/assets/opis-mark.svg" width="72" height="72" alt="Logo Opis">
  <h1>Opis</h1>
  <p><strong>API Health Monitor &amp; Incident Reporter</strong></p>
  <p>Pantau ketersediaan API, tangani insiden, dan pahami performa layanan dalam satu workspace.</p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&amp;logoColor=white" alt="Python 3.13">
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&amp;logoColor=white" alt="FastAPI 0.115">
    <img src="https://img.shields.io/badge/HTTPX-0.28-4051B5" alt="HTTPX 0.28">
    <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&amp;logoColor=white" alt="PostgreSQL 16 pada Docker Compose">
    <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&amp;logoColor=white" alt="Docker Compose">
    <img src="https://img.shields.io/badge/pytest-8.3-0A9EDC?logo=pytest&amp;logoColor=white" alt="pytest 8.3">
  </p>
  <p>
    <a href="#fitur-utama">Fitur</a> &nbsp;·&nbsp;
    <a href="#galeri-antarmuka">Galeri</a> &nbsp;·&nbsp;
    <a href="#mulai-cepat">Mulai cepat</a> &nbsp;·&nbsp;
    <a href="#pengujian">Pengujian</a> &nbsp;·&nbsp;
    <a href="#keamanan-dan-batasan-operasional">Keamanan</a>
  </p>
</div>

---

Opis adalah aplikasi pemantauan API berbasis **Python dan FastAPI**. Aplikasi menjalankan pemeriksaan berkala menggunakan HTTPX, mencatat hasil dan insiden, lalu menyajikannya melalui dashboard berbahasa Indonesia. PostgreSQL digunakan pada Docker Compose; SQLite tersedia untuk menjalankan aplikasi secara lokal dan untuk pengujian.

> [!IMPORTANT]
> Screenshot dalam README menggunakan **data demo simulasi**, bukan status layanan sungguhan. Endpoint yang Anda tambahkan sendiri diperiksa secara nyata.

[![Dashboard overview Opis: metrik ketersediaan, grafik respons, kondisi endpoint, dan insiden terbaru](docs/screenshots/01-overview.png)](docs/screenshots/01-overview.png)

<sub>Dashboard overview · Klik gambar untuk melihat ukuran penuh.</sub>

## Fitur utama

| Fitur | Yang dapat dilakukan |
| --- | --- |
| **Pemantauan endpoint** | Pemeriksaan `GET`/`HEAD` secara berkala atau manual; atur interval, timeout, dan status HTTP yang diharapkan. |
| **Status dan waktu respons** | Simpan hasil pemeriksaan, kode HTTP, durasi hingga header respons diterima, dan jenis kesalahan. |
| **Insiden otomatis** | Buka dan pulihkan insiden berdasarkan ambang kegagalan dan keberhasilan berturut-turut. |
| **Notifikasi** | Tampilkan insiden di aplikasi dan kirim webhook opsional saat insiden dibuka atau pulih. |
| **Analisis insiden** | Lihat bukti dan kronologi, baca saran investigasi, serta simpan catatan analisis akar masalah. |
| **Laporan SLA** | Bandingkan ketersediaan berbasis sampel dengan target, lihat metrik per endpoint, dan ekspor CSV. |
| **Pengujian terisolasi** | Jalankan pytest dengan respons HTTP palsu menggunakan SQLite atau PostgreSQL; tersedia smoke test browser opsional. |

## Galeri antarmuka

Semua gambar berikut adalah tangkapan layar aplikasi, diambil menggunakan dataset demo terisolasi. **Klik gambar** untuk membuka ukuran penuh.

### Pemantauan endpoint

| Daftar endpoint | Tambah endpoint |
| :---: | :---: |
| [![Daftar endpoint dengan status, interval, uptime, dan pemeriksaan terakhir](docs/screenshots/02-endpoints.png)](docs/screenshots/02-endpoints.png) | [![Form tambah endpoint dengan pengaturan interval, timeout, dan ambang insiden](docs/screenshots/03-add-endpoint.png)](docs/screenshots/03-add-endpoint.png) |
| Filter status, pencarian, dan tindakan endpoint. | Konfigurasi pemeriksaan dan ambang per layanan. |

| Detail endpoint | Riwayat insiden |
| :---: | :---: |
| [![Detail endpoint dengan konfigurasi dan riwayat pemeriksaan](docs/screenshots/04-endpoint-detail.png)](docs/screenshots/04-endpoint-detail.png) | [![Daftar insiden aktif dan yang telah pulih](docs/screenshots/05-incidents.png)](docs/screenshots/05-incidents.png) |
| Hasil pemeriksaan terbaru dan konfigurasi. | Lihat insiden aktif, pulih, dan ditutup. |

### Analisis dan pelaporan

| Detail dan investigasi insiden | Laporan SLA |
| :---: | :---: |
| [![Detail insiden dengan ringkasan, bukti, dan catatan investigasi](docs/screenshots/06-incident-detail.png)](docs/screenshots/06-incident-detail.png) | [![Laporan SLA gabungan dan per endpoint](docs/screenshots/07-sla-report.png)](docs/screenshots/07-sla-report.png) |
| Ringkasan berbasis bukti dan contoh catatan investigasi. | Ketersediaan berbasis sampel dan ekspor CSV. |

### Pengaturan workspace

| Notifikasi dan webhook | Pengaturan |
| :---: | :---: |
| [![Halaman notifikasi dan konfigurasi webhook](docs/screenshots/08-notifications.png)](docs/screenshots/08-notifications.png) | [![Pengaturan target SLA, scheduler, keamanan, dan data demo](docs/screenshots/09-settings.png)](docs/screenshots/09-settings.png) |
| Kelola webhook dan tinjau riwayat pengiriman. | Atur target SLA dan kelola data demo. |

### Tampilan seluler

<a href="docs/screenshots/10-mobile-overview.png"><img src="docs/screenshots/10-mobile-overview.png" width="290" alt="Dashboard Opis pada layar seluler"></a>

<sub>Dashboard responsif pada layar seluler.</sub>

## Teknologi dan arsitektur

| Lapisan | Teknologi |
| --- | --- |
| Backend dan API | Python 3.13, FastAPI, Uvicorn |
| Pemeriksaan dan webhook | HTTPX |
| Penyimpanan | SQLAlchemy, PostgreSQL; SQLite untuk lokal/pengujian |
| Antarmuka | HTML, CSS, JavaScript; disajikan oleh FastAPI tanpa build frontend |
| Pengujian | pytest, HTTPX `MockTransport`, Playwright opsional |
| Deployment lokal | Docker dan Docker Compose |

```text
Browser / dashboard
       │  REST API
       ▼
FastAPI + scheduler ── HTTPX ──► Endpoint API yang dipantau
       │             └─ HTTPX ──► Webhook opsional
       ▼
PostgreSQL (Compose) / SQLite (lokal)
       │
       └── Endpoint, hasil pemeriksaan, insiden, konfigurasi, pengiriman webhook
```

Scheduler berjalan di dalam proses FastAPI. Untuk batasan penggunaan satu worker/replika, lihat [Keamanan dan batasan operasional](#keamanan-dan-batasan-operasional).

## Mulai cepat

### Docker + PostgreSQL

**Prasyarat:** Docker Engine dan Docker Compose v2.

Dari direktori proyek:

```bash
cp .env.example .env
# Ganti POSTGRES_PASSWORD di .env dengan sandi alfanumerik unik.
docker compose up --build -d
```

| Akses | Alamat |
| --- | --- |
| Dashboard | [http://localhost:8000](http://localhost:8000) |
| Dokumentasi API interaktif | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Pemeriksaan kesehatan aplikasi | [http://localhost:8000/api/health](http://localhost:8000/api/health) |

Port aplikasi dipublikasikan hanya pada `127.0.0.1` host secara default. PostgreSQL tidak dipublikasikan ke host, dan volume `opis_db` menyimpan data database.

```bash
docker compose logs -f app       # melihat log aplikasi
docker compose down              # menghentikan container; data tetap tersimpan
# docker compose down -v         # HATI-HATI: menghapus volume dan seluruh data database
```

Kata sandi Compose dimasukkan ke URL koneksi: gunakan karakter alfanumerik, atau lakukan URL-encoding jika menyusun URL sendiri. Mengubah sandi di `.env` setelah volume dibuat **tidak** otomatis mengubah sandi database yang sudah ada.

### Menjalankan lokal tanpa Docker

Gunakan Python 3.13. File lock dependency ditujukan untuk Linux/Python 3.13, sama seperti image Docker.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Tanpa `OPIS_DATABASE_URL`, aplikasi menggunakan SQLite `opis.db` di direktori kerja. Untuk PostgreSQL lokal:

```bash
export OPIS_DATABASE_URL='postgresql+psycopg://opis:password@localhost:5432/opis'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Skema dibuat saat startup jika belum ada. `create_all` **bukan** sistem migrasi; gunakan migrasi terkelola sebelum mengubah skema pada instalasi yang menyimpan data penting.

## Cara menggunakan

1. **Tambahkan endpoint.** Buka menu **Endpoint → Tambah endpoint**, lalu isi URL, metode, status HTTP yang diharapkan, interval, timeout, dan ambang insiden/pemulihan.
2. **Pantau pemeriksaan.** Scheduler menjadwalkan pemeriksaan pertama segera. Gunakan **Periksa sekarang** untuk menjalankan pemeriksaan manual pada endpoint nyata yang aktif.
3. **Investigasi insiden.** Ketika ambang kegagalan tercapai, buka detail insiden untuk melihat bukti, kronologi, saran investigasi, dan menyimpan catatan.
4. **Atur notifikasi.** Pada menu **Notifikasi**, opsional konfigurasikan URL webhook dan gunakan **Kirim tes**.
5. **Tinjau SLA.** Pilih periode pada **Laporan SLA**, bandingkan dengan target, lalu ekspor laporan CSV bila diperlukan.

### Data demo

Pada database kosong dengan `OPIS_DEMO_DATA=true`, Opis membuat lima endpoint dan riwayat sintetis. Seluruhnya diberi label **Demo**, tidak diperiksa oleh scheduler, dan tidak mengirim webhook. Data demo **ikut dihitung** dalam dashboard dan laporan sampai dihapus melalui **Pengaturan → Data demo**.

Seed dilakukan sekali; data demo yang dihapus tidak muncul kembali saat restart. Set `OPIS_DEMO_DATA=false` sebelum startup untuk memulai dengan workspace kosong.

### Perilaku pemeriksaan

- Status dianggap berhasil hanya jika kode HTTP **persis** sama dengan `expected_status`. Redirect tidak diikuti.
- Interval minimal adalah **30 detik**; timeout dapat diatur per endpoint.
- Opis menutup respons setelah menerima header tanpa mengunduh body. Waktu respons mencakup DNS dan koneksi hingga header atau kegagalan/timeout.
- Saat ini belum tersedia autentikasi header khusus, pemeriksaan isi body, atau metode selain `GET`/`HEAD`.

### Siklus insiden

```text
Gagal pertama ──► ambang gagal tercapai ──► insiden aktif
                                               │
                       ambang pulih tercapai ◄─┘
                                  │
                                  ▼
                           insiden pulih
```

Waktu kegagalan pertama dan waktu ambang terlampaui disimpan terpisah, bersama bukti pertama/terakhir dan jumlah pemeriksaan gagal. Menjeda endpoint tidak otomatis menutup insiden yang masih terbuka. Mengarsipkan endpoint atau mengubah URL, metode, status yang diharapkan, maupun timeout menutup insiden aktif dengan alasan khusus, **bukan** mengklaim layanan telah pulih. Riwayat endpoint yang diarsipkan tetap tersedia dalam laporan.

Saran pada ringkasan insiden adalah **petunjuk investigasi**, bukan diagnosis pasti. Penyebab sebenarnya perlu diverifikasi dan dapat dicatat secara manual.

### Metode SLA

```text
ketersediaan (%) = pemeriksaan berhasil / seluruh pemeriksaan × 100
```

Nilai gabungan dibobot berdasarkan jumlah pemeriksaan, sehingga endpoint dengan interval lebih pendek memiliki lebih banyak sampel. Periode tanpa pemeriksaan ditampilkan sebagai `—`, bukan 100%. Target dibandingkan sebelum pembulatan untuk tampilan.

Dashboard hanya memakai endpoint yang belum diarsipkan; laporan juga mencakup endpoint yang diarsipkan. Durasi insiden adalah estimasi dari pemeriksaan gagal pertama sampai pemulihan atau penutupan, dipotong pada batas periode. Insiden yang masih terbuka dihitung hingga saat ini.

> [!NOTE]
> SLA Opis berbasis **sampel**, bukan pengukuran uptime berbasis durasi. Jeda pemantauan dan gangguan yang terjadi di antara pemeriksaan dapat tidak tercatat.

## API dan webhook

Dokumentasi lengkap tersedia di [`/docs`](http://localhost:8000/docs) saat aplikasi berjalan. Beberapa rute utama:

| Metode | Rute | Fungsi |
| --- | --- | --- |
| `GET` | `/api/health` | Status aplikasi dan database. |
| `GET` | `/api/dashboard?period=24h` | Ringkasan dashboard. |
| `GET`, `POST` | `/api/endpoints` | Daftar atau tambah endpoint. |
| `POST` | `/api/endpoints/{id}/check` | Jalankan pemeriksaan manual. |
| `GET` | `/api/incidents` | Daftar insiden. |
| `GET`, `PATCH` | `/api/incidents/{id}` | Detail atau catatan investigasi insiden. |
| `GET` | `/api/reports/sla?period=7d` | Laporan SLA; tersedia juga `/api/reports/sla.csv`. |
| `PUT`, `POST` | `/api/alerts/config`, `/api/alerts/test` | Konfigurasi dan uji webhook. |

Contoh menambahkan endpoint melalui API:

```bash
curl -X POST http://localhost:8000/api/endpoints \
  -H 'Content-Type: application/json' \
  -d '{"name":"Example API","url":"https://example.com/","method":"GET","expected_status":200,"interval_seconds":60,"timeout_seconds":10,"failure_threshold":2,"recovery_threshold":1}'

curl http://localhost:8000/api/dashboard?period=24h
curl http://localhost:8000/api/incidents
curl 'http://localhost:8000/api/reports/sla?period=7d'
```

### Format webhook

Webhook dikirim sebagai `POST` dengan `Content-Type: application/json`; respons HTTP 2xx dianggap berhasil. Contoh struktur—objek `incident` juga memuat detail tambahan:

```json
{
  "event": "incident.opened",
  "source": "opis",
  "sent_at": "2026-10-30T01:00:00Z",
  "incident": {
    "id": 1,
    "endpoint_id": 1,
    "endpoint_name": "Example API",
    "status": "open",
    "first_error_type": "http_status",
    "first_status_code": 503,
    "failure_count": 2
  }
}
```

Peristiwa pemulihan bernama `incident.resolved`. Tombol tes mengirim peristiwa `test` dengan `incident: null`. Pengiriman bersifat **best-effort**, satu kali per transisi; kegagalannya tersimpan di menu Notifikasi. Belum ada retry otomatis, antrean persisten, atau tanda tangan webhook. Notifikasi dalam aplikasi tetap tersedia tanpa webhook.

## Konfigurasi lingkungan

| Variabel | Default | Keterangan |
| --- | --- | --- |
| `OPIS_DATABASE_URL` | `sqlite:///./opis.db` | URL SQLAlchemy; Compose mengisinya dengan PostgreSQL. |
| `OPIS_DEMO_DATA` | `true` | Seed data simulasi pada database kosong. |
| `OPIS_SCHEDULER_ENABLED` | `true` | Aktifkan scheduler dalam proses aplikasi. |
| `OPIS_ALLOW_PRIVATE_TARGETS` | `false` | Izinkan target lokal/privat; hanya untuk jaringan tepercaya. |
| `OPIS_CHECK_CONCURRENCY` | `10` | Maksimum pemeriksaan scheduler bersamaan, dari 1 hingga 100. |
| `OPIS_SCHEDULER_INTERVAL` | `2` | Interval polling scheduler dalam detik; minimum 0,25. |
| `OPIS_TEST_DATABASE_URL` | Tidak diatur | Database khusus pengujian; **tabel Opis dihapus oleh fixture**. |

Waktu disimpan dalam UTC dan ditampilkan dalam zona waktu browser. URL webhook disimpan di database; UI hanya menampilkan host URL yang tersimpan.

## Pengujian

Pengujian inti memakai dependency terversi, database terisolasi, dan respons HTTP palsu. Suite tidak bergantung pada ketersediaan layanan eksternal.

```bash
pip install -r requirements-lock.txt
pytest -q
```

### Pengujian dengan PostgreSQL melalui Docker

```bash
docker compose --profile test run --rm tests
# test-db memakai tmpfs dan terpisah dari database aplikasi.
docker compose --profile test stop test-db
```

Atau gunakan database PostgreSQL khusus pengujian yang sudah dibuat:

```bash
# PERINGATAN: fixture akan menghapus tabel Opis dalam database ini.
export OPIS_TEST_DATABASE_URL='postgresql+psycopg://opis_test:password@localhost:5432/opis_test'
pytest -q
```

Suite mencakup validasi target, status HTTP dan redirect, timeout/koneksi, ambang kegagalan dan pemulihan, webhook sukses/gagal, pencatatan kesalahan, data demo, scheduler, pengarsipan, catatan, ekspor CSV, dan perhitungan SLA.

### Pengujian browser opsional

```bash
pip install -r requirements-ui.txt
python -m playwright install chromium
# Pada Linux, jika diminta: python -m playwright install-deps chromium
pytest -q tests_ui
```

Pengujian browser menggunakan TestClient dan HTTPX mock; tidak memerlukan server atau jaringan eksternal saat pengujian. Untuk membuat ulang gambar pada README dengan dataset demo yang terisolasi:

```bash
python scripts/capture_screenshots.py
```

Perintah tersebut menulis gambar ke `docs/screenshots/` tanpa mengubah database aplikasi yang sedang berjalan.

## Keamanan dan batasan operasional

> [!WARNING]
> Opis **belum memiliki autentikasi, otorisasi, TLS termination, atau multi-user**. Jangan mengekspos aplikasi langsung ke internet. Gunakan pada jaringan tepercaya atau tambahkan autentikasi, TLS, dan kontrol akses pada reverse proxy.

- **Keamanan target:** URL HTTP(S) yang mengandung kredensial ditolak. Alamat IP lokal/privat dan host yang ter-resolve ke alamat tersebut diblokir secara default; redirect tidak diikuti. Validasi DNS ini **bukan perlindungan SSRF yang lengkap** karena DNS dapat berubah antara validasi dan koneksi. Batasi egress dengan jaringan/proxy dan isolasi tambahan untuk input yang tidak tepercaya. Aktifkan `OPIS_ALLOW_PRIVATE_TARGETS=true` hanya saat diperlukan dan pengguna/target tepercaya.
- **Rahasia dalam URL:** URL target dan webhook disimpan di database; URL webhook tersimpan dalam teks biasa. Hindari token atau rahasia di URL dan batasi akses database. Penyembunyian URL lengkap di UI bukan kontrol akses.
- **Scheduler:** kunci pemeriksaan hanya berlaku dalam satu proses. Jalankan **satu worker dan satu replika scheduler**; belum ada distributed locking atau antrean kerja untuk multi-replica.
- **Pengiriman webhook:** belum ada retry otomatis. Untuk jaminan pengiriman, tambahkan antrean persisten, retry/backoff, deduplikasi, dan autentikasi webhook.
- **Operasional:** belum ada retensi otomatis, migrasi database, atau rotasi log. Log ditulis ke stdout; atur retensi, backup, observability, dan akses sesuai lingkungan Anda.

## Struktur proyek

```text
opis/
├── app/
│   ├── main.py               # API, lifecycle, dan static frontend
│   ├── monitor.py            # pemeriksaan HTTPX, scheduler, webhook
│   ├── analytics.py          # status, ringkasan insiden, dan SLA
│   ├── models.py             # model SQLAlchemy
│   ├── seed.py               # data demo sintetis
│   └── static/               # HTML, CSS, JavaScript, dan font lokal
├── docs/
│   ├── assets/               # identitas visual Opis
│   └── screenshots/          # tangkapan layar untuk README
├── scripts/                  # pembuatan ulang tangkapan layar
├── tests/                    # unit dan integrasi terisolasi
├── tests_ui/                 # smoke test browser opsional
├── Dockerfile
├── docker-compose.yml
└── requirements-lock.txt
```

Font Manrope dan DM Sans disertakan dengan lisensi SIL Open Font License; teks lisensinya tersedia di `app/static/fonts/`.
