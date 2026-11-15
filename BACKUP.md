# Резервная копия и откат

Кратко, как сохранить состояние проекта и вернуться к рабочей версии.

## Git (основной способ)

```powershell
git fetch origin
git checkout project-v1.1
git pull origin project-v1.1
```

Перед рискованными правками — отдельная ветка или тег:

```powershell
git checkout -b backup-2025-11-16
git push -u origin backup-2025-11-16
```

Откат файлов к последнему коммиту (локальные правки пропадут):

```powershell
git restore .
```

## Файлы вне git

| Что | Зачем |
|-----|--------|
| `.env` | ключи AITunnel; в репозитории есть копия для команды, но личные правки лучше дублировать |
| `out/crm.json` | заявки и сессии с сервера |
| `out/answer-cache.json` | кэш ответов LLM |
| `out/submission.csv`, `out/submission.zip` | последняя сдача |

Скопируйте каталог `out/` целиком:

```powershell
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
Copy-Item -Recurse out "out_backup_$stamp"
Copy-Item .env ".env_backup_$stamp" -ErrorAction SilentlyContinue
```

## Восстановление

1. Вернуть код: `git checkout project-v1.1` и `git pull`.
2. Подложить сохранённые `out/` и `.env` при необходимости.
3. Перезапустить: `.\run-web.ps1` или `docker compose up --build`.

ZIP для платформы по-прежнему собирается через `python package_zip.py` — в архив не попадают `.env`, база и `out/`.