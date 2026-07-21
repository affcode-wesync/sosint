# Email Analyzer - OSINT Tool

Инструмент для анализа email-адресов с использованием различных источников данных.

## Возможности

- **Валидация email** — проверка формата
- **DNS анализ** — MX, SPF, DKIM, DMARC записи
- **Проверка утечек** — Have I Been Pwned (HIBP)
- **Gravatar профиль** — поиск аватара и информации
- **Социальные сети** — проверка по username
- **WHOIS** — информация о домене
- **Порты** — проверка SMTP/IMAP/POP3 портов
- **Оценка риска** — автоматический расчет уровня угрозы

## Установка

1. Установите Python 3.9+

2. Установите зависимости:
```bash
cd email-analyzer/backend
pip install -r requirements.txt
```

3. Запустите сервер:
```bash
cd email-analyzer/backend
python main.py
```

4. Откройте в браузере: http://localhost:8000

## API Endpoints

- `POST /api/analyze` — анализ email
- `GET /api/health` — проверка здоровья сервера

## Пример запроса

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"email": "example@gmail.com"}'
```

## Технологии

- **Backend:** FastAPI, Python
- **Frontend:** HTML/CSS/JavaScript (SPA)
- **Библиотеки:** dnspython, httpx, python-whois

## Важно

Используйте инструмент ответственно и только для легитимных целей анализа.
