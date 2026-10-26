# Спайк bdo-toolkit на Windows

Перевірка, чи bdo-toolkit 1.0.15 бачить трафік гри і знімає інвентар та склади міст. Це етап 0 з [docs.md](../docs.md).

bdo-toolkit — бібліотека, а не фоновий агент: сам він нічого не захоплює і не зберігає. Знімок з'являється лише тоді, коли сесію захоплення запущено **до** входу персонажем.

Усе нижче — у **PowerShell** (Пуск → «PowerShell», права адміністратора не потрібні), з папки спайку `C:\dev\bdo-spike`, окремо від репозиторію.

## 0. Підготовка (один раз)

Потрібні Python 3.14 і Npcap (без галочки «Restrict Npcap driver's access to Administrators only»).

```powershell
py -3.14 -m venv C:\dev\bdo-spike\.venv
```

```powershell
C:\dev\bdo-spike\.venv\Scripts\pip install bdo-toolkit==1.0.15
```

Скопіюй скрипт знімка з репозиторію в папку спайку:

```powershell
copy C:\dev\bdo-assistant\spike\snapshot.py C:\dev\bdo-spike\
```

Перейди в папку спайку — усі наступні команди виконуються звідси:

```powershell
cd C:\dev\bdo-spike
```

`dir` має показати `.venv` і `snapshot.py`.

## 1. Профіль опкодів

Без профілю трафік не розпізнається. Свіжий профіль NA/EU від мейнтейнерів:

```powershell
.venv\Scripts\bdo-toolkit profile fetch https://ychwu.github.io/bdo-toolkit-profiles/channels/na-eu/stable.json --output opcodes.local
```

З'явиться файл `opcodes.local`. Після щотижневого патча профіль може кілька днів відставати — тоді знадобиться ручне калібрування.

## 2. Чи бачить захоплення гру

Зайди в гру на сервер і запусти:

```powershell
.venv\Scripts\bdo-toolkit diagnose-capture
```

Має бути пропозиція `game_port` з портами `8884,8885,8889`. `no_game` або `no_connections` — гра ще не на сервері.

Швидкий тест подій луту:

```powershell
.venv\Scripts\bdo-toolkit live --profile opcodes.local
```

Підбери щось або переклади предмет зі складу в інвентар — у терміналі мають з'явитися події. Зупинка — Ctrl+C.

## 3. Знімок інвентаря й складів

Склади міст надсилаються лише при **першому** вході у світ після запуску гри; зміна персонажа оновлює тільки інвентар.

1. Повністю закрий гру.
2. Запусти скрипт:
   ```powershell
   .venv\Scripts\python snapshot.py
   ```
3. Запусти гру, зайди персонажем, дочекайся, поки світ завантажиться, і натисни Enter у терміналі.

Знімок збережеться в `C:\dev\bdo-spike\snapshots\<дата-час>.json`.

## 4. Як зрозуміти, що вдалося

У виводі:

- `Hydration packets detected` — завантаження персонажа спіймане;
- `Storage decoder: compatible` — профіль підходить до поточного патча;
- `INVENTORY SNAPSHOT` — кількість стеків близька до реального інвентаря;
- `STORAGE SNAPSHOT` — `N/34 known destinations observed`, скільки складів міст побачено.

Немає рядка про hydration — скрипт запущено вже після входу у світ, або профіль застарів.

Вивід і JSON містять твої баланси й вміст складів: не викладай їх публічно.
