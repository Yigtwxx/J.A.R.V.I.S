# J.A.R.V.I.S - AI Assistant 🤖

![JARVIS](https://img.shields.io/badge/JARVIS-AI%20Assistant-00f3ff?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?style=for-the-badge&logo=fastapi)
![Next.js](https://img.shields.io/badge/Next.js-15-black?style=for-the-badge&logo=next.js)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql)
![Platform](https://img.shields.io/badge/Platform-Windows%20|%20macOS%20|%20Linux-lightgrey?style=for-the-badge)

**Just A Rather Very Intelligent System** - Iron Man'deki JARVIS'ten esinlenerek yapılmış, yapay zeka destekli kişi profil arama asistanı.

## ✨ Özellikler

- 🧠 **Ollama AI Integration** - Ücretsiz, local AI ile akıllı profil analizi
- 🔍 **Web Scraping** - GitHub, Instagram, X (Twitter), LinkedIn profil arama
- 🌐 **Google Search** - Bilgi bulunamazsa otomatik Google araması
- 💾 **PostgreSQL Database** - Onaylanan profilleri güvenli şekilde saklama
- 🎨 **Futuristic UI** - Iron Man temalı, Arc Reactor efektli arayüz
- ⚡ **Real-time Search** - Anında sonuçlar ve dinamik yükleme animasyonları
- 🖥️ **Cross-Platform** - Windows, macOS ve Linux desteği

## 🏗️ Proje Yapısı

```
J.A.R.V.I.S/
├── backend/              # FastAPI Backend
│   ├── app/
│   │   ├── models/      # SQLAlchemy modelleri
│   │   ├── routes/      # API endpoints
│   │   ├── services/    # İş mantığı
│   │   └── schemas/     # Pydantic schemas
│   └── requirements.txt
│
├── frontend/            # Next.js Frontend
│   ├── app/            # Next.js app directory
│   ├── components/     # React bileşenleri
│   ├── services/       # API servisleri
│   └── types/          # TypeScript tipleri
│
├── database/
│   └── init.sql        # PostgreSQL şema
│
├── start-jarvis.bat    # Windows başlatma scripti
└── start-jarvis.sh     # macOS/Linux başlatma scripti
```

## 🚀 Kurulum

### Gereksinimler

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+
- Ollama (AI için)

### 1. Ollama Kurulumu

```bash
# Ollama'yı indirin ve kurun: https://ollama.ai/download

# Llama 3 modelini indirin
ollama pull llama3
```

### 2. PostgreSQL Kurulumu

<details>
<summary><strong>🪟 Windows</strong></summary>

```bash
# PostgreSQL'i indirin: https://www.postgresql.org/download/windows/
# Kurulumdan sonra database oluşturun
createdb jarvis

# Schema'yı yükleyin
psql -U postgres -d jarvis -f database/init.sql
```
</details>

<details>
<summary><strong>🍎 macOS</strong></summary>

```bash
# Homebrew ile PostgreSQL kurulumu
brew install postgresql@16
brew services start postgresql@16

# Database oluşturun
createdb jarvis

# Schema'yı yükleyin
psql -d jarvis -f database/init.sql
```
</details>

<details>
<summary><strong>🐧 Linux</strong></summary>

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# Database oluşturun
sudo -u postgres createdb jarvis

# Schema'yı yükleyin
sudo -u postgres psql -d jarvis -f database/init.sql
```
</details>

### 3. Hızlı Başlatma (Önerilen)

**Tek Komutla Her Şeyi Başlatın:**

<details>
<summary><strong>🪟 Windows</strong></summary>

```bash
# Ana dizinde
start-jarvis.bat
```
</details>

<details>
<summary><strong>🍎 macOS / 🐧 Linux</strong></summary>

```bash
# Ana dizinde
chmod +x start-jarvis.sh  # İlk seferde çalıştırma izni verin
./start-jarvis.sh
```
</details>

Bu script:
- ✅ Ollama ve PostgreSQL kontrolü yapar
- ✅ Backend virtual environment oluşturur
- ✅ Tüm bağımlılıkları yükler
- ✅ Backend ve Frontend'i arka planda başlatır
- ✅ Tarayıcıyı otomatik açar

### 4. Manuel Kurulum (Alternatif)

<details>
<summary><strong>🪟 Windows</strong></summary>

**Backend:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# .env dosyasını düzenleyin
python -m app.main
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```
</details>

<details>
<summary><strong>🍎 macOS / 🐧 Linux</strong></summary>

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env dosyasını düzenleyin
python -m app.main
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```
</details>

## 💻 Kullanım

### Hızlı Başlatma

**Windows:**
```bash
start-jarvis.bat  # Her şeyi otomatik başlatır
```

**macOS / Linux:**
```bash
./start-jarvis.sh  # Her şeyi otomatik başlatır
```

### Kullanım Adımları
1. **Uygulamayı açın**: Script otomatik açacak veya `http://localhost:3000`
2. **Bir isim girin**: Örnek: "Linus Torvalds", "Yiğit Erdoğan"
3. **JARVIS araştırsın**: AI, GitHub, sosyal medya ve web'de arama yapacak
4. **Sonuçları inceleyin**: JARVIS bulunan tüm bilgileri size sunacak
5. **Onaylayın**: Beğendiyseniz "Save" butonuna basın, PostgreSQL'e kaydedilsin

### Terminal Çıktısı
Backend'de güzel formatlanmış loglar göreceksiniz:
```
============================================================
🔍 NEW SEARCH REQUEST: Linus Torvalds
============================================================
[1/4] 🐙 Searching GitHub...
      ✅ GitHub profile found: https://github.com/torvalds
[2/4] 📱 Searching social media...
      ✅ Found 2 social media profiles
[3/4] 🌐 Searching Google...
      ✅ Web search completed
[4/4] 🤖 JARVIS analyzing data...
      ✅ Analysis complete

✅ SEARCH COMPLETED: Linus Torvalds
============================================================
```

## 🎨 Kullanılan Teknolojiler

### Backend
- **FastAPI** - Modern, hızlı web framework
- **Ollama** - Ücretsiz, local AI
- **SQLAlchemy** - ORM
- **BeautifulSoup** - Web scraping
- **PostgreSQL** - Database

### Frontend
- **Next.js 15** - React framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Framer Motion** - Animasyonlar
- **Axios** - HTTP client

## 🔧 API Endpoints

### Search
```http
POST /api/search/
Content-Type: application/json

{
  "query": "Yiğit Erdoğan"
}
```

### Profiles
```http
GET    /api/profiles/              # Tüm profiller
GET    /api/profiles/{id}          # Belirli bir profil
POST   /api/profiles/              # Yeni profil oluştur
DELETE /api/profiles/{id}          # Profil sil
GET    /api/profiles/search/{name} # İsme göre ara
```

## 🎯 Özellik Roadmap

- [ ] Voice input (ses ile arama)
- [ ] Multiple language support
- [ ] Export profilleri (JSON, CSV)
- [ ] Advanced filtering
- [ ] Email notifications
- [ ] Chrome extension

## 🐛 Bilinen Sorunlar

- Instagram ve X (Twitter) scraping platformların rate limiting'i nedeniyle bazen başarısız olabilir
- Ollama ilk kullanımda model download ettiği için yavaş olabilir
- Google scraping CAPTCHA ile karşılaşabilir

## 📝 Lisans

MIT License - İstediğiniz gibi kullanabilirsiniz!

## 👨‍💻 Geliştirici

Yiğit Erdoğan

## 🙏 Teşekkürler

- Marvel Studios - JARVIS konsepti için
- Tony Stark - İlham için 😄
- Ollama Team - Ücretsiz AI için

---

**"Sometimes you gotta run before you can walk."** - Tony Stark