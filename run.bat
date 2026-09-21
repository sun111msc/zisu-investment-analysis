@echo off
REM 紫苏投资分析 — 一键脚本（Windows）
REM
REM 用法：
REM   run.bat check           全量检查（lint + test + eval）
REM   run.bat demo            演示八类错误如何被拦截
REM   run.bat quickstart      跑一次完整分析
REM   run.bat analyze <文件>   分析指定场景
REM   run.bat gates           列出全部闸门
REM   run.bat eval            跑评测
REM   run.bat docs            本地启动文档站
REM   run.bat clean           清理缓存

setlocal
cd /d "%~dp0"
if "%PY%"=="" set PY=python

if "%~1"=="" goto help
if /i "%~1"=="check"      goto check
if /i "%~1"=="quickstart" goto quickstart
if /i "%~1"=="demo"       goto demo
if /i "%~1"=="analyze"    goto analyze
if /i "%~1"=="gates"      goto gates
if /i "%~1"=="eval"       goto eval
if /i "%~1"=="docs"       goto docs
if /i "%~1"=="clean"      goto clean
goto help

:check
echo.
echo [1/3] 静态检查 ruff
%PY% -m ruff check src tests evals || exit /b 1
echo.
echo [2/3] 测试 pytest
%PY% -m pytest -q || exit /b 1
echo.
echo [3/3] 评测 eval --strict
set PYTHONPATH=src
%PY% evals\run_eval.py --strict || exit /b 1
echo.
echo 全部通过
goto :eof

:quickstart
set PYTHONPATH=src
%PY% examples\quickstart.py
goto :eof

:demo
set PYTHONPATH=src
%PY% examples\gate_demo.py
goto :eof

:analyze
set PYTHONPATH=src
shift
%PY% -m zisu.cli analyze %1 %2 %3 %4 %5
goto :eof

:gates
set PYTHONPATH=src
%PY% -m zisu.cli gates
goto :eof

:eval
set PYTHONPATH=src
%PY% evals\run_eval.py --json --out evals\reports\latest.md
goto :eof

:docs
%PY% -m mkdocs serve
goto :eof

:clean
if exist .pytest_cache rmdir /s /q .pytest_cache
if exist .ruff_cache rmdir /s /q .ruff_cache
if exist .coverage del /q .coverage
if exist htmlcov rmdir /s /q htmlcov
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist site rmdir /s /q site
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
echo 完成
goto :eof

:help
echo.
echo 紫苏投资分析 — 一键脚本
echo.
echo   run.bat check       全量检查（lint + test + eval）
echo   run.bat quickstart  跑一次完整分析
echo   run.bat demo        演示八类错误如何被拦截
echo   run.bat analyze ^<场景.json^>   分析指定场景
echo   run.bat gates       列出全部闸门
echo   run.bat eval        跑评测
echo   run.bat docs        本地启动文档站
echo   run.bat clean       清理缓存
echo.
goto :eof
