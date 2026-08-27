# AGENTS.md

## Проект и ownership

Перед работой прочитать `README.md` и `docs/swift-architecture.md`.

- Native Swift implementation живёт в `Sources/HotkeyMaster`,
  `Sources/HotkeyMasterKit` и `Sources/CMultitouchBridge`.
- Root Python/PyQt implementation является legacy reference и rollback path.
  Не менять его вместе со Swift feature без отдельной compatibility-задачи.
- Private `MultitouchSupport.framework` изолирован C bridge; отсутствие
  framework/trackpad не должно ломать keyboard rules или запуск приложения.

## Проверки

- Для scoped Swift change запускать `make check` и `make swift-build`.
- Packaging change дополнительно проверять через `make app` и code-signature
  validation существующего build flow.
- `make install` заменяет `/Applications/HotkeyMaster.app`; build/change/commit
  не разрешают установку. Устанавливать только по явной просьбе, сохраняя
  штатный backup/rollback и повторно проверяя запущенную версию.
- Accessibility permission является внешним состоянием пользователя. Не
  сбрасывать и не менять его автоматически; проверять keyboard/gesture paths с
  учётом фактического permission state.

## Performance и gesture diagnostics

- Делать короткие контролируемые OFF/ON и component A/B окна. Записывать app
  CPU, WindowServer, wakeups/context switches и релевантные logs; шумный baseline
  и корреляцию не называть причиной без counterexample.
- Disabled gesture path не должен поддерживать high-frequency bridge traffic.
  Минимальное число contacts выводить из реально включённых rules, а не из
  широкого experimental toggle.
- При воспроизведении жестов проверять false positives на обычных one-finger
  touches и конфликт между tap/swipe actions, а не только intended gesture.

## Evidence и Git

- Различать `implemented`, `checks-passed`, `app-built`, `installed` и
  `runtime-verified`. Успешная сборка не доказывает поведение установленного app.
- Проверять branch/status/diff, не откатывать чужие изменения и stage только
  scoped файлы. Один логический этап — один commit.
- Local commit не разрешает push, release, замену установленного приложения или
  изменение login-item state.
