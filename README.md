# BDO Companion

Особистий трекер акаунта Black Desert (EU): персонажі, робітники, транспорт, знання, інвентар і склади
з пасивного читання власного трафіку гри, ціни — з arsha.io. Усе працює локально на ігровому ПК.
Задум, джерела даних і межі — у [docs.md](docs.md).

## Встановлення (один раз)

Потрібні Python 3.14, Node.js (лише для збірки фронту) і [Npcap](https://npcap.com) без опції
«Restrict Npcap driver's access to Administrators only».

```powershell
py -3.14 -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt
npm install
npm run build
```

Для знімків інвентаря покладіть профіль опкодів bdo-toolkit у `backend\opcodes.local`
(або вкажіть шлях у `BDO_OPCODE_PROFILE`).

## Запуск

```powershell
cd backend
.venv\Scripts\pythonw.exe tray.py
```

Відкриється браузер на http://127.0.0.1:8000, а в треї з'явиться іконка: «Відкрити», «Агент слухає гру»,
«Вихід». Агент вмикається одразу (`--no-agent`, щоб ні). Автозапуск з Windows:
`.venv\Scripts\python.exe tray.py --install-autostart` (прибрати — `--remove-autostart`).

Після змін у фронті — знову `npm run build`.

## Питання до локальних даних через MCP

У VS Code відкрийте Copilot Chat і виберіть модель із підтримкою MCP. Workspace-сервер `bdo-companion`
надає інструменти для пошуку незакритих категорій знань, які збільшують максимальну Енергію, та списку
відсутніх знань із підказками й NPC. Наприклад: «Хочу збільшити максимальну Енергію. Яку категорію
найшвидше закрити?» або «Що саме мені потрібно знайти в цій категорії?»

Перед першим запитом встановіть залежності (`backend\\.venv\\Scripts\\pip install -r backend\\requirements.txt`)
і запустіть застосунок хоча б один раз, щоб створилася локальна база. Для персональних результатів
імпортуйте власні дані знань. У VS Code виконайте `MCP: List Servers` і запустіть `bdo-companion`, якщо
він ще не запущений. Відповіді про прогрес спираються на цю локальну базу; без імпортованих знань
сервер не зможе визначити, що вже вивчено.

## Розробка

```powershell
cd backend; .venv\Scripts\python.exe -m uvicorn main:app --port 8000
npm run dev
```

`npm run dev` бере адресу бекенду з `.env.development.local` (`NEXT_PUBLIC_API_URL=http://localhost:8000`).
Тести: `backend\.venv\Scripts\python.exe -m pytest backend\tests`.
