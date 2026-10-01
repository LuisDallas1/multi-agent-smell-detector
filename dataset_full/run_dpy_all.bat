@echo off

for /D %%R in ("new_dataset\*") do (
    echo.
    echo ========================================
    echo Analisando: %%~nxR
    echo ========================================

    DPy.exe analyze ^
        -i "%%R" ^
        -o "resultado\%%~nxR" ^
        -c "config.json"
)

echo.
echo ========================================
echo ANALISE CONCLUIDA
echo ========================================
pause