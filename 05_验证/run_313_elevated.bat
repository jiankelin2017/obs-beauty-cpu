@echo off
rem Elevated wrapper: runs install_313.bat with output captured to a log.
rem Invoke via ShellExecute "runas" so UAC elevates this wrapper.
call "C:\legacy_e2e\install_313.bat" > "C:\legacy_e2e\install_313.log" 2>&1
echo EXITCODE=%errorlevel% >> "C:\legacy_e2e\install_313.log"
echo [WRAPPER-FINISHED] >> "C:\legacy_e2e\install_313.log"
exit /b %errorlevel%
