' Elevate via ShellExecute "runas" (legitimate UAC consent prompt, not a bypass)
Dim sh
Set sh = CreateObject("Shell.Application")
sh.ShellExecute "C:\nama_e2e\run_313_elevated.bat", "", "", "runas", 1
Set sh = Nothing
