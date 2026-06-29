Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName) & "\novel-chapter-exporter"
shell.CurrentDirectory = base
shell.Run "pythonw.exe """ & base & "\gui\smart_downloader_gui.py""", 0, False
