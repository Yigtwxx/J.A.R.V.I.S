# J.A.R.V.I.S Setup Guide

## Hızlı Başlangıç

### 1. Ollama Kurulumu ve Model İndirme

```bash
# Ollama'yı indirin: https://ollama.ai/download
# Kurulumdan sonra:

ollama pull llama3
```

### 2. PostgreSQL Kurulumu

<details>
<summary><strong>🪟 Windows</strong></summary>

```bash
# PostgreSQL'i indirin: https://www.postgresql.org/download/
# Kurulumdan sonra database oluşturun:

createdb jarvis

# Schema'yı yükleyin (PostgreSQL dizininde):
psql -U postgres -d jarvis -f database/init.sql
```
</details>

<details>
<summary><strong>🍎 macOS</strong></summary>

```bash
# Homebrew ile kurulum
brew install postgresql@16
brew services start postgresql@16

# Database oluşturun
createdb jarvis

# Schema'yı yükleyin
psql -d jarvis -f database/init.sql
```
</details>

<details>
<summary><strong>🐧 Linux (Ubuntu/Debian)</strong></summary>

```bash
# PostgreSQL kurulumu
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# Database oluşturun
sudo -u postgres createdb jarvis

# Schema'yı yükleyin
sudo -u postgres psql -d jarvis -f database/init.sql
```
</details>

### 3. Backend Environment Setup

`backend/.env` dosyasını oluşturun:

```env
DATABASE_URL=postgresql://postgres:SİFRENİZ@localhost:5432/jarvis
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
GITHUB_TOKEN=
HOST=0.0.0.0
PORT=8000
```

**Önemli**: `SİFRENİZ` kısmını PostgreSQL şifrenizle değiştirin!

### 4. Hızlı Başlatma (Otomatik Script)

<details>
<summary><strong>🪟 Windows</strong></summary>

```bash
start-jarvis.bat
```
</details>

<details>
<summary><strong>🍎 macOS / 🐧 Linux</strong></summary>

```bash
# İlk seferde çalıştırma izni verin
chmod +x start-jarvis.sh

# Başlatın
./start-jarvis.sh
```
</details>

### 5. Manuel Başlatma (Alternatif)

<details>
<summary><strong>🪟 Windows</strong></summary>

**Backend:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
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
python -m app.main
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```
</details>

## Sorun Giderme

### Ollama Çalışmıyor
```bash
# Ollama servisinin çalıştığını kontrol edin
ollama serve

# Model listesini kontrol edin
ollama list
```

### PostgreSQL Bağlantı Hatası

<details>
<summary><strong>🪟 Windows</strong></summary>

- PostgreSQL servisinin çalıştığını kontrol edin (Windows Services)
- Database URL'in doğru olduğunu kontrol edin
- Database'in oluşturulduğunu kontrol edin: `psql -U postgres -l`
</details>

<details>
<summary><strong>🍎 macOS</strong></summary>

```bash
# PostgreSQL servisini kontrol edin
brew services list

# Servisi başlatın (durduysa)
brew services start postgresql@16

# Database listesini kontrol edin
psql -l
```
</details>

<details>
<summary><strong>🐧 Linux</strong></summary>

```bash
# Servis durumunu kontrol edin
sudo systemctl status postgresql

# Servisi başlatın
sudo systemctl start postgresql

# Database listesini kontrol edin
sudo -u postgres psql -l
```
</details>

### Frontend Backend'e Bağlanamıyor
- Backend'in çalıştığını kontrol edin: `http://localhost:8000/health`
- CORS hatası alıyorsanız, `backend/app/main.py`'daki CORS ayarlarını kontrol edin

### Import Hataları

<details>
<summary><strong>🪟 Windows</strong></summary>

```bash
# Backend dependencies'i yeniden yükleyin
cd backend
pip install --upgrade pip
pip install -r requirements.txt

# Frontend dependencies'i yeniden yükleyin
cd frontend
rmdir /s /q node_modules
del package-lock.json
npm install
```
</details>

<details>
<summary><strong>🍎 macOS / 🐧 Linux</strong></summary>

```bash
# Backend dependencies'i yeniden yükleyin
cd backend
pip install --upgrade pip
pip install -r requirements.txt

# Frontend dependencies'i yeniden yükleyin
cd frontend
rm -rf node_modules package-lock.json
npm install
```
</details>

## Test Etme

1. Backend test: `http://localhost:8000/docs` (Swagger UI)
2. Frontend test: `http://localhost:3000`
3. Basit arama yapın: "Yiğit Erdoğan" gibi bir isim girin

## İlk Kullanım

1. Backend ve Frontend'i başlatın
2. `http://localhost:3000` adresini açın
3. JARVIS sizi karşılayacak
4. Bir isim girin (örn: "Linus Torvalds")
5. JARVIS bilgileri araştırsın
6. Beğendiyseniz "Save" butonuna basın

