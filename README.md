# МТС Energytool: интерфейс чата

Запуск: `uvicorn server:app --port 8000`, затем http://localhost:8000
Файл index.html двойным кликом не откроется: используются ES-модули. Нужен любой сервер (uvicorn выше).
Отладка: `?debug=1`. Другой адрес бэкенда: `?api=http://host:port`.

## Структура
- index.html: разметка (дизайн прежний), стили в styles/main.css
- domain: сущности диалога и демо-сценарии
- application: ChatService (сценарии: отправить, новый диалог, заявка)
- infrastructure: HTTP-шлюз к /api, localStorage
- presentation: отрисовка DOM
- main.js: сборка зависимостей
- server.py: отдаёт интерфейс и вызывает solution.py
- solution.py: код команды, не изменён

## Подключение solution.py
solution.py лежит рядом с server.py вместе со своими модулями (chunks, config, consult, contract, dialogue, llm) и базой знаний.
Демо-заглушки больше нет: если solution.py не запускается, /api/consult отвечает 503, а чат показывает сообщение об ошибке.
Контракт ответа /api/consult:
{ answer, sources: [{path, title, quote, score}], lead: null | {fio, phone, company, summary} }
