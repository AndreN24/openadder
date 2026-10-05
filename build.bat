@echo off
rem Builds dist\OpenAdder\OpenAdder.exe.
rem Needs Python 3 to build. Running OpenAdder needs nothing.
rem The build uses its own clean environment (.venv-build) with only the libraries
rem OpenAdder uses, so nothing else from your Python installation ends up in the app.
cd /d "%~dp0"

if not exist .venv-build\Scripts\python.exe (
  echo Creating the build environment...
  py -3 -m venv .venv-build || exit /b 1
  .venv-build\Scripts\python -m pip install --quiet --upgrade pip
  .venv-build\Scripts\python -m pip install --quiet -r requirements.txt pyinstaller || exit /b 1
)

.venv-build\Scripts\python tools\make_version_file.py || exit /b 1
.venv-build\Scripts\python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name OpenAdder ^
  --icon assets\openadder.ico ^
  --version-file build\version_info.txt ^
  --add-data "openadder\assets\art;openadder\assets\art" ^
  --add-data "assets\openadder.ico;assets" ^
  --exclude-module unittest --exclude-module pydoc --exclude-module doctest ^
  --exclude-module email --exclude-module http --exclude-module xmlrpc --exclude-module xml ^
  --exclude-module multiprocessing --exclude-module asyncio --exclude-module sqlite3 ^
  --exclude-module ssl --exclude-module lzma --exclude-module bz2 --exclude-module decimal ^
  --exclude-module tkinter.tix --exclude-module _hashlib --exclude-module unicodedata ^
  --exclude-module PIL --exclude-module sv_ttk --exclude-module pystray ^
  OpenAdder.pyw || exit /b 1

rem Tcl/Tk data that OpenAdder does not use: time zones, translations, demos,
rem East Asian text encodings, and the Tcl web and test packages.
set I=dist\OpenAdder\_internal
for %%d in (_tcl_data\tzdata _tcl_data\msgs _tk_data\msgs _tk_data\demos _tk_data\images) do (
  if exist "%I%\%%d" rmdir /s /q "%I%\%%d"
)
for %%e in (big5 cns11643 cp932 cp936 cp949 cp950 euc-cn euc-jp euc-kr gb12345 gb1988 gb2312 gb2312-raw jis0201 jis0208 jis0212 ksc5601 macJapan shiftjis) do (
  if exist "%I%\_tcl_data\encoding\%%e.enc" del /q "%I%\_tcl_data\encoding\%%e.enc"
)
del /q "%I%\tcl8\8.6\http-*.tm" "%I%\tcl8\8.5\tcltest-*.tm" 2>nul

echo.
echo Done: dist\OpenAdder\OpenAdder.exe
