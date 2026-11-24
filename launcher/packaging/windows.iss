#ifndef LauncherVersion
  #define LauncherVersion "0.3.5"
#endif
[Setup]
AppId=Sharkfj.NETLauncher
AppName=.NET Launcher
AppVersion={#LauncherVersion}
DefaultDirName={localappdata}\Programs\NET Launcher
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
DisableProgramGroupPage=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\NET-Launcher.exe
OutputDir=../dist
OutputBaseFilename=NET-Launcher-Setup
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "../dist/NET-Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\NET Launcher"; Filename: "{app}\NET-Launcher.exe"; AppUserModelID: "Sharkfj.NETLauncher"
Name: "{autodesktop}\NET Launcher"; Filename: "{app}\NET-Launcher.exe"; AppUserModelID: "Sharkfj.NETLauncher"; Tasks: desktopicon

[Run]
Filename: "{app}\NET-Launcher.exe"; Description: "Open .NET Launcher"; Flags: nowait postinstall skipifsilent
