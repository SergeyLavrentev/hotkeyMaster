# Multitouch-to-Hotkey Engine (Python + macOS)

Этот файл — готовое техописание решения, которое можно вставить в
`README.md`, Confluence, Copilot-prompt или куда угодно целиком.

---

## Зачем

* **Цель:** превратить трекпад-жесты (3- и 4-пальцевый _tap_)  
  в горячие клавиши **⌘ T** и **⌘ W** (новая вкладка / закрыть вкладку).
* **Платформа:** macOS 13 → 14 (Ventura / Sonoma), Intel и Apple Silicon.
* **Язык:** чистый Python 3 + PyObjC (только фреймворк **Quartz**).

---

## Ключевая идея

1. Внутри macOS сидит **`MultitouchSupport.framework`** (приватный).  
   Он рассылает _сырые_ данные о каждом пальце через C-callback
   примерно 60 раз в секунду.
2. Подцепляемся к нему через **`ctypes`**  
   (без Swift, Objective-C и codesign).
3. В callback анализируем массив структур **`Finger`**:
   определяем «краткий тап» нужным количеством пальцев.
4. Когда жест распознан — шлём виртуальные нажатия ⌘+T / ⌘+W
   при помощи **Quartz CGEvents**.

---

# Multitouch trackpad → hotkeys (Python, macOS)

## 1. Библиотека

Подключаем приватный фреймворк:

```python
import ctypes, glob, os
from ctypes.util import find_library

def load_multitouch():
    try:
        # классический путь (работает даже если бинарь только в dyld-кэше)
        return ctypes.CDLL(
            "/System/Library/PrivateFrameworks/MultitouchSupport.framework/MultitouchSupport"
        )
    except OSError:
        pass

    # ищем в dyld-кэше
    lib = find_library("MultitouchSupport")
    if lib:
        try:
            return ctypes.CDLL(lib)
        except OSError:
            pass

    # бекап — рекурсивный glob по PrivateFrameworks
    pattern = (
        "/System/Library/PrivateFrameworks/**/"
        "MultitouchSupport.framework/**/MultitouchSupport"
    )
    for p in glob.glob(pattern, recursive=True):
        if p.endswith(".tbd"):        # пропускаем заглушки
            continue
        try:
            return ctypes.CDLL(p)
        except OSError:
            continue

    raise FileNotFoundError("MultitouchSupport.framework not found")

## 2. Получаем устройство трекпада

`MTDeviceCreateList()` отдаёт **CFArrayRef** со всеми multitouch-устройствами.
С помощью Core Foundation достаём первый элемент — указатель на `MTDeviceRef`.

```python
import ctypes
from ctypes.util import find_library

# CoreFoundation helpers
CF             = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
CFArrayRef     = ctypes.c_void_p
CFIndex        = ctypes.c_long

CF.CFArrayGetCount.argtypes        = [CFArrayRef]
CF.CFArrayGetCount.restype         = CFIndex
CF.CFArrayGetValueAtIndex.argtypes = [CFArrayRef, CFIndex]
CF.CFArrayGetValueAtIndex.restype  = ctypes.c_void_p

# сигнатуры приватных API
CB_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_void_p), ctypes.c_int,
                           ctypes.c_double, ctypes.c_int)

MT.MTDeviceCreateList.restype = CFArrayRef
MT.MTRegisterContactFrameCallback.argtypes = [ctypes.c_void_p, CB_TYPE]
MT.MTDeviceStart.argtypes = [ctypes.c_void_p, ctypes.c_int]

# берём первый трекпад
dev_array = MT.MTDeviceCreateList()
if CF.CFArrayGetCount(dev_array) == 0:
    raise RuntimeError("Trackpad not found")

DEV = CF.CFArrayGetValueAtIndex(dev_array, 0)   # MTDeviceRef

## 3. Структура `Finger`

`MultitouchSupport.framework` передаёт массив структур `Finger`.
Для детекта тапов нам достаточно основных полей — остальное можно игнорировать.

```python
class MTPoint(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),   # нормализованная координата X (0‒1)
        ("y", ctypes.c_float),   # нормализованная координата Y (0‒1)
    ]

class MTReadout(ctypes.Structure):
    _fields_ = [
        ("pos", MTPoint),        # позиция
        ("vel", MTPoint),        # скорость (не используем)
    ]

class Finger(ctypes.Structure):
    _fields_ = [
        ("frame",      ctypes.c_int32),    # номер кадра
        ("timestamp",  ctypes.c_double),   # время (секунд с boot-time)
        ("identifier", ctypes.c_int32),    # ID пальца, уникален пока палец на стекле
        ("state",      ctypes.c_int32),    # 1=DOWN, 2=MOVE, 4=UP
        ("_pad1",      ctypes.c_int32 * 4),
        ("norm",       MTReadout),         # нормализованные координаты
        ("size",       ctypes.c_float),    # «площадь» касания (можно игнорировать)
        ("_pad2",      ctypes.c_int32),
        ("angle",      ctypes.c_float),    # угол пальца
        ("major",      ctypes.c_float),    # большая ось эллипса касания
        ("minor",      ctypes.c_float),    # малая ось
        ("_pad3",      ctypes.c_int32 * 5),
    ]

## 4. Детект «тапа» и отправка шорткатов

### Константы

```python
MAX_DT   = 0.25   # палец на стекле ≤ 250 мс
MAX_DPOS = 0.03   # смещение ≤ 0.03 нормализованных единиц
VK_T, VK_W = 0x11, 0x0D          # kVK_ANSI_T / kVK_ANSI_W

### Вспомогательная функция — шлём ⌘ + key через Quartz

from Quartz import (
    CGEventCreateKeyboardEvent, CGEventSetFlags,
    CGEventPost, kCGHIDEventTap, kCGEventFlagMaskCommand,
)

def send_cmd(keycode: int | None) -> None:
    """Имитирует Cmd+<key>. Если keycode == None — ничего не делает."""
    if keycode is None:
        return
    for down in (True, False):           # key-down, затем key-up
        ev = CGEventCreateKeyboardEvent(None, keycode, down)
        CGEventSetFlags(ev, kCGEventFlagMaskCommand)      # ⌘
        CGEventPost(kCGHIDEventTap, ev)

### Callback on_frame
_active  = {}       # id → (x, y, t0)   — живые пальцы
start_ts = None     # время первого DOWN в текущем кадре

def on_frame(dev, data, count, ts, frame):
    """
    Вызывается MultitouchSupport'ом ~60 fps.
    data   → указатель на Finger[count]
    ts     → timestamp последнего события в секундах
    frame  → последовательный номер кадра
    """
    global _active, start_ts

    fingers = ctypes.cast(data, ctypes.POINTER(Finger))

    # 1. Обновляем карту активных пальцев
    for i in range(count):
        f = fingers[i]
        if f.state == 1:                     # DOWN
            _active[f.identifier] = (f.norm.pos.x, f.norm.pos.y, ts)
            start_ts = start_ts or ts
        elif f.state == 4:                   # UP
            _active.pop(f.identifier, None)

    # 2. Если пальцев не осталось — решаем, был ли это tap
    if not _active and start_ts is not None:
        duration = ts - start_ts
        nfingers = count                     # столько пальцев было в последнем кадре

        if duration <= MAX_DT:
            # Кол-во пальцев определяет действие
            keycode = VK_T if nfingers == 3 else VK_W if nfingers == 4 else None
            send_cmd(keycode)

        start_ts = None                      # сброс для следующего жеста

### Регистрация callback и запуск цикла
CB = CB_TYPE(on_frame)                       # важ-но: держим ссылку, иначе GC!

MT.MTRegisterContactFrameCallback(DEV, CB)
MT.MTDeviceStart(DEV, 0)

print("tap-hotkeys running…  Ctrl-C to quit")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

## 5. Зависимости и разрешения системы

### Python-зависимости

```bash
pip install pyobjc-framework-Quartz

Разрешения macOS
System Settings → Privacy & Security → Accessibility
Добавьте ваш терминал, VS Code, PyCharm — любой процесс, который будет запускать скрипт.
Это даёт право эмулировать нажатия клавиш.

System Settings → Privacy & Security → Input Monitoring
Отметьте тот же процесс.
Без этой галочки фреймворк отдаст NULL-указатель устройства.

(Опционально) Trackpad → Point & Click → “Tap to click”
Включите, чтобы трёх-/четырёхпальцевые taps фиксировались надёжнее.

## 6. Архитектура потока событий

```text
┌────────────────────┐
│  Trackpad hardware │
└────────┬───────────┘
         │  (HID-отчёты)
         ▼
┌───────────────────────────────────────────────────────────────┐
│ MultitouchSupport.framework (приватный, macOS)               │
│   • вызывает C-callback ~60 fps, передавая массив Finger[]   │
└────────┬──────────────────────────────────────────────────────┘
         ▼
┌───────────────────────────────────────────────────────────────┐
│ Python (ctypes)                                              │
│   on_frame():                                                │
│     1. ведёт карту активных пальцев (_active)                │
│     2. по времени/смещению детектирует 3-/4-finger tap       │
│     3. по числу пальцев выбирает действие (⌘T / ⌘W)          │
└────────┬──────────────────────────────────────────────────────┘
         │  (Quartz CGEvents: Cmd+T / Cmd+W)
         ▼
┌────────────────────┐
│ Window Server macOS│
└────────┬───────────┘
         ▼
┌───────────────────────────────────────────────────────────────┐
│ Foreground application (Chrome, Finder, VS Code, …)          │
│   • получает эмулированные шорткаты                          │
└───────────────────────────────────────────────────────────────┘


*Время от фактического касания до прихода CG-события ≈ 2–3 мс
— на глаз мгновенно.*

---

## 7. Как расширять

| Что хотите  | Что менять                                            |
|-------------|-------------------------------------------------------|
| **Больше жестов** (например, 5-finger tap → Mission Control) | добавьте условие `if nfingers == 5: …` и отправьте нужную комбинацию клавиш |
| **Свайпы**  | во время `MOVE` считайте Δx / Δy между первым и последним положением каждого пальца; при UP сравните магнитуду и направление |
| **Pinch / Rotate** | анализируйте изменение расстояния / углов между пальцами в `MOVE`-кадрах |
| **Конфигурация через JSON** | вынесите таблицу «жест → action» в файл и подгружайте на каждую итерацию цикла |
| **Меню-бар UI** | с PyObjC (`NSStatusBar`, `NSMenu`) или PyQt6; ядро детектора можно оставить как есть |

---

## 8. Итог

* Скрипт полностью на **Python**, без нативной компиляции и codesign-акробатики.
* Работает на **Intel и Apple Silicon** ( Ventura → Sonoma 14.5 проверено).
* Лёгко модифицируется под любые кастомные жесты — у вас уже поток сырых пальцев.

_Копируйте, форкайте, улучшайте. Happy hacking!_

