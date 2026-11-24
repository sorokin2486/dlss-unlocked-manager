# DLSS Unlocked Manager

Программа для Windows, которая находит игры с поддержкой DLSS и в один клик ставит в них мод
[DLSS Unlocked](https://github.com/ShyVortex/dlss-unlocked). Мод основан на OptiScaler. Он включает
генерацию кадров DLSS (в том числе мультикадровую) и DLSS Neural Rendering («DLSS 5») на видеокартах
RTX 20, 30 и 40.

> Это неофициальный проект. Он не связан с NVIDIA, авторами DLSS Unlocked или OptiScaler.
> DLSS — торговая марка NVIDIA Corporation.

## Что умеет

- **Находит игры.** Сканирует все библиотеки Steam и сам определяет, где лежит основной exe и есть ли
  в игре DLSS Super Resolution и Frame Generation.
- **Ставит мод из любой папки.** Игры не из Steam добавляются кнопкой «Добавить папку».
- **Не трогает онлайн-игры с античитом.** Игры с EasyAntiCheat, BattlEye, ACE и другими античитами
  помечаются и не устанавливаются: за мод в них можно получить бан.
- **Скачивает свежий мод** из релизов GitHub, с проверкой размера и защитой от вредных путей в архиве.
- **Ставит и удаляет без следов.** Файлы игры, которые мод заменяет, сохраняются в резервную копию и
  возвращаются при удалении. Список установленных файлов хранится рядом с игрой.
- **Знает про игры Capcom на RE Engine** и предлагает поставить вместе с модом REFramework.
- **Даёт сменить клавишу меню OptiScaler** (по умолчанию F8 вместо Insert) и имя прокси-DLL.
- Светлая и тёмная тема в стиле Windows 11.

## Требования

- Windows 10 или 11, видеокарта NVIDIA RTX 20 / 30 / 40.
- Игра на DirectX 12 со встроенными DLSS и DLSS Frame Generation.

## Установка

Скачайте `DLSS Manager.exe` из [Releases](../../releases) и запустите. Python не нужен.

## Запуск из исходников

```powershell
pip install -r requirements.txt
python -m dlss_manager
```

Есть и командная строка:

```powershell
python -m dlss_manager scan              # игры с DLSS
python -m dlss_manager scan --all -v     # все игры с подробностями
python -m dlss_manager download          # скачать последнюю версию мода
python -m dlss_manager install "Witcher 3" --menu-key F8
python -m dlss_manager install "D:\Games\MyGame"   # игра не из Steam
python -m dlss_manager uninstall "Witcher 3"
```

## Разработка

```powershell
pip install -r requirements-dev.txt
python -m pytest tests     # тесты
python build_exe.py        # собрать DLSS Manager.exe
python tools/make_icon.py  # перерисовать иконку (dlss_manager/ui/assets)
```

Данные программы (скачанный мод, настройки, список своих папок) лежат в
`%LOCALAPPDATA%\DLSSUnlockedManager`.

## Лицензия

[MIT](LICENSE). Мод DLSS Unlocked и OptiScaler распространяются под своими лицензиями и в репозиторий
не входят: программа скачивает их с GitHub при первом запуске.
